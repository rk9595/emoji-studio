import hashlib
import io
import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from emoji_studio.alpha import AccessPolicy, AlphaUser
from emoji_studio.api import create_app
from emoji_studio.service import (
    FluxRenderer,
    JobStore,
    MockRenderer,
    RetentionManager,
    VastServerlessRenderer,
    create_seeds,
    make_sticker,
)

PROJECT = Path(__file__).resolve().parents[1]


class StickerTest(unittest.TestCase):
    def test_flat_background_becomes_transparent_and_subject_is_retained(self):
        image = Image.new("RGB", (200, 160), "white")
        ImageDraw.Draw(image).ellipse((50, 30, 150, 130), fill=(220, 30, 60))
        sticker = make_sticker(image, size=128)
        self.assertEqual(sticker.mode, "RGBA")
        self.assertEqual(sticker.size, (128, 128))
        self.assertEqual(sticker.getpixel((0, 0))[3], 0)
        self.assertGreater(sticker.getchannel("A").getbbox()[2], 64)

    def test_empty_background_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "no foreground"):
            make_sticker(Image.new("RGB", (64, 64), "white"))


class ServiceUtilityTest(unittest.TestCase):
    def test_selected_serving_adapter_exists_and_matches_lock(self):
        renderer = FluxRenderer(PROJECT, PROJECT / "configs/serving.json")
        self.assertFalse(renderer.loaded)
        self.assertEqual(renderer.config["selected_step"], 25)
        self.assertEqual(renderer.adapter.name, "step-25.safetensors")

    def test_explicit_seed_sequence_is_reproducible_and_wraps(self):
        self.assertEqual(create_seeds(3, 42), [42, 43, 44])
        self.assertEqual(create_seeds(2, 2**32 - 1), [2**32 - 1, 0])

    def test_running_jobs_are_requeued_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            job = store.create(["apple"], [7], "request")
            store.update(job["id"], status="running")
            self.assertEqual(store.pending_ids(), [job["id"]])
            self.assertEqual(store.get(job["id"])["status"], "queued")

    def test_retention_deletes_terminal_job_but_not_active_job(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(directory)
            expired = store.create(["apple"], [7], "expired")
            active = store.create(["pear"], [8], "active")
            store.update(expired["id"], status="succeeded", finished_at="2020-01-01T00:00:00+00:00")
            store.update(active["id"], status="running", finished_at="2020-01-01T00:00:00+00:00")
            deleted = RetentionManager(store, retention_days=7).cleanup()
            self.assertEqual(deleted, [expired["id"]])
            self.assertIsNone(store.get(expired["id"]))
            self.assertIsNotNone(store.get(active["id"]))

    def test_serverless_renderer_resolves_once_and_decodes_png(self):
        class FakeDeployment:
            def __init__(self):
                self.ready_calls = 0

            def ensure_ready(self):
                self.ready_calls += 1

        async def remote_render(prompt, seed):
            image = Image.new("RGB", (32, 32), (seed, 10, 20))
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            return {
                "png": buffer.getvalue(),
                "generation_seconds": 1.25,
                "peak_vram_bytes": 123,
                "renderer": "fake-serverless",
            }

        deployment = FakeDeployment()
        renderer = VastServerlessRenderer(deployment, remote_render)
        first, metrics = renderer.render("apple", 7)
        second, _ = renderer.render("pear", 8)
        self.assertEqual(deployment.ready_calls, 1)
        self.assertEqual(first.getpixel((0, 0)), (7, 10, 20))
        self.assertEqual(second.getpixel((0, 0)), (8, 10, 20))
        self.assertEqual(metrics["renderer"], "fake-serverless")
        renderer.unload()
        self.assertFalse(renderer.loaded)


class ApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        app = create_app(
            root=Path(self.temp.name),
            api_key="test-secret",
            renderer=MockRenderer(),
            jobs_dir=Path(self.temp.name) / "jobs",
            hourly_cost_dollars=0.5,
            idle_unload_seconds=0.05,
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)
        self.headers = {"Authorization": "Bearer test-secret"}

    def wait_for_job(self, job_id):
        for _ in range(100):
            response = self.client.get(f"/v1/generations/{job_id}", headers=self.headers)
            if response.json()["status"] in {"succeeded", "failed"}:
                return response
            time.sleep(0.01)
        self.fail("Generation job did not finish")

    def test_auth_queue_poll_export_and_metrics(self):
        self.assertEqual(
            self.client.post("/v1/generations", json={"prompt": "apple"}).status_code, 401
        )
        response = self.client.post(
            "/v1/generations",
            headers={**self.headers, "X-Request-ID": "client-request-7"},
            json={"prompt": "a smiling apple", "variations": 2, "seed": 9},
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.headers["x-request-id"], "client-request-7")
        self.assertEqual(response.json()["seeds"], [9, 10])
        complete = self.wait_for_job(response.json()["id"])
        self.assertEqual(complete.json()["status"], "succeeded")
        self.assertEqual(len(complete.json()["results"]), 2)
        result = complete.json()["results"][0]
        artifact = self.client.get(result["png_url"], headers=self.headers)
        self.assertEqual(artifact.status_code, 200)
        self.assertEqual(artifact.headers["content-type"], "image/png")
        metrics = self.client.get("/metrics", headers=self.headers).text
        self.assertIn('emoji_studio_jobs_total{status="succeeded"} 1', metrics)
        self.assertIn('emoji_studio_images_generated_total{status="ok"} 2', metrics)

    def test_pack_validation_and_not_found(self):
        invalid = self.client.post(
            "/v1/generations",
            headers=self.headers,
            json={"prompts": ["apple", "pear"], "variations": 2},
        )
        self.assertEqual(invalid.status_code, 422)
        missing = self.client.get("/v1/generations/notfound", headers=self.headers)
        self.assertEqual(missing.status_code, 404)

    def test_health_and_studio_are_public(self):
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Emoji Studio", page.text)


class AlphaApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        users = [
            AlphaUser(
                id="tester-one",
                token_sha256=hashlib.sha256(b"token-one").hexdigest(),
                daily_image_quota=2,
                requests_per_minute=4,
                admin=False,
            ),
            AlphaUser(
                id="tester-two",
                token_sha256=hashlib.sha256(b"token-two").hexdigest(),
                daily_image_quota=3,
                requests_per_minute=1,
                admin=False,
            ),
            AlphaUser(
                id="alpha-admin",
                token_sha256=hashlib.sha256(b"admin-token").hexdigest(),
                daily_image_quota=10,
                requests_per_minute=20,
                admin=True,
            ),
        ]
        self.jobs = Path(self.temp.name) / "jobs"
        app = create_app(
            root=Path(self.temp.name),
            renderer=MockRenderer(),
            jobs_dir=self.jobs,
            access_policy=AccessPolicy(users),
            idle_unload_seconds=0.05,
            retention_interval_seconds=3600,
            trial_image_cap=3,
        )
        self.client_context = TestClient(app)
        self.client = self.client_context.__enter__()
        self.addCleanup(self.client_context.__exit__, None, None, None)
        self.one = {"Authorization": "Bearer token-one"}
        self.two = {"Authorization": "Bearer token-two"}
        self.admin = {"Authorization": "Bearer admin-token"}

    def wait(self, job_id, headers):
        for _ in range(100):
            response = self.client.get(f"/v1/generations/{job_id}", headers=headers)
            if response.json()["status"] in {"succeeded", "failed"}:
                return response.json()
            time.sleep(0.01)
        self.fail("Generation did not finish")

    def test_quota_isolation_feedback_metrics_and_delete(self):
        created = self.client.post(
            "/v1/generations",
            headers=self.one,
            json={"prompt": "apple", "variations": 2, "seed": 4},
        )
        self.assertEqual(created.status_code, 202)
        job = self.wait(created.json()["id"], self.one)
        self.assertEqual(
            self.client.get("/v1/me", headers=self.one).json()["quota"]["remaining"], 0
        )
        self.assertEqual(
            self.client.get("/v1/me", headers=self.one).json()["trial"]["remaining"], 1
        )
        self.assertEqual(
            self.client.post(
                "/v1/generations", headers=self.one, json={"prompt": "another"}
            ).status_code,
            429,
        )

        job_path = f"/v1/generations/{job['id']}"
        self.assertEqual(self.client.get(job_path, headers=self.two).status_code, 404)
        self.assertEqual(
            self.client.get(job["results"][0]["png_url"], headers=self.two).status_code, 404
        )
        feedback = self.client.post(
            job_path + "/feedback",
            headers=self.one,
            json={"rating": "up", "comment": "  useful  "},
        )
        self.assertEqual(feedback.status_code, 201)
        self.assertEqual(feedback.json()["comment"], "useful")
        self.assertTrue((self.jobs / job["id"] / "feedback.json").is_file())

        self.assertEqual(self.client.get("/metrics", headers=self.one).status_code, 403)
        self.assertEqual(self.client.get("/metrics", headers=self.admin).status_code, 200)
        self.assertEqual(self.client.delete(job_path, headers=self.two).status_code, 404)
        self.assertEqual(self.client.delete(job_path, headers=self.one).status_code, 204)
        self.assertEqual(self.client.get(job_path, headers=self.one).status_code, 404)
        self.assertEqual(
            self.client.get("/v1/me", headers=self.one).json()["quota"]["remaining"], 0
        )

    def test_rate_limit_and_private_history(self):
        first = self.client.post("/v1/generations", headers=self.two, json={"prompt": "apple"})
        self.assertEqual(first.status_code, 202)
        limited = self.client.post("/v1/generations", headers=self.two, json={"prompt": "pear"})
        self.assertEqual(limited.status_code, 429)
        self.assertIn("retry-after", limited.headers)
        history = self.client.get("/v1/generations", headers=self.two).json()["jobs"]
        self.assertEqual([row["id"] for row in history], [first.json()["id"]])

        capped = self.client.post(
            "/v1/generations",
            headers=self.admin,
            json={"prompt": "pack", "variations": 3},
        )
        self.assertEqual(capped.status_code, 429)
        self.assertIn("Private-alpha image cap", capped.json()["detail"])


if __name__ == "__main__":
    unittest.main()
