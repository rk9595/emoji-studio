import hashlib
import io
import sqlite3
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from PIL import Image

from emoji_studio.alpha import AccessPolicy, AlphaUser
from emoji_studio.durable_api import create_app
from emoji_studio.service import MockRenderer
from emoji_studio.worker_queue import LeaseLost, WorkerQueue


class ControlledRenderer(MockRenderer):
    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def render(self, prompt, seed):
        self.started.set()
        if not self.release.wait(5):
            raise TimeoutError("test renderer was not released")
        return super().render(prompt, seed)


class DurableApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "durable.sqlite3"
        self.alice = {"Authorization": "Bearer alice-token"}
        self.bob = {"Authorization": "Bearer bob-token"}
        self.admin = {"Authorization": "Bearer admin-token"}

    def app(self, **kwargs):
        users = [
            AlphaUser(
                name,
                hashlib.sha256((name + "-token").encode()).hexdigest(),
                2 if name != "admin" else 100,
                120,
                name == "admin",
            )
            for name in ("alice", "bob", "admin")
        ]
        settings = {
            "renderer": MockRenderer(),
            "access_policy": AccessPolicy(users),
            "trial_image_cap": 4,
            "poll_seconds": 0.01,
            "idle_unload_seconds": 0.05,
        }
        settings.update(kwargs)
        return create_app(self.path, **settings)

    def submit(self, client, **payload):
        response = client.post(
            "/v1/generations",
            headers={**self.alice, "X-Request-ID": "test:request"},
            json={"prompt": "apple", "seed": 7, **payload},
        )
        self.assertEqual(response.status_code, 202, response.text)
        return response.json()

    def wait(self, client, job_id, headers=None):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            response = client.get(f"/v1/generations/{job_id}", headers=headers or self.alice)
            self.assertEqual(response.status_code, 200)
            if response.json()["status"] in ("succeeded", "failed"):
                return response.json()
            time.sleep(0.01)
        self.fail("Job did not finish")

    def test_authenticated_pack_export_feedback_and_delete(self):
        app = self.app()
        with TestClient(app) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertEqual(client.get("/v1/me").status_code, 401)
            self.assertEqual(client.post("/v1/generations", json={"prompt": "a"}).status_code, 401)
            created = self.submit(client, variations=2)
            job = self.wait(client, created["id"])
            self.assertEqual(job["status"], "succeeded", job)
            self.assertEqual(job["request_id"], "test:request")
            self.assertEqual(job["seeds"], [7, 8])
            self.assertEqual(len(job["results"]), 2)
            self.assertIn("finished_at", job)
            self.assertNotIn("token", job)
            for result in job["results"]:
                for extension in ("png", "webp"):
                    response = client.get(result[f"{extension}_url"], headers=self.alice)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["content-type"], f"image/{extension}")
                    with Image.open(io.BytesIO(response.content)) as image:
                        self.assertEqual(image.size, (512, 512))
                        self.assertEqual(image.mode, "RGBA")
                        self.assertEqual(image.getpixel((0, 0))[3], 0)
            path = f"/v1/generations/{job['id']}"
            for target in (path, job["results"][0]["png_url"]):
                self.assertEqual(client.get(target, headers=self.bob).status_code, 404)
            self.assertEqual(client.get("/v1/generations", headers=self.bob).json(), {"jobs": []})
            feedback = client.post(
                path + "/feedback", headers=self.alice, json={"rating": "up", "comment": " useful "}
            )
            self.assertEqual(feedback.status_code, 201)
            self.assertEqual(feedback.json()["comment"], "useful")
            self.assertEqual(
                client.post(
                    path + "/feedback", headers=self.bob, json={"rating": "down"}
                ).status_code,
                404,
            )
            with sqlite3.connect(self.path) as connection:
                self.assertEqual(
                    connection.execute("SELECT comment FROM feedback").fetchone()[0], "useful"
                )
            self.assertEqual(client.get("/metrics", headers=self.alice).status_code, 403)
            self.assertIn(
                "emoji_studio_images_generated_total",
                client.get("/metrics", headers=self.admin).text,
            )
            self.assertEqual(client.delete(path, headers=self.bob).status_code, 404)
            self.assertEqual(client.delete(path, headers=self.alice).status_code, 204)
            self.assertEqual(client.get(path, headers=self.alice).status_code, 404)
            self.assertEqual(
                client.get("/v1/me", headers=self.alice).json()["quota"]["remaining"], 0
            )
            with sqlite3.connect(self.path) as connection:
                self.assertEqual(
                    connection.execute("SELECT COUNT(*) FROM feedback").fetchone()[0], 0
                )

    def test_keyed_random_seed_pack_replays_after_restart_at_full_quota(self):
        headers = {**self.alice, "Idempotency-Key": "pack:1", "X-Request-ID": "first"}
        payload = {"prompt": " apple ", "variations": 2}
        with TestClient(self.app(worker_enabled=False, trial_image_cap=2)) as client:
            first = client.post("/v1/generations", headers=headers, json=payload)
            self.assertEqual(first.status_code, 202)
        with TestClient(self.app(worker_enabled=False, trial_image_cap=2)) as client:
            response = client.post(
                "/v1/generations", headers={**headers, "X-Request-ID": "retry"},
                json={"prompts": ["apple", "apple"], "seed": None},
            )
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), first.json())
            self.assertEqual(response.headers["X-Request-ID"], "retry")
            self.assertEqual(response.json()["request_id"], "first")
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 2)
            self.assertNotIn("pack:1", response.text)

    def test_key_conflicts_and_owner_scope(self):
        headers = {**self.alice, "Idempotency-Key": "shared"}
        with TestClient(self.app(worker_enabled=False)) as client:
            first = client.post("/v1/generations", headers=headers, json={"prompt": "apple"})
            for changed in ({"prompt": "pear"}, {"prompt": "apple", "seed": 7},
                            {"prompt": "apple", "variations": 2}):
                with self.subTest(changed=changed):
                    self.assertEqual(client.post(
                        "/v1/generations", headers=headers, json=changed,
                    ).status_code, 409)
            other = client.post("/v1/generations",
                                headers={**self.bob, "Idempotency-Key": "shared"},
                                json={"prompt": "apple"})
            self.assertEqual(other.status_code, 202)
            self.assertNotEqual(other.json()["id"], first.json()["id"])
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 2)

    def test_keyed_concurrent_submissions_admit_one_job_and_metric(self):
        app = self.app(worker_enabled=False, trial_image_cap=1)
        with TestClient(app) as client, patch.object(app.state.metrics, "record_job") as metric:
            def submit(_):
                return client.post("/v1/generations",
                                   headers={**self.alice, "Idempotency-Key": "race"},
                                   json={"prompt": "apple"})
            with ThreadPoolExecutor(max_workers=8) as pool:
                results = list(pool.map(submit, range(8)))
            self.assertEqual({r.status_code for r in results}, {202})
            self.assertEqual(len({r.json()["id"] for r in results}), 1)
            self.assertEqual(len({tuple(r.json()["seeds"]) for r in results}), 1)
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 1)
            metric.assert_called_once_with("queued")

    def test_keyed_failed_and_deleted_job_never_readmits(self):
        headers = {**self.alice, "Idempotency-Key": "failed"}
        app = self.app(worker_enabled=False)
        with TestClient(app) as client:
            first = client.post("/v1/generations", headers=headers, json={"prompt": "a"}).json()
            lease = app.state.store.claim("test")
            app.state.store.fail(lease)
            replay = client.post("/v1/generations", headers=headers, json={"prompt": "a"})
            self.assertEqual(replay.status_code, 202)
            self.assertEqual(replay.json()["status"], "failed")
            self.assertEqual(replay.json()["id"], first["id"])
            self.assertEqual(client.delete(
                "/v1/generations/" + first["id"], headers=self.alice,
            ).status_code, 204)
        with TestClient(self.app(worker_enabled=False)) as client:
            self.assertEqual(client.post(
                "/v1/generations", headers=headers, json={"prompt": "a"},
            ).status_code, 409)
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 1)

    def test_bad_or_duplicate_key_rejected_without_usage(self):
        with TestClient(self.app(worker_enabled=False)) as client:
            for key in ("", "a b", "a,b", "a" * 129):
                with self.subTest(key=key):
                    self.assertEqual(client.post(
                        "/v1/generations", headers={**self.alice, "Idempotency-Key": key},
                        json={"prompt": "a"},
                    ).status_code, 422)
            response = client.post(
                "/v1/generations", headers=[*self.alice.items(),
                                           ("Idempotency-Key", "a"), ("Idempotency-Key", "b")],
                json={"prompt": "a"},
            )
            self.assertEqual(response.status_code, 422)
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 0)

    def test_key_retries_still_require_auth_and_obey_request_rate(self):
        headers = {**self.alice, "Idempotency-Key": "retry"}
        app = self.app(worker_enabled=False)
        with TestClient(app) as client:
            first = client.post("/v1/generations", headers=headers, json={"prompt": "a"})
            self.assertEqual(first.status_code, 202)
            self.assertEqual(client.post(
                "/v1/generations", headers={"Idempotency-Key": "retry"}, json={"prompt": "a"},
            ).status_code, 401)
            with patch.object(app.state.access_policy, "allow_request", return_value=(False, 9)):
                response = client.post("/v1/generations", headers=headers, json={"prompt": "a"})
                self.assertEqual(response.status_code, 429)
                self.assertEqual(response.headers["Retry-After"], "9")

    def test_retry_after_commit_but_lost_response_does_not_render_twice(self):
        app = self.app(worker_enabled=False)
        enqueue = app.state.store.enqueue
        headers = {**self.alice, "Idempotency-Key": "lost-response"}

        def commit_then_fail(*args, **kwargs):
            enqueue(*args, **kwargs)
            raise sqlite3.OperationalError("simulated failure after commit")

        with TestClient(app) as client:
            with patch.object(app.state.store, "enqueue", side_effect=commit_then_fail):
                self.assertEqual(client.post(
                    "/v1/generations", headers=headers, json={"prompt": "a"},
                ).status_code, 503)
            lease = app.state.store.claim("worker")
            replay = client.post("/v1/generations", headers=headers, json={"prompt": "a"})
            self.assertEqual(replay.status_code, 202)
            self.assertEqual(replay.json()["id"], lease.job_id)
            self.assertEqual(replay.json()["status"], "running")
            self.assertEqual(replay.json()["seeds"], lease.payload["seeds"])
            app.state.store.fail(lease)
            self.assertIsNone(app.state.store.claim("worker"))
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 1)

    def test_no_key_and_same_request_id_still_create_distinct_jobs(self):
        with TestClient(self.app(worker_enabled=False)) as client:
            first, second = self.submit(client), self.submit(client)
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(first["request_id"], second["request_id"])
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 2)

    def test_quota_and_restart_after_deleted_output(self):
        with TestClient(self.app()) as client:
            job = self.wait(client, self.submit(client, variations=2)["id"])
            client.delete(f"/v1/generations/{job['id']}", headers=self.alice)
        with TestClient(self.app()) as client:
            response = client.post("/v1/generations", headers=self.alice, json={"prompt": "new"})
            self.assertEqual(response.status_code, 429)
            self.assertIn("retry-after", response.headers)
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["trial"]["used"], 2)
            response = client.post(
                "/v1/generations", headers=self.admin, json={"prompts": ["a", "b", "c"]}
            )
            self.assertEqual(response.status_code, 429)
            self.assertIn("Private-alpha", response.json()["detail"])

    def test_queued_jobs_resume_after_api_restart(self):
        with TestClient(self.app(worker_enabled=False)) as client:
            job = self.submit(client)
            self.assertEqual(job["status"], "queued")
            path = f"/v1/generations/{job['id']}"
            self.assertEqual(
                client.post(
                    path + "/feedback", headers=self.alice, json={"rating": "up"}
                ).status_code,
                409,
            )
            self.assertEqual(client.delete(path, headers=self.alice).status_code, 409)
        with TestClient(self.app()) as client:
            done = self.wait(client, job["id"])
            self.assertEqual(done["status"], "succeeded")
            self.assertEqual(done["request_id"], "test:request")
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 1)

    def test_crashed_worker_lease_recovers_without_recharging(self):
        with TestClient(self.app(worker_enabled=False)) as client:
            job = self.submit(client)
        old_store = WorkerQueue(self.path, clock=lambda: time.time() - 120)
        old_lease = old_store.claim("crashed-worker", ttl=1)
        with TestClient(self.app()) as client:
            self.assertEqual(self.wait(client, job["id"])["status"], "succeeded")
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 1)
        with self.assertRaises(LeaseLost):
            old_store.heartbeat(old_lease)

    def test_live_lease_is_not_stolen_on_api_start(self):
        with TestClient(self.app(worker_enabled=False)) as client:
            job = self.submit(client)
        owner = WorkerQueue(self.path)
        lease = owner.claim("other-live-worker", ttl=60)
        with TestClient(self.app()) as client:
            response = client.get(f"/v1/generations/{job['id']}", headers=self.alice)
            self.assertEqual(response.json()["status"], "running")
            self.assertEqual(owner.heartbeat(lease, ttl=60) > time.time(), True)
            owner.fail(lease, retryable=True)
            self.assertEqual(self.wait(client, job["id"])["status"], "succeeded")

    def test_heartbeat_renews_while_renderer_is_busy(self):
        renderer = ControlledRenderer()
        self.addCleanup(renderer.release.set)
        with TestClient(self.app(renderer=renderer, lease_seconds=1)) as client:
            job = self.submit(client)
            self.assertTrue(renderer.started.wait(2))
            time.sleep(1.2)
            self.assertIsNone(WorkerQueue(self.path).claim("competing-worker"))
            renderer.release.set()
            self.assertEqual(self.wait(client, job["id"])["status"], "succeeded")

    def test_fenced_worker_cannot_publish_late_render(self):
        renderer = ControlledRenderer()
        self.addCleanup(renderer.release.set)
        with TestClient(self.app(renderer=renderer)) as client:
            job = self.submit(client)
            self.assertTrue(renderer.started.wait(2))
            store = WorkerQueue(self.path, clock=lambda: time.time() + 1000)
            replacement = store.claim("replacement-worker")
            store.fail(replacement, error="replacement intentionally failed")
            renderer.release.set()
            self.assertEqual(self.wait(client, job["id"])["status"], "failed")
        record = WorkerQueue(self.path).get(job["id"], "alice")
        self.assertEqual(record["artifacts"], {})
        self.assertEqual(record["error"], "replacement intentionally failed")

    def test_renderer_error_is_sanitized_and_quota_kept(self):
        class BrokenRenderer(MockRenderer):
            def render(self, prompt, seed):
                raise RuntimeError("secret must not appear in public state")

        with TestClient(self.app(renderer=BrokenRenderer())) as client:
            job = self.wait(client, self.submit(client)["id"])
            self.assertEqual(job["status"], "failed")
            self.assertNotIn("secret", job["error"])
            self.assertEqual(job["results"], [])
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 1)

    def test_concurrent_http_admissions_are_atomic(self):
        with TestClient(self.app(worker_enabled=False)) as client:

            def submit(index):
                return client.post(
                    "/v1/generations", headers=self.alice, json={"prompt": "a", "seed": index}
                ).status_code

            with ThreadPoolExecutor(max_workers=4) as pool:
                statuses = list(pool.map(submit, range(8)))
            self.assertEqual(statuses.count(202), 2)
            self.assertEqual(statuses.count(429), 6)
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 2)

    def test_retention_deletes_terminal_content_not_active_or_usage(self):
        app = self.app(worker_enabled=False)
        with TestClient(app) as client:
            first = self.submit(client)
            second = self.submit(client)
            store = app.state.store
            lease = store.claim("fake")
            store.fail(lease)
            with sqlite3.connect(self.path) as connection:
                connection.execute("UPDATE jobs SET finished=? WHERE id=?", (0, lease.job_id))
            removed = app.state.retention.cleanup()
            self.assertEqual(removed, [lease.job_id])
            active_id = second["id"] if lease.job_id == first["id"] else first["id"]
            self.assertIsNotNone(store.get(active_id, "alice"))
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 2)

    def test_validation_rate_limit_and_storage_error(self):
        app = self.app(worker_enabled=False)
        with TestClient(app) as client:
            self.assertEqual(
                client.post(
                    "/v1/generations", headers=self.alice, json={"prompt": " "}
                ).status_code,
                422,
            )
            self.assertEqual(
                client.get("/v1/generations?limit=0", headers=self.alice).status_code, 422
            )
            with patch.object(app.state.access_policy, "allow_request", return_value=(False, 12)):
                limited = client.post("/v1/generations", headers=self.alice, json={"prompt": "a"})
                self.assertEqual(limited.status_code, 429)
                self.assertEqual(limited.headers["retry-after"], "12")
            with patch.object(
                app.state.store, "enqueue", side_effect=sqlite3.OperationalError("private path")
            ):
                failed = client.post("/v1/generations", headers=self.alice, json={"prompt": "a"})
                self.assertEqual(failed.status_code, 503)
                self.assertNotIn("private path", failed.text)

    def test_default_factory_unchanged_and_schema_v2_requires_migration(self):
        from emoji_studio.api import create_app as old_factory
        from emoji_studio.service import JobStore

        legacy = old_factory(root=self.temp.name, api_key="legacy", renderer=MockRenderer())
        self.assertIsInstance(legacy.state.store, JobStore)
        WorkerQueue(self.path)
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(ValueError, "schema"):
            self.app(trial_image_cap=100)

    def test_deterministic_exports_persist_across_restart(self):
        with TestClient(self.app()) as client:
            first = self.wait(client, self.submit(client)["id"])
            original = {
                extension: client.get(
                    first["results"][0][f"{extension}_url"], headers=self.alice
                ).content
                for extension in ("png", "webp")
            }
        with TestClient(self.app()) as client:
            saved = client.get(f"/v1/generations/{first['id']}", headers=self.alice).json()
            self.assertEqual(saved, first)
            second = self.wait(client, self.submit(client)["id"])
            for extension in ("png", "webp"):
                self.assertEqual(
                    client.get(
                        second["results"][0][f"{extension}_url"], headers=self.alice
                    ).content,
                    original[extension],
                )

    def test_bad_second_image_never_exposes_partial_pack(self):
        class BadSecond(MockRenderer):
            def render(self, prompt, seed):
                if seed == 8:
                    raise ValueError("second image failed")
                return super().render(prompt, seed)

        app = self.app(renderer=BadSecond())
        with TestClient(app) as client:
            job = self.wait(client, self.submit(client, variations=2)["id"])
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["results"], [])
            self.assertEqual(app.state.store.get(job["id"], "alice")["artifacts"], {})
            self.assertEqual(client.get("/v1/me", headers=self.alice).json()["quota"]["used"], 2)

    def test_corrupt_stored_artifact_is_not_served(self):
        with TestClient(self.app()) as client:
            job = self.wait(client, self.submit(client)["id"])
            with sqlite3.connect(self.path) as connection:
                connection.execute("UPDATE artifacts SET content=?", (b"corrupt",))
            response = client.get(job["results"][0]["png_url"], headers=self.alice)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("corrupt", response.text)

    def test_retention_storage_failure_degrades_health_without_killing_task(self):
        app = self.app(worker_enabled=False)
        with patch.object(
            app.state.retention, "cleanup", side_effect=sqlite3.OperationalError("private")
        ):
            with TestClient(app) as client:
                for _ in range(100):
                    if app.state.retention.last_error:
                        break
                    time.sleep(0.01)
                self.assertEqual(client.get("/healthz").json()["status"], "degraded")
                self.assertFalse(app.state.retention.task.done())
