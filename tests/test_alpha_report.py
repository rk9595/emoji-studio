import json
import tempfile
import unittest
from pathlib import Path

from emoji_studio.alpha_report import markdown_report, summarize_alpha
from emoji_studio.common import write_json
from emoji_studio.service import JobStore


class AlphaReportTest(unittest.TestCase):
    def test_summary_uses_terminal_jobs_feedback_and_result_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            store = JobStore(root)
            good = store.create(["apple"], [1], "one", owner_id="tester-one")
            store.update(
                good["id"],
                status="succeeded",
                results=[
                    {
                        "metrics": {
                            "generation_seconds": 8.0,
                            "estimated_cost_dollars": 0.002,
                        }
                    }
                ],
            )
            write_json(
                root / good["id"] / "feedback.json",
                {"rating": "up", "comment": "useful"},
            )
            failed = store.create(["bicycle"], [2], "two", owner_id="tester-two")
            store.update(failed["id"], status="failed", results=[])
            criteria = {
                "trial_generation_cap": 100,
                "success_criteria": {
                    "minimum_usable_fraction": 0.7,
                    "maximum_failure_fraction": 0.6,
                    "maximum_warm_cost_per_image_dollars": 0.03,
                },
            }

            report = summarize_alpha(root, criteria)

            self.assertEqual(report["jobs"], {"total": 2, "failed": 1, "succeeded": 1})
            self.assertEqual(report["images"]["succeeded"], 1)
            self.assertEqual(report["feedback"]["usable_fraction"], 1.0)
            self.assertEqual(report["failure_fraction"], 0.5)
            self.assertTrue(report["all_measured_checks_pass"])
            self.assertIn("PASS — usable fraction", markdown_report(report))

    def test_empty_alpha_is_explicitly_awaiting_feedback(self):
        with tempfile.TemporaryDirectory() as directory:
            report = summarize_alpha(
                directory,
                {
                    "trial_generation_cap": 100,
                    "success_criteria": {
                        "minimum_usable_fraction": 0.7,
                        "maximum_failure_fraction": 0.05,
                        "maximum_warm_cost_per_image_dollars": 0.03,
                    },
                },
            )
            self.assertEqual(report["status"], "awaiting_feedback")
            self.assertFalse(report["all_measured_checks_pass"])
            self.assertIsNone(report["feedback"]["usable_fraction"])
            json.dumps(report)


if __name__ == "__main__":
    unittest.main()
