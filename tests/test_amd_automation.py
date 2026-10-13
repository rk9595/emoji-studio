import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(relative):
    spec = importlib.util.spec_from_file_location(Path(relative).stem, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load("scripts/amd_compare.py")
campaign = load("ops/amd_campaign.py")
supervisor = load("ops/codex_supervisor.py")


class ComparisonTest(unittest.TestCase):
    def test_real_plan_balanced_and_hash_locked(self):
        config, pairs, lock = compare.plan(ROOT)
        self.assertEqual(len(pairs), 24)
        self.assertEqual(len(config["conditions"]), 6)
        self.assertEqual(config["expected_images"], 144)
        self.assertEqual(len(lock["config_sha256"]), 64)

    def test_verify_rejects_duplicate_corrupt_and_unsafe_images(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            image = output / "image.png"
            image.write_bytes(b"test-image")
            pair = {"pair_id": "p", "prompt": "x", "seed": 0, "category": "a", "criteria": ["b"]}
            row = {**pair, "condition": "base", "adapter_sha256": None,
                   "image": "image.png", "sha256": compare.sha256(image)}
            config = {"conditions": [{"id": "base", "sha256": None}]}
            lock = {"config_sha256": "locked"}
            report = {**lock, "status": "completed", "images": [row]}
            compare.save(output / "report.json", report)
            compare.verify(output, config, [pair], lock)
            report["images"] = [row, row]
            compare.save(output / "report.json", report)
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                compare.verify(output, config, [pair], lock)
            report["images"] = [{**row, "image": "../image.png"}]
            compare.save(output / "report.json", report)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                compare.verify(output, config, [pair], lock)
            report["images"] = [row]
            compare.save(output / "report.json", report)
            image.write_bytes(b"corrupt")
            with self.assertRaisesRegex(ValueError, "corrupt"):
                compare.verify(output, config, [pair], lock)


class CleanupTest(unittest.TestCase):
    def test_ssh_retries_transient_disconnect_and_reuses_transport(self):
        import subprocess

        with patch.dict("os.environ", {"AMD_SSH_KEY_FILE": "/tmp/test-key"}), \
             patch.object(campaign, "command") as command, patch.object(campaign.time, "sleep"):
            command.side_effect = [subprocess.CalledProcessError(255, "ssh"), "checksum\n"]
            self.assertEqual(campaign.ssh("test", "sha256sum inputs.tar.gz"), "checksum\n")
            self.assertEqual(command.call_count, 2)
            self.assertIn("ControlMaster=auto", command.call_args.args[0])
            self.assertIn("ControlPath=/tmp/emoji-ops-ssh-%C", command.call_args.args[0])

    def test_readiness_requires_clean_sentinel_not_only_ssh_success(self):
        for output in ("Initializing GPU image...", "Welcome\nEMOJI_OPS_READY_V1\n", ""):
            with patch.object(campaign, "ssh", return_value=output):
                self.assertFalse(campaign.remote_ready("test"))
        with patch.object(campaign, "ssh", return_value="EMOJI_OPS_READY_V1\n") as ssh:
            self.assertTrue(campaign.remote_ready("test"))
            self.assertFalse(ssh.call_args.kwargs["multiplex"])

    def test_ownership_requires_name_and_tag(self):
        self.assertFalse(campaign.owned({"name": campaign.NAME, "tags": []}))
        self.assertFalse(campaign.owned({"name": "unrelated", "tags": [campaign.TAG]}))
        self.assertTrue(campaign.owned({"name": campaign.NAME, "tags": [campaign.TAG]}))

    def test_destroy_refuses_other_instance(self):
        with patch.object(campaign, "api", return_value={"droplet": {"name": "other"}}) as api:
            with self.assertRaisesRegex(ValueError, "Refusing"):
                campaign.destroy(123)
            api.assert_called_once_with("GET", "/droplets/123")

    def test_reaper_only_deletes_overdue_owned_results(self):
        rows = [{"id": 1, "created_at": "1970-01-01T00:00:00Z"},
                {"id": 2, "created_at": "1970-01-01T01:00:00Z"}]
        with patch.object(campaign, "droplets", return_value=rows), patch.object(campaign, "destroy") as destroy:
            campaign.reap(now=4600)
            destroy.assert_called_once_with(1)

    def test_consumed_allocation_never_relaunches(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "ops").mkdir()
            (folder / "ops/campaign.json").write_text(json.dumps({"expires_epoch": 9999999999}))
            (folder / "state.json").write_text(json.dumps({"status": "running", "allocation_attempted": True}))
            import os
            previous = Path.cwd()
            try:
                os.chdir(folder)
                with patch.object(campaign, "command"), patch.object(campaign, "api") as api:
                    campaign.run()
                    api.assert_not_called()
            finally:
                os.chdir(previous)


class SupervisorTest(unittest.TestCase):
    def test_system_error_is_resumed_when_work_is_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "ops").mkdir()
            (root / "ops/work-queue.json").write_text('{"status":"ready"}')
            with patch.object(supervisor, "ROOT", root), \
                 patch.object(supervisor, "RUNTIME", root), \
                 patch.object(supervisor, "AppServer") as server:
                client = server.return_value
                client.call.side_effect = [
                    {"thread": {"status": {"type": "systemError"}}},
                    {"rateLimits": {"primary": {"usedPercent": 20}}}, {}, {},
                ]
                supervisor.tick({"enabled": True, "socket_path": "unused", "thread_id": "test"})
                self.assertEqual([c.args[0] for c in client.call.call_args_list],
                                 ["thread/read", "account/rateLimits/read", "thread/resume", "turn/start"])

    def test_waits_for_longest_exhausted_window(self):
        limits = {"rateLimits": {"primary": {"usedPercent": 100, "resetsAt": 5000},
                                  "secondary": {"usedPercent": 100, "resetsAt": 9000}}}
        self.assertEqual(supervisor.next_reset(limits, now=1000), 9060)

    def test_no_exhaustion_does_not_delay(self):
        limits = {"rateLimits": {"primary": {"usedPercent": 59, "resetsAt": 5000}}}
        self.assertEqual(supervisor.next_reset(limits, now=1000), 1000)

    def test_unknown_limits_defer(self):
        with self.assertRaisesRegex(ValueError, "unavailable"):
            supervisor.next_reset({}, 1000)

    def test_active_thread_is_never_resumed(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(supervisor, "RUNTIME", Path(directory)), \
                 patch.object(supervisor, "AppServer") as server:
                client = server.return_value
                client.call.side_effect = [
                    {"thread": {"status": {"type": "active"}}},
                    {"rateLimits": {"primary": {"usedPercent": 20}}},
                ]
                supervisor.tick({"enabled": True, "socket_path": "unused", "thread_id": "test"})
                self.assertEqual(client.call.call_count, 2)
                self.assertEqual(json.loads((Path(directory) / "supervisor-state.json").read_text())["reason"],
                                 "thread_already_active")


if __name__ == "__main__":
    unittest.main()
