import importlib.util
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("supervisor", ROOT / "ops/codex_supervisor.py")
supervisor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(supervisor)


class CPUReceiptTest(unittest.TestCase):
    def setUp(self):
        self.queue = {"cloud_run_id": "123", "cloud_repository": "rk9595/emoji-studio",
                      "cloud_run_head": "a" * 40}
        self.receipt = {"headSha": "a" * 40, "status": "completed", "conclusion": "success",
                        "workflowName": "AMD runtime CPU validation", "url": "https://example.invalid"}

    def read(self, receipt):
        with patch.object(supervisor.subprocess, "run", return_value=SimpleNamespace(
            stdout=json.dumps(receipt))) as run:
            state = supervisor.cloud_state({"gh": "gh"}, self.queue)
            self.assertEqual(run.call_args.args[0][:4], ["gh", "run", "view", "123"])
            self.assertEqual(run.call_count, 1)
            self.assertEqual(run.call_args.kwargs["timeout"], 30)
            return state

    def test_completed_receipt_wakes_continuation(self):
        self.assertEqual(self.read(self.receipt)["status"], "completed")

    def test_queued_or_active_receipt_does_not_start_model_work(self):
        for status in ("queued", "in_progress", "waiting"):
            with self.subTest(status=status):
                receipt = {**self.receipt, "status": status, "conclusion": ""}
                self.assertEqual(self.read(receipt)["status"], "running")

    def test_failed_cancelled_and_timed_out_builds_need_review(self):
        for conclusion in ("failure", "cancelled", "timed_out", "skipped"):
            with self.subTest(conclusion=conclusion):
                self.assertEqual(self.read({**self.receipt, "conclusion": conclusion})["status"], "failed")

    def test_old_head_or_wrong_workflow_is_rejected(self):
        for change in ({"headSha": "b" * 40}, {"workflowName": "AMD DevCloud capacity watcher"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read({**self.receipt, **change})

    def test_bad_scope_or_id_never_reaches_cli(self):
        for change in ({"cloud_repository": "rk9595/emoji-studio-ops"},
                       {"cloud_run_id": "--help"}, {"cloud_run_head": None}):
            with self.subTest(change=change), patch.object(supervisor.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    supervisor.cloud_state({"gh": "gh"}, {**self.queue, **change})
                run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
