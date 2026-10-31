import importlib.util
import json
import os
import subprocess
import sys
import tempfile
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
worker = module("amd_training_worker")


class TrainingLifecycleTest(unittest.TestCase):
    def plan(self):
        return {"campaign": live.RELEASE, "max_allocations": 1, "max_concurrent_gpus": 1,
                "max_lifetime_seconds": 3600, "work_cutoff_seconds": 3300,
                "self_expiry_seconds": 3360, "max_hourly_dollars": 1.99,
                "reserve_dollars": 2.25, "max_training_steps": 624,
                "smoke_steps": 2, "max_physical_renders": 49,
                "previous_attempt": {"release": "amd-coverage-20261031a",
                                     "run_id": "41203305217", "droplet_id": 614520349,
                                     "source": "82b486c9ba73ee47332f4f8f0e1f14b6de9ed6a6"}}

    def test_previous_cleanup_and_total_budget_are_required(self):
        plan = self.plan()
        state = {"droplet_id": 614520349, "campaign": "amd-coverage-20261031a",
                 "run_id": "41203305217", "source": plan["previous_attempt"]["source"],
                 "cleanup_confirmed": True, "started_epoch": 1000, "cleanup_epoch": 1250,
                 "rate_hourly": 1.99}
        watchdog = {"droplet_id": 614520349, "cleanup_confirmed": True, "independent": True}
        for changed, succeeds in (({}, True), ({"cleanup_confirmed": False}, False),
                                  ({"cleanup_epoch": 4600}, False), ({"droplet_id": 1}, False)):
            with self.subTest(changed=changed), patch.object(live, "command", side_effect=[
                json.dumps(state | changed), json.dumps(watchdog)]), patch.object(
                    live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/614520349")):
                if succeeds:
                    self.assertAlmostEqual(live.previous_attempt_cost(plan), 250 * 1.99 / 3600)
                else:
                    with self.assertRaises(RuntimeError):
                        live.previous_attempt_cost(plan)
        with patch.object(live, "command", side_effect=[json.dumps(state), json.dumps(watchdog)]), \
                patch.object(live, "api", return_value={}), self.assertRaises(RuntimeError):
            live.previous_attempt_cost(plan)

    def test_no_implicit_budget_expansion_or_old_claims(self):
        live.validate_plan(self.plan())
        for field, value in (("max_allocations", 2), ("reserve_dollars", 3),
                             ("max_training_steps", 1000), ("max_physical_renders", 50),
                             ("self_expiry_seconds", 4000), ("campaign", "amd-comparison-v1"),
                             ("previous_attempt", {"release": "old"})):
            with self.subTest(field=field), self.assertRaises(ValueError):
                live.validate_plan(self.plan() | {field: value})

    def test_unarmed_and_rerun_jobs_never_allocate(self):
        with patch.dict(os.environ, {"AMD_TRAINING_SOURCE": "wrong", "GITHUB_SHA": "head"}), \
                patch.object(live, "api") as api, self.assertRaises(RuntimeError):
            live.run()
        api.assert_not_called()
        with patch.dict(os.environ, {"AMD_TRAINING_SOURCE": "head", "GITHUB_SHA": "head",
                                     "GITHUB_RUN_ATTEMPT": "2"}), \
                patch.object(live, "api") as api, self.assertRaises(RuntimeError):
            live.run()
        api.assert_not_called()

    def test_artifact_paths_counts_and_sizes_are_bounded(self):
        descriptor = {"bytes": 10, "sha256": "a" * 64}
        live.checked_files({"files": {"step-500.safetensors": descriptor}})
        for name in ("../secret", "evaluation-48.png", "arbitrary.bin"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                live.checked_files({"files": {name: descriptor}})
        for changed in (descriptor | {"bytes": 50_000_001}, descriptor | {"sha256": "z" * 64}):
            with self.assertRaises(ValueError):
                live.checked_files({"files": {"smoke.png": changed}})

    def test_deletion_requires_exact_resource_confirmation(self):
        intent = {"started_epoch": 1000}
        with patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/123")) as api:
            self.assertTrue(live.delete_exact(123, intent))
        self.assertEqual(api.call_args.args, ("GET", "/droplets/123"))
        with patch.object(live, "api", return_value={"droplet": {"id": 123}}), \
                patch.object(live, "owned", return_value=False), self.assertRaises(RuntimeError):
            live.delete_exact(123, intent)

    def test_expiry_is_absolute_and_campaign_specific(self):
        with patch.dict(os.environ, {"AMD_DEV_CLOUD_TOKEN": "test-placeholder"}):
            text = live.cloud_init({"started_epoch": 1000})
        self.assertIn("--on-calendar=@4360", text)
        self.assertIn("emoji-training-expiry", text)
        self.assertNotIn("amd-comparison-v1", text)

    def test_child_render_records_survive_parent_phase_save(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(worker, "OUT", Path(temp)), \
                patch.object(worker, "collect_checkpoints"):
            report = {"files": {}, "images": [], "phases": {}}
            worker.save(report)
            child = {"files": {"smoke.png": {"bytes": 10, "sha256": "a" * 64}},
                     "images": [{"file": "smoke.png"}], "phases": {}}
            command = [sys.executable, "-c", "from pathlib import Path; import sys; Path(sys.argv[1]).write_text(sys.argv[2])",
                       str(Path(temp) / "report.json"), json.dumps(child)]
            # Real child execution; avoid a five-second polling delay in this fixture.
            real_popen = subprocess.Popen

            def completed(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                process.wait(timeout=10)
                return process

            with patch.object(worker.subprocess, "Popen", side_effect=completed):
                worker.phase(command, worker.time.time() + 30, report, "reload")
            saved = json.loads((Path(temp) / "report.json").read_bytes())
            self.assertEqual(saved["images"], child["images"])
            self.assertEqual(saved["files"], child["files"])
            self.assertEqual(saved["phases"]["reload"]["exit_code"], 0)


if __name__ == "__main__":
    unittest.main()
