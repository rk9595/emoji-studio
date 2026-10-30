"""Failure boundaries for the dedicated real-GPU acceptance wrapper."""

import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.render_budget import BudgetDenied, RenderBudget

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "ops" / f"{name}.py")
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


worker = module("amd_api_worker")
live = module("amd_api_live")


class Renderer:
    loaded = True

    def __init__(self):
        self.calls = 0

    def render(self, prompt, seed):
        self.calls += 1
        return prompt, seed


class TestLiveSmoke(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name).resolve() / "budget.sqlite"
        self.budget = RenderBudget.create(self.path, allocation_id="123", plan_sha256="a" * 64)

    def test_only_two_physical_calls_and_no_restart(self):
        renderer = Renderer()
        bounded = worker.BoundedRenderer(renderer, self.budget, 100, clock=lambda: 1)
        bounded.render("apple", 7)
        bounded.render("face", 8)
        with self.assertRaises(BudgetDenied):
            bounded.render("third", 9)
        self.assertEqual(renderer.calls, 2)
        with self.assertRaises(FileExistsError):
            RenderBudget.create(self.path, allocation_id="123", plan_sha256="a" * 64)

    def test_deadline_denies_before_call(self):
        renderer = Renderer()
        bounded = worker.BoundedRenderer(renderer, self.budget, 100, clock=lambda: 100)
        with self.assertRaises(RuntimeError):
            bounded.render("apple", 7)
        self.assertEqual(renderer.calls, 0)

    def test_failed_or_late_call_halts_further_work(self):
        renderer = Renderer()
        times = iter([1, 1, 101])
        bounded = worker.BoundedRenderer(renderer, self.budget, 100, clock=lambda: next(times))
        with self.assertRaises(RuntimeError):
            bounded.render("apple", 7)
        self.assertEqual(self.budget.snapshot()["calls"][0]["state"], "failed")
        bounded.clock = lambda: 1
        with self.assertRaises(BudgetDenied):
            bounded.render("face", 8)
        self.assertEqual(renderer.calls, 1)

    def test_exact_ownership_required_for_delete(self):
        row = {"name": "someone-else", "created_at": "2026-10-29T00:00:00Z"}
        with patch.object(live, "api", return_value={"droplet": row}) as api:
            with self.assertRaises(RuntimeError):
                live.delete_exact(123, {"started_epoch": 0})
            self.assertEqual(api.call_count, 1)

    def test_cleanup_only_confirmed_by_authenticated_404(self):
        with patch.object(live, "api", side_effect=live.ProviderError(403, "GET", "/droplets/123")):
            with self.assertRaises(live.ProviderError):
                live.delete_exact(123, {})
        with patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/123")):
            self.assertTrue(live.delete_exact(123, {}))

    def test_old_comparison_cannot_match(self):
        row = {"name": "emoji-ops-compare-v1", "tags": ["emoji-ops-compare-v1"],
               "created_at": "2026-10-29T00:00:00Z", "size_slug": live.SIZE,
               "region": {"slug": "atl1"}}
        self.assertFalse(live.owned(row, {"started_epoch": 0}))

    def test_claim_never_overwrites(self):
        with patch.object(Path, "write_text"), patch.object(live, "command") as command:
            live.put("allocation-intent.json", {"attempted": True})
            self.assertNotIn("--clobber", command.call_args.args[0])

    def test_workflow_rerun_cannot_reach_provider(self):
        with patch.dict(live.os.environ, {"AMD_API_SMOKE_SOURCE": "a", "GITHUB_SHA": "a", "GITHUB_RUN_ATTEMPT": "2"}):
            with patch.object(live, "api") as api:
                with self.assertRaises(RuntimeError):
                    live.run()
                api.assert_not_called()

    def test_ambiguous_post_consumes_claim_and_reconciles_for_cleanup(self):
        plan = Path(self.directory.name) / "plan.json"
        plan.write_text(json.dumps({"allocation_expires_epoch": 2000,
                                    "input_sha256": hashlib.sha256(b"archive").hexdigest()}))
        inspection = {"sizes": [{"price_hourly": 1.99, "available": True, "regions": ["atl1"]}],
                      "account": {"status": "active"},
                      "droplets": {"count": 0, "has_next_page": False}}
        env = {"AMD_API_SMOKE_SOURCE": "a", "GITHUB_SHA": "a", "GITHUB_RUN_ATTEMPT": "1",
               "GITHUB_RUN_ID": "456", "GH_REPO": "rk9595/emoji-studio-ops",
               "AMD_SSH_KEY_ID": "789", "AMD_DEV_CLOUD_TOKEN": "synthetic-test-token"}
        with (patch.dict(live.os.environ, env), patch.object(live, "PLAN", plan),
              patch.object(live.time, "time", return_value=1000),
              patch.object(live, "preflight", return_value=inspection),
              patch.object(live, "command", return_value='{"isPrivate": true}'),
              patch.object(Path, "read_bytes", return_value=b"archive"),
              patch.object(live, "get", return_value={"run_id": "456", "started_epoch": 1000}),
              patch.object(live, "put") as put,
              patch.object(live, "api", side_effect=TimeoutError) as api,
              patch.object(live, "candidates", return_value=[{"id": 123}]),
              patch.object(live, "delete_exact", return_value=True) as delete):
            with self.assertRaises(TimeoutError):
                live.run()
            self.assertEqual(api.call_count, 1)
            self.assertEqual(api.call_args.args[:2], ("POST", "/droplets"))
            delete.assert_called_once()
            self.assertEqual(delete.call_args.args[0], 123)
            self.assertEqual(put.call_args_list[0].args[0], "allocation-intent.json")
            self.assertEqual(put.call_args_list[0].kwargs, {})
            self.assertTrue(put.call_args.args[1]["cleanup_confirmed"])

    def test_read_only_transport_can_reconnect_but_is_bounded(self):
        with patch.object(live, "ssh", side_effect=[live.CommandError("ssh", 255), "hash"]) as ssh:
            with patch.object(live.time, "sleep"):
                self.assertEqual(live.ssh_read("host", "sha256sum file"), "hash")
                self.assertEqual(ssh.call_count, 2)
        with patch.object(live, "ssh", side_effect=live.CommandError("ssh", 255)) as ssh:
            with patch.object(live.time, "sleep"), self.assertRaises(live.CommandError):
                live.ssh_read("host", "sha256sum file")
            self.assertEqual(ssh.call_count, 3)

    def test_remote_launch_is_never_retried(self):
        with patch.object(live, "ssh_args", return_value=[]):
            with patch.object(live, "command", side_effect=live.CommandError("ssh", 255)) as command:
                with self.assertRaises(live.CommandError):
                    live.ssh("host", "systemd-run worker")
                command.assert_called_once()

    def test_ssh_framing_ignores_provider_banner(self):
        def run_locally(args, timeout):
            # Execute the actual generated shell wrapper, with a provider-like
            # prefix and suffix that would break exact READY matching/rsync.
            wrapper = "printf 'Welcome to the GPU image!\\n'; " + args[-1]
            result = subprocess.run(["bash", "-c", wrapper], capture_output=True,
                                    text=True, timeout=timeout, check=True)
            return result.stdout + "\nConnection banner after command\n"
        with patch.object(live, "ssh_args", return_value=[]):
            with patch.object(live, "command", side_effect=run_locally):
                self.assertEqual(live.ssh("host", "printf 'READY\\n'"), "READY\n")
                self.assertEqual(live.ssh("host", "printf 'abc123 file\\n'"), "abc123 file\n")

    def test_missing_command_frame_is_not_treated_as_readiness(self):
        with patch.object(live, "ssh_args", return_value=[]):
            with patch.object(live, "command", return_value="READY\n"), patch.object(live, "transport_diagnostic"):
                with self.assertRaisesRegex(RuntimeError, "framing missing"):
                    live.ssh("host", "echo READY")

    def test_previous_attempt_needs_verified_absence_and_remaining_reserve(self):
        plan = {"reserve_dollars": 2, "previous_attempt": {"release": "old", "droplet_id": 123, "run_id": "456"}}
        state = {"droplet_id": 123, "run_id": "456", "cleanup_confirmed": True,
                 "started_epoch": 1000, "cleanup_epoch": 1300, "rate_hourly": 1.99,
                 "prior_attempt_cost_dollars": 0.1256}
        watchdog = {"droplet_id": 123, "cleanup_confirmed": True}
        with patch.object(live, "command", side_effect=[json.dumps(state), json.dumps(watchdog)]):
            with patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/123")):
                self.assertAlmostEqual(live.previous_attempt_cost(plan), 0.1256 + 1.99 / 12)
        with patch.object(live, "command", side_effect=[json.dumps(state), json.dumps(watchdog)]):
            with patch.object(live, "api", return_value={}), self.assertRaises(RuntimeError):
                live.previous_attempt_cost(plan)
        plan["reserve_dollars"] = 1
        with patch.object(live, "command", side_effect=[json.dumps(state), json.dumps(watchdog)]):
            with patch.object(live, "api", side_effect=live.ProviderError(404, "GET", "/droplets/123")):
                with self.assertRaises(RuntimeError):
                    live.previous_attempt_cost(plan)
