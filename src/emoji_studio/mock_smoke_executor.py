"""Dedicated mock-only smoke executor. No real renderer selection or provisioning."""

import hashlib
import json
import secrets
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from .durable_worker import render_pack
from .render_budget import BudgetDenied, RenderBudget
from .service import MockRenderer


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def require(condition):
    if not condition:
        raise RuntimeError("Mock smoke verification failed")


def read_plan(path, expected_hash):
    raw = Path(path).read_bytes()
    if digest(raw) != expected_hash:
        raise ValueError("Mock executor plan checksum differs")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate plan key")
            result[key] = value
        return result

    plan = json.loads(raw, object_pairs_hook=unique)
    if (plan["plan_id"] != "amd-api-smoke-v1" or plan["status"] != "prepared_only"
            or plan["execution_authorized"] is not False
            or plan["approved_allowance_usd"] is not None
            or canonical(plan["requests"]) != canonical([
                {"prompt": "a cheerful red apple sticker", "seed": 7},
                {"prompt": "a cheerful red apple sticker", "seed": 7},
            ])
            or type(plan["proposed_limits"]["physical_render_calls"]) is not int
            or plan["proposed_limits"]["physical_render_calls"] != 2):
        raise ValueError("Only the prepared-only two-image mock proposal is supported")
    return plan


class MockSmokeExecutor:
    """Use with the dedicated durable API's worker disabled and a trial cap of 2.

    The constructor cannot receive a renderer/factory. Each callback constructs
    MockRenderer internally; the default API and DurableWorker remain unchanged.
    No lease token/attempt number participates in the stable call identity.
    """

    def __init__(self, store, budget, plan_path):
        self.store, self.budget = store, budget
        plan = read_plan(plan_path, budget.snapshot()["plan_sha256"])
        if store.usage("mock-smoke-policy-check")["trial"]["limit"] != 2:
            raise ValueError("Dedicated mock smoke requires a persisted two-image trial cap")
        self.expected_payload = {
            "prompts": [plan["requests"][0]["prompt"]], "seeds": [plan["requests"][0]["seed"]],
        }
        self.model_identity = canonical({
            "actual_renderer": "MockRenderer", "mock_contract": "mock-smoke-v1",
            "planned_serving": plan["serving"],
            "serving_config_sha256": plan["source_sha256"]["configs/serving.json"],
        })

    def call_identity(self, lease):
        # Exactly one image per smoke job. A different lease/attempt must never
        # change this identity or hide a previously consumed physical call.
        if canonical(lease.payload) != canonical(self.expected_payload):
            raise ValueError("Job differs from the single-image smoke request")
        call_id = f"{lease.job_id}:0"
        fingerprint = digest(canonical({
            "version": 1, "job_id": lease.job_id, "image_index": 0,
            "prompt": lease.payload["prompts"][0], "seed": lease.payload["seeds"][0],
            "model_identity": json.loads(self.model_identity),
        }))
        return call_id, fingerprint

    def _render_and_publish(self, lease):
        # Keep publication inside the reserved budget interval. If rendering
        # succeeds but publication fails (or its acknowledgement is lost), the
        # ledger stays failed/reserved and stops the entire smoke after restart.
        self.store.heartbeat(lease, ttl=60)
        renderer = MockRenderer()
        try:
            outputs, results = render_pack(renderer, lease)
            hashes = {name: digest(content) for name, content in outputs.items()}
            self.store.complete(lease, outputs, hashes, results=results)
            return lease.job_id
        finally:
            renderer.unload()

    def _reconcile_publications(self, snapshot):
        # Trusted local control-plane read, never exposed as an ownerless API.
        # Fail closed on a lost/deleted publication or an unguarded worker's
        # completed job, rather than spending the remaining call on a new job.
        with self.store._transaction() as connection:
            rows = {row["id"]: row for row in connection.execute("SELECT id,payload,status FROM jobs")}
        consumed = {call["call_id"]: call for call in snapshot["calls"]}
        for call in snapshot["calls"]:
            job_id, separator, index = call["call_id"].rpartition(":")
            row = rows.get(job_id)
            if not separator or index != "0" or row is None or row["status"] != "succeeded":
                raise BudgetDenied("render_publication_not_reconciled")
            identity = self.call_identity(SimpleNamespace(job_id=job_id, payload=json.loads(row["payload"])))
            if identity != (call["call_id"], call["request_sha256"]):
                raise BudgetDenied("published_request_identity_differs")
        if any(row["status"] == "succeeded" and f"{row['id']}:0" not in consumed for row in rows.values()):
            raise BudgetDenied("publication_without_render_reservation")

    def run_next(self):
        snapshot = self.budget.snapshot()
        if snapshot["further_calls_blocked"]:
            raise BudgetDenied("mock_smoke_stopped_or_exhausted")
        self._reconcile_publications(snapshot)
        lease = self.store.claim("mock-smoke-executor", ttl=60)
        if lease is None:
            return None
        try:
            call_id, fingerprint = self.call_identity(lease)
            return self.budget.run(call_id, fingerprint, lambda: self._render_and_publish(lease))
        except BaseException:
            try:
                self.store.fail(lease, error="Mock smoke stopped; inspect private execution state")
            except Exception:
                # May already be terminal or have lost its lease/DB. Never rerender.
                pass
            raise


