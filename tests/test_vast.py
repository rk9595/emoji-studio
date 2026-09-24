import importlib.util
import io
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from emoji_studio.benchmark import create_plan
from emoji_studio.runner import execute_jobs

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/vast_smoke.py"
SPEC = importlib.util.spec_from_file_location("vast_smoke", SCRIPT)
vast = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(vast)


class VastSafetyTest(unittest.TestCase):
    def test_resume_bundle_includes_only_checksum_verified_images(self):
        import shutil

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["configs", "benchmarks"]:
                shutil.copytree(SCRIPT.parents[1] / name, root / name)
            folder = root / "runs/test"
            plan = create_plan(root, folder / "plan.json", "sdxl", ["raw"], [0], limit=2)
            execute_jobs(
                plan, folder, lambda *args: (Image.new("RGB", (8, 8)), {}), 100, clock=lambda: 0
            )
            bad_id = plan["jobs"][1]["id"]
            (folder / "images" / f"{bad_id}.png").write_bytes(b"corrupt")
            with tarfile.open(root / "test.tar", "w") as archive:
                vast.add_run_artifacts(archive, root, "test")
            with tarfile.open(root / "test.tar") as archive:
                names = archive.getnames()
            self.assertIn("runs/test/plan.json", names)
            self.assertEqual(sum(n.endswith(".png") for n in names), 1)
            self.assertFalse(any(bad_id in n for n in names))

    def test_offer_checks_fail_closed(self):
        offer = {
            "gpu_name": "RTX 6000Ada",
            "num_gpus": 1,
            "gpu_ram": 48000,
            "cpu_ram": 64000,
            "compute_cap": 890,
            "dph_total": 0.65,
            "inet_down_cost": 0.004,
            "inet_up_cost": 0.004,
        }
        self.assertTrue(vast.offer_allowed(offer))
        for key, value in [
            ("dph_total", 0.71),
            ("dph_total", float("nan")),
            ("inet_up_cost", 0.01),
            ("gpu_name", "RTX 4090"),
            ("num_gpus", 2),
            ("cpu_ram", 32000),
        ]:
            self.assertFalse(vast.offer_allowed({**offer, key: value}))
        self.assertFalse(vast.offer_allowed({}))

    def test_failed_snapshot_preserves_last_good_archive(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            previous = folder / "results.tar.gz"
            previous.write_bytes(b"previous verified snapshot")
            with (
                patch.object(
                    vast.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 90)
                ),
                patch("builtins.print"),
            ):
                self.assertFalse(vast.sync_results(["ssh", "test"], folder))
            self.assertEqual(previous.read_bytes(), b"previous verified snapshot")

    def test_successful_snapshot_is_committed_atomically(self):
        def fake_download(*args, **kwargs):
            with tarfile.open(fileobj=kwargs["stdout"], mode="w:gz") as archive:
                member = tarfile.TarInfo("runs/klein-smoke/plan.json")
                member.size = 2
                archive.addfile(member, io.BytesIO(b"{}"))
            return subprocess.CompletedProcess([], 0)

        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            with (
                patch.object(vast.subprocess, "run", side_effect=fake_download),
                patch("builtins.print"),
            ):
                self.assertTrue(vast.sync_results(["ssh", "test"], folder))
            self.assertTrue((folder / "results.tar.gz").exists())
            self.assertFalse((folder / "results.download").exists())

    def test_log_tail_can_start_mid_utf8_character(self):
        result = subprocess.CompletedProcess([], 0, stdout=b"\x81partial character\n")
        with patch.object(vast.subprocess, "run", return_value=result), patch("builtins.print"):
            vast.print_remote_progress(["ssh", "test"])

    def test_progress_timeout_does_not_abort_workload(self):
        with (
            patch.object(vast.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 30)),
            patch("builtins.print"),
        ):
            vast.print_remote_progress(["ssh", "test"])

    def test_credit_is_not_the_legacy_balance_field(self):
        with patch.object(vast, "request", return_value={"balance": 0, "credit": 8.5}):
            self.assertEqual(vast.credit(), 8.5)

    def test_missing_credit_fails_closed(self):
        with patch.object(vast, "request", return_value={"balance": 100}):
            with self.assertRaises(ValueError):
                vast.credit()

    def test_cleanup_refuses_unrelated_instance(self):
        with patch.object(
            vast, "request", return_value={"instances": {"label": "unrelated"}}
        ) as req:
            with self.assertRaises(ValueError):
                vast.destroy({"instance_id": 1, "label": "emoji-smoke-test"})
            self.assertEqual(req.call_count, 1)
            self.assertEqual(req.call_args.args[0], "GET")

    def test_cleanup_requires_matching_label(self):
        with patch.object(
            vast,
            "request",
            side_effect=[
                {"instances": {"label": "emoji-smoke-test"}},
                {"success": True},
            ],
        ) as req:
            result = vast.destroy({"instance_id": 1, "label": "emoji-smoke-test"})
            self.assertTrue(result["success"])
            self.assertEqual(req.call_args.args, ("DELETE", "/v0/instances/1"))


if __name__ == "__main__":
    unittest.main()
