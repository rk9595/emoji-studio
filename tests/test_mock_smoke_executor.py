import hashlib
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock, patch

from emoji_studio.mock_smoke_executor import MockSmokeExecutor, run_smoke
from emoji_studio.render_budget import BudgetDenied, RenderBudget
from emoji_studio.service import MockRenderer
from emoji_studio.worker_queue import LeaseLost, WorkerQueue

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "configs/amd-api-smoke-plan.json"
PAYLOAD = {"prompts": ["a cheerful red apple sticker"], "seeds": [7]}


def crashed_executor(directory, plan_hash, after_publication=False):
    root = Path(directory)
    store = WorkerQueue(root / "jobs.sqlite3", clock=lambda: 100)
    budget = RenderBudget(root / "budget.sqlite3", allocation_id="offline-test", plan_sha256=plan_hash)
    executor = MockSmokeExecutor(store, budget, PLAN)

    if after_publication:
        complete = store.complete

        def publish_then_die(*args, **kwargs):
            complete(*args, **kwargs)
            os._exit(21)

        with patch.object(store, "complete", side_effect=publish_then_die):
            executor.run_next()
        return

    def die(self, prompt, seed):
        (root / "mock-render-entered").write_text("entered")
        os._exit(19)

    with patch.object(MockRenderer, "render", die):
        executor.run_next()


class MockSmokeExecutorTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.now = 100
        self.identity = {"allocation_id": "offline-test",
                         "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest()}
        self.store = WorkerQueue(self.root / "jobs.sqlite3", clock=lambda: self.now, trial_image_cap=2)
        self.budget = RenderBudget.create(self.root / "budget.sqlite3", **self.identity)
        self.executor = MockSmokeExecutor(self.store, self.budget, PLAN)

    def enqueue(self, job="first", **payload):
        data = {**PAYLOAD, **payload}
        return self.store.enqueue(job, "alice", data["prompts"], data["seeds"])

    def reopen(self):
        return MockSmokeExecutor(
            WorkerQueue(self.store.path, clock=lambda: self.now),
            RenderBudget(self.budget.path, **self.identity), PLAN,
        )

    def test_two_jobs_survive_reopen_and_stop_at_two_calls(self):
        self.enqueue()
        self.assertEqual(self.executor.run_next(), "first")
        first = self.store.get("first", "alice")
        self.assertEqual(first["status"], "succeeded")
        self.assertEqual(len(first["artifacts"]), 2)
        self.enqueue("second")
        self.assertEqual(self.reopen().run_next(), "second")
        self.assertEqual(self.store.get("second", "alice")["artifacts"], first["artifacts"])
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaises(BudgetDenied):
                self.reopen().run_next()
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 2)
        self.assertEqual(self.store.usage("alice")["trial"]["used"], 2)

    def test_empty_queue_does_not_consume_render_budget(self):
        self.assertIsNone(self.executor.run_next())
        self.assertEqual(self.budget.snapshot()["consumed"], 0)

    def test_call_identity_survives_reclaimed_lease(self):
        self.enqueue()
        first = self.store.claim("worker-one", ttl=1)
        identity = self.executor.call_identity(first)
        self.now += 2
        second = self.store.claim("worker-two")
        self.assertNotEqual(first.token, second.token)
        self.assertNotEqual(first.attempt, second.attempt)
        self.assertEqual(self.executor.call_identity(second), identity)
        self.assertEqual(identity[0], "first:0")
        self.assertNotEqual(self.executor.call_identity(replace(second, job_id="other")), identity)

    def test_model_config_and_request_are_bound_to_fingerprint(self):
        self.enqueue()
        lease = self.store.claim("worker")
        original = self.executor.call_identity(lease)
        changed_plan = json.loads(PLAN.read_text())
        changed_plan["serving"]["adapter_sha256"] = "b" * 64
        path = self.root / "changed-plan.json"
        path.write_text(json.dumps(changed_plan))
        changed_budget = RenderBudget.create(self.root / "changed-budget.sqlite3",
                                            allocation_id="offline-test",
                                            plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        changed = MockSmokeExecutor(self.store, changed_budget, path)
        self.assertNotEqual(changed.call_identity(lease)[1], original[1])
        with self.assertRaises(ValueError):
            self.executor.call_identity(replace(lease, payload={**PAYLOAD, "seeds": [8]}))

    def test_publication_failure_halts_before_any_second_render(self):
        self.enqueue()
        self.enqueue("second")
        real_render = MockRenderer.render
        with patch.object(MockRenderer, "render", autospec=True, side_effect=real_render) as render:
            with patch.object(self.store, "complete", side_effect=sqlite3.OperationalError("secret-storage-path")):
                with self.assertRaises(sqlite3.OperationalError):
                    self.executor.run_next()
            with self.assertRaises(BudgetDenied):
                self.reopen().run_next()
            self.assertEqual(render.call_count, 1)
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "failed")
        job = self.store.get("first", "alice")
        self.assertEqual(job["artifacts"], {})
        self.assertNotIn("secret-storage-path", job["error"])
        self.assertEqual(self.store.get("second", "alice")["status"], "queued")

    def test_publication_commit_ack_lost_preserves_output_but_halts(self):
        self.enqueue()
        complete = self.store.complete

        def commit_then_fail(*args, **kwargs):
            complete(*args, **kwargs)
            raise sqlite3.OperationalError("acknowledgement lost")

        with patch.object(self.store, "complete", side_effect=commit_then_fail):
            with self.assertRaises(sqlite3.OperationalError):
                self.executor.run_next()
        self.assertEqual(self.store.get("first", "alice")["status"], "succeeded")
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "failed")
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaises(BudgetDenied):
                self.reopen().run_next()
            render.assert_not_called()

    def test_death_inside_renderer_blocks_even_after_lease_recovery(self):
        self.enqueue()
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=crashed_executor,
                                  args=(self.root, self.identity["plan_sha256"]))
        process.start()
        try:
            process.join(10)
            self.assertEqual(process.exitcode, 19)
        finally:
            if process.is_alive():
                process.kill()
                process.join(3)
        self.assertTrue((self.root / "mock-render-entered").exists())
        self.now = 200
        self.store.recover()
        self.assertEqual(self.store.get("first", "alice")["status"], "queued")
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaises(BudgetDenied):
                self.reopen().run_next()
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 1)

    def test_previously_succeeded_call_is_not_rerendered_if_job_unpublished(self):
        self.enqueue()
        lease = self.store.claim("previous", ttl=1)
        call_id, fingerprint = self.executor.call_identity(lease)
        self.budget.run(call_id, fingerprint, lambda: None)
        self.now += 2
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaisesRegex(BudgetDenied, "publication_not_reconciled"):
                self.reopen().run_next()
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 1)

    def test_crash_after_publication_before_budget_completion_blocks(self):
        self.enqueue()
        process = multiprocessing.get_context("spawn").Process(
            target=crashed_executor, args=(self.root, self.identity["plan_sha256"], True),
        )
        process.start()
        try:
            process.join(10)
            self.assertEqual(process.exitcode, 21)
        finally:
            if process.is_alive():
                process.kill()
                process.join(3)
        self.assertEqual(self.store.get("first", "alice")["status"], "succeeded")
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "reserved")
        self.enqueue("second")
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaises(BudgetDenied):
                self.reopen().run_next()
            render.assert_not_called()

    def test_deleted_publication_blocks_remaining_allowance(self):
        self.enqueue()
        self.executor.run_next()
        self.store.delete("first", "alice")
        self.enqueue("second")
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaisesRegex(BudgetDenied, "publication_not_reconciled"):
                self.reopen().run_next()
            render.assert_not_called()
        self.assertEqual(self.store.get("second", "alice")["status"], "queued")

    def test_unguarded_publication_blocks_new_render(self):
        from emoji_studio.durable_worker import render_pack

        self.enqueue()
        lease = self.store.claim("unguarded")
        outputs, results = render_pack(MockRenderer(), lease)
        self.store.complete(lease, outputs, {key: hashlib.sha256(value).hexdigest()
                                            for key, value in outputs.items()}, results=results)
        self.enqueue("second")
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaisesRegex(BudgetDenied, "without_render_reservation"):
                self.reopen().run_next()
            render.assert_not_called()

    def test_bad_render_and_export_validation_failure_consume_and_halt(self):
        self.enqueue()
        with patch.object(MockRenderer, "render", return_value=(None, {})):
            with self.assertRaises(ValueError):
                self.executor.run_next()
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "failed")
        self.assertEqual(self.store.get("first", "alice")["artifacts"], {})
        with self.assertRaises(BudgetDenied):
            self.reopen().run_next()

    def test_lease_expires_during_render_cannot_publish_or_retry(self):
        self.enqueue()
        real_render = MockRenderer.render

        def expire(renderer, prompt, seed):
            result = real_render(renderer, prompt, seed)
            self.now += 100
            return result

        with patch.object(MockRenderer, "render", expire):
            with self.assertRaises(LeaseLost):
                self.executor.run_next()
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "failed")
        self.store.recover()
        with self.assertRaises(BudgetDenied):
            self.reopen().run_next()
        self.assertEqual(self.store.get("first", "alice")["artifacts"], {})

    def test_pack_or_wrong_request_rejected_without_render(self):
        self.enqueue(prompts=["a", "b"], seeds=[7, 8])
        with patch.object(MockRenderer, "render") as render:
            with self.assertRaises(ValueError):
                self.executor.run_next()
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 0)

    def test_renderer_cannot_be_supplied_and_default_worker_not_modified(self):
        with self.assertRaises(TypeError):
            MockSmokeExecutor(self.store, self.budget, PLAN, renderer=Mock())
        from emoji_studio.durable_api import create_app
        app = create_app(self.root / "default.sqlite3", api_key="temporary-test",
                         renderer=MockRenderer())
        self.assertEqual(type(app.state.worker).__name__, "DurableWorker")

    def test_wrong_plan_and_trial_cap_rejected_before_claim(self):
        self.enqueue()
        path = self.root / "changed-plan.json"
        path.write_bytes(PLAN.read_bytes() + b"\n")
        with self.assertRaises(ValueError):
            MockSmokeExecutor(self.store, self.budget, path)
        other = WorkerQueue(self.root / "other.sqlite3", trial_image_cap=3)
        with self.assertRaises(ValueError):
            MockSmokeExecutor(other, self.budget, PLAN)
        self.assertEqual(self.store.get("first", "alice")["status"], "queued")

    def test_authorized_plan_is_not_a_switch_to_real_rendering(self):
        plan = json.loads(PLAN.read_text())
        plan["execution_authorized"] = True
        path = self.root / "authorized.json"
        path.write_text(json.dumps(plan))
        budget = RenderBudget.create(self.root / "authorized.sqlite3", allocation_id="offline-test",
                                     plan_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaises(ValueError):
            MockSmokeExecutor(self.store, budget, path)

    def test_api_reopen_replay_and_export_smoke(self):
        receipt = run_smoke()
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["render_calls_consumed"], 2)
        self.assertTrue(receipt["third_call_denied"])
        self.assertTrue(receipt["temporary_data_removed"])
        self.assertFalse(receipt["execution_authorized"])
        self.assertEqual(receipt["gpu_allocations"], 0)
