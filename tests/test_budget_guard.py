import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("budget_guard", ROOT / "scripts/vast_train.py")
guard_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard_module)


class BudgetGuardTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name) / "allocation.json"
        self.state = {"deadline_epoch": 100, "credit_before": 10, "max_total_dollars": 1}
        self.tick = 0

    def sleep(self, seconds):
        self.tick += seconds
        if self.tick > 1000:
            self.fail("Guard did not terminate")

    def run_guard(self, credit_effect):
        write_json(self.path, self.state)
        with patch.object(guard_module, "credit", side_effect=credit_effect) as credit_mock:
            with patch.object(guard_module, "destroy", return_value={"success": True}) as destroy:
                guard_module.guard(self.path, clock=lambda: self.tick, sleep=self.sleep)
        destroy.assert_called_once_with(self.state)
        return read_json(self.path.parent / "guard-result.json"), credit_mock

    def test_expired_deadline_never_calls_billing(self):
        self.tick = 101
        report, credit_mock = self.run_guard(OSError("billing unavailable"))
        credit_mock.assert_not_called()
        self.assertEqual(report["reason"], "deadline")

    def test_billing_error_crossing_deadline_does_not_delay_teardown(self):
        def slow_failure():
            self.tick = 101
            raise OSError("billing unavailable")
        report, _ = self.run_guard(slow_failure)
        self.assertEqual(report["time"], 101)
        self.assertEqual(report["reason"], "deadline")

    def test_unavailable_credit_stops_before_long_deadline(self):
        self.state["deadline_epoch"] = 900
        report, _ = self.run_guard(OSError("billing unavailable"))
        self.assertEqual(report["reason"], "credit_unavailable")
        self.assertEqual(report["time"], 120)

    def test_cleanup_reserve(self):
        self.state["cleanup_lead_seconds"] = 20
        report, _ = self.run_guard(lambda: 10)
        self.assertEqual(report["time"], 80)
        self.assertEqual(report["reason"], "deadline")

    def test_spend_limit_stops_immediately(self):
        report, _ = self.run_guard(lambda: 8.9)
        self.assertEqual(report["reason"], "credit_guard")
        self.assertEqual(report["time"], 0)
