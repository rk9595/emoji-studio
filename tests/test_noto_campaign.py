import importlib.util
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


live = module("amd_training_live")


def noto_plan():
    return {"campaign": live.NOTO_RELEASE, "max_allocations": 1, "max_concurrent_gpus": 1,
            "max_lifetime_seconds": 3600, "work_cutoff_seconds": 3300,
            "self_expiry_seconds": 3360, "max_hourly_dollars": 1.99,
            "reserve_dollars": 10, "max_training_steps": live.NOTO_STEPS,
            "smoke_steps": 2, "max_physical_renders": 49,
            "training_bundle": "fluent-noto-v1",
            "training_recipe": "configs/lora-fluent-noto-v1.json",
            "codex_usage_guard": False,
            "execution_authorized": True,
            "previous_attempts": [dict(item) for item in live.CONSUMED_ATTEMPTS]}


class NotoCampaignTest(unittest.TestCase):
    def test_even_subset_covers_the_ends_without_collapsing(self):
        from emoji_studio.noto_font import SUBSET_COUNT, emoji_codepoint, evenly_spaced

        self.assertFalse(emoji_codepoint(0x23))
        self.assertFalse(emoji_codepoint(0xFE837))
        self.assertTrue(emoji_codepoint(0x1F600))

        chosen = evenly_spaced(list(range(3727)), SUBSET_COUNT)
        self.assertEqual(len(chosen), SUBSET_COUNT)
        self.assertEqual(chosen[0], 0)
        self.assertEqual(chosen[-1], 3726)
        self.assertEqual(len(set(chosen)), SUBSET_COUNT)

    def test_noto_plan_requires_both_consumed_attempts_and_no_codex_guard(self):
        with patch.dict(os.environ, {"AMD_TRAINING_RELEASE": live.NOTO_RELEASE}):
            reloaded = module("amd_training_live")
        reloaded.validate_plan(noto_plan() | {"campaign": reloaded.NOTO_RELEASE})
        for change in ({"max_training_steps": 624}, {"reserve_dollars": 2.25}, {"codex_usage_guard": True},
                       {"execution_authorized": False},
                       {"previous_attempts": [dict(live.CONSUMED_ATTEMPTS[0])]},
                       {"training_bundle": "coverage-v1"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                reloaded.validate_plan(noto_plan() | change | {"campaign": reloaded.NOTO_RELEASE})

    def test_aggregate_cost_uses_reconciliation_for_campaign_b(self):
        plan = noto_plan()
        first = {"droplet_id": 614520349, "campaign": "amd-coverage-20261031a",
                 "run_id": "41203305217", "source": plan["previous_attempts"][0]["source"],
                 "cleanup_confirmed": True, "started_epoch": 1000, "cleanup_epoch": 1250,
                 "rate_hourly": 1.99}
        second = {"droplet_id": 614682073, "campaign": "amd-coverage-20261031b",
                  "run_id": "41273277371", "source": plan["previous_attempts"][1]["source"],
                  "cleanup_confirmed": True, "started_epoch": 2000, "cleanup_epoch": 2125,
                  "rate_hourly": 1.99}
        watchdog = {"droplet_id": 614520349, "cleanup_confirmed": True, "independent": True}
        reconciliation = {"allocation_id": 614682073, "original_run_id": "41273277371",
                          "cleanup_confirmed": True, "independent": True, "read_only": True,
                          "exact_resource_http_status": 404}
        payloads = [json.dumps(first), json.dumps(watchdog), json.dumps(second), json.dumps(reconciliation)]
        with patch.object(live, "command", side_effect=payloads), \
                patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/1")):
            self.assertAlmostEqual(live.aggregate_prior_cost(plan), (250 + 125) * 1.99 / 3600)
        broken = dict(reconciliation, exact_resource_http_status=200)
        with patch.object(live, "command", side_effect=[payloads[0], payloads[1], payloads[2], json.dumps(broken)]), \
                patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/1")), \
                self.assertRaises(RuntimeError):
            live.aggregate_prior_cost(plan)

    def test_consumed_controller_cannot_allocate_again(self):
        with patch.dict(os.environ, {"AMD_TRAINING_SOURCE": "head", "GITHUB_SHA": "head",
                                     "GITHUB_RUN_ATTEMPT": "1"}), \
                patch.object(live, "api") as api, self.assertRaisesRegex(RuntimeError, "Consumed campaign"):
            live.run()
        api.assert_not_called()


if __name__ == "__main__":
    unittest.main()