def run_smoke():
    """Disposable API integration; no persistent DB, remote endpoint or GPU option."""
    from fastapi.testclient import TestClient

    from .durable_api import create_app

    root = Path(__file__).resolve().parents[2]
    plan_path = root / "configs/amd-api-smoke-plan.json"
    plan_hash = digest(plan_path.read_bytes())
    identity = {"allocation_id": "offline-mock-executor", "plan_sha256": plan_hash}
    headers = {"Authorization": "Bearer " + secrets.token_urlsafe(32)}
    exports = []
    job_ids = []
    with tempfile.TemporaryDirectory(prefix="emoji-mock-executor-") as temporary:
        directory = Path(temporary).resolve()
        budget_path = directory / "budget.sqlite3"
        RenderBudget.create(budget_path, **identity)
        # Two independent app/executor instances reopen the same temporary files.
        for number in range(2):
            app = create_app(directory / "jobs.sqlite3", renderer=MockRenderer(),
                             api_key=headers["Authorization"][7:], trial_image_cap=2,
                             worker_enabled=False)
            executor = MockSmokeExecutor(app.state.store, RenderBudget(budget_path, **identity), plan_path)
            with TestClient(app) as client:
                if job_ids:
                    require(client.get("/v1/generations/" + job_ids[0], headers=headers).json()["status"] == "succeeded")
                response = client.post("/v1/generations", headers={**headers, "Idempotency-Key": f"image-{number}"},
                                       json={"prompt": "a cheerful red apple sticker", "seed": 7})
                require(response.status_code == 202)
                job_id = response.json()["id"]
                require(executor.run_next() == job_id)
                job_ids.append(job_id)
                job = client.get("/v1/generations/" + job_id, headers=headers).json()
                require(job["status"] == "succeeded")
                hashes = {}
                for extension in ("png", "webp"):
                    artifact = client.get(job["results"][0][f"{extension}_url"], headers=headers)
                    require(artifact.status_code == 200)
                    hashes[extension] = digest(artifact.content)
                exports.append(hashes)
                replay = client.post("/v1/generations", headers={**headers, "Idempotency-Key": f"image-{number}"},
                                     json={"prompt": "a cheerful red apple sticker", "seed": 7})
                require(replay.status_code == 202 and replay.json()["id"] == job_id)
                if number == 1:
                    rejected = client.post("/v1/generations", headers=headers,
                                           json={"prompt": "a cheerful red apple sticker", "seed": 7})
                    require(rejected.status_code == 429)
        snapshot = RenderBudget(budget_path, **identity).snapshot()
        require(snapshot["consumed"] == 2 and snapshot["further_calls_blocked"])
        require([call["call_id"] for call in snapshot["calls"]] == [f"{job}:0" for job in job_ids])
        require(all(call["state"] == "succeeded" for call in snapshot["calls"]))
        require(exports[0] == exports[1])
        try:
            executor.run_next()
        except BudgetDenied:
            pass
        else:
            raise RuntimeError("Third call was not denied")
    return {"status": "passed", "renderer": "MockRenderer", "gpu_allocations": 0,
            "execution_authorized": False, "jobs_published": 2, "render_calls_consumed": 2,
            "third_call_denied": True, "restart_and_api_replay_verified": True,
            "export_hashes_match": True, "temporary_data_removed": not directory.exists(),
            "source_sha256": {name: digest((Path(__file__).parent / name).read_bytes())
                              for name in ("mock_smoke_executor.py", "render_budget.py",
                                           "durable_worker.py", "worker_queue.py")}}


def main():
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python -m emoji_studio.mock_smoke_executor")
    try:
        print(json.dumps(run_smoke(), indent=2, sort_keys=True))
    except Exception as error:
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
