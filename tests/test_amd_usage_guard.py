import importlib.util
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
spec = importlib.util.spec_from_file_location("guard", Path(__file__).resolve().parents[1] / "ops/amd_usage_guard.py")
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class UsageGuardTest(unittest.TestCase):
    def test_training_and_api_campaign_binding(self):
        for workflow, key, seconds in (("AMD coverage training", "active_training_attempt", 4200),
                                       ("AMD two-image API smoke", "active_api_attempt", 2400)):
            queue = {"cloud_repository": "rk9595/emoji-studio-ops", "cloud_run_workflow": workflow,
                     key: {"release": "fresh"}}
            self.assertEqual(guard.campaign_binding(queue, "fresh"), seconds)
            with self.assertRaises(ValueError):
                guard.campaign_binding(queue, "consumed")
        with self.assertRaises(ValueError):
            guard.campaign_binding({"cloud_run_workflow": "unknown"}, "fresh")

    def test_weekly_or_primary_near_limit_stops(self):
        for first, second, expected in [(49, 39, False), (85, 39, True), (30, 90, True)]:
            with self.subTest(primary=first, secondary=second):
                response = {"rateLimits": {"primary": {"usedPercent": first},
                                          "secondary": {"usedPercent": second}}}
                self.assertEqual(guard.near_limit(response), expected)

    def test_all_metered_buckets_are_considered(self):
        response = {"rateLimitsByLimitId": {"one": {"primary": {"usedPercent": 10}},
                                             "two": {"primary": {"usedPercent": 95}}}}
        self.assertTrue(guard.near_limit(response))

    def test_unknown_signal_never_claims_headroom(self):
        for response in ({}, {"rateLimits": {"primary": {"usedPercent": None}}},
                         {"rateLimits": {"primary": {"usedPercent": float("nan")}}}):
            with self.subTest(response=response), self.assertRaises(ValueError):
                guard.near_limit(response)

    def test_classified_limit_reached_stops_immediately(self):
        self.assertTrue(guard.near_limit({"rateLimits": {"rateLimitReachedType": "usage_limit"}}))
