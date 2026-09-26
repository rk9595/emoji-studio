import copy
import importlib.util
import io
import os
import subprocess
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from emoji_studio.common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sampler = load_script("sample_interaction_teacher")
remote = load_script("remote_teacher_pilot")
cloud = load_script("vast_teacher_pilot")


class TeacherPilotTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.output = self.root / sampler.OUTPUT
        self.output.mkdir(parents=True)
        self.plan = sampler.make_plan()
        write_json(self.output / "plan.json", self.plan)

    def report(self, count=4):
        (self.output / "images").mkdir(exist_ok=True)
        rows = []
        for index, job in enumerate(self.plan["jobs"][:count]):
            path = self.output / "images" / f"{job['id']}.png"
            Image.new("RGB", (1328, 1328), (index, 0, 0)).save(path)
            rows.append({"job": job, "image": f"images/{path.name}",
                         "image_sha256": sampler.sha256(path), "curation_decision": "pending"})
        report = {"plan_hash": self.plan["plan_hash"], "status": "completed", "images": rows}
        write_json(self.output / "report.json", report)
        return report

    def test_four_candidates_have_no_frozen_prompts(self):
        frozen = read_json(ROOT / "benchmarks/high-five-v1.json")["prompts"]
        self.assertEqual(len(self.plan["jobs"]), 4)
        for job in self.plan["jobs"]:
            self.assertFalse(any(row["prompt"] in job["prompt"] for row in frozen))
        self.assertEqual(len({r["pose_group"] for r in self.plan["jobs"]}), 4)

    def test_report_requires_every_job_and_valid_dimensions(self):
        self.report(3)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            sampler.validate_report(self.output, self.plan)
        report = self.report()
        self.assertEqual(sampler.validate_report(self.output, self.plan), report)
        path = self.output / report["images"][0]["image"]
        Image.new("RGB", (64, 64)).save(path)
        report["images"][0]["image_sha256"] = sampler.sha256(path)
        write_json(self.output / "report.json", report)
        with self.assertRaisesRegex(ValueError, "dimensions"):
            sampler.validate_report(self.output, self.plan)

    def test_corrupted_image_or_repeated_job_is_rejected(self):
        report = self.report()
        report["images"].append(copy.deepcopy(report["images"][0]))
        write_json(self.output / "report.json", report)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            sampler.validate_report(self.output, self.plan)
        report = self.report()
        (self.output / report["images"][0]["image"]).write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError, "checksum"):
            sampler.validate_report(self.output, self.plan)

    def test_snapshot_copies_only_committed_report_images(self):
        report = self.report(1)
        (self.output / "images/uncommitted.png").write_bytes(b"not in report")
        stream = io.BytesIO()
        remote.snapshot(stream, self.root)
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:gz") as archive:
            self.assertNotIn(f"{sampler.OUTPUT}/images/uncommitted.png", archive.getnames())
            self.assertIn(f"{sampler.OUTPUT}/{report['images'][0]['image']}", archive.getnames())

    def test_worker_bootstraps_pinned_installer_before_environment(self):
        with patch.object(remote, "ROOT", self.root), patch.dict(os.environ), \
                patch.object(remote.subprocess, "run", return_value=Mock(returncode=0)) as run:
            self.assertEqual(remote.worker(1200), 0)
            commands = [call.args[0] for call in run.call_args_list]
            self.assertEqual(commands[0][1:], ["-m", "pip", "install", "--target",
                                              "/workspace/uv-cli", "uv==0.10.9"])
            self.assertEqual(commands[1][1:], ["scripts/remote_environment.py"])
            self.assertTrue(os.environ["PATH"].startswith("/workspace/uv-cli/bin" + os.pathsep))
            self.assertEqual(os.environ["HF_HOME"], "/workspace/huggingface")
        self.assertEqual((self.root / "teacher.exit").read_text(), "0")

    def test_upload_excludes_credentials_and_other_experiments(self):
        for name in cloud.FILES:
            path = self.root / name
            if name == "src":
                path.mkdir()
                (path / "fixture.py").write_text("pass")
            elif not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fixture")
        write_json(self.root / "configs/alpha-users.json", {"private": "must not upload"})
        write_json(self.root / "artifacts/private.json", {"private": "must not upload"})
        archive_path = self.root / "bundle.tar.gz"
        with patch.object(cloud, "ROOT", self.root), patch.object(cloud, "make_plan",
                                                                 return_value=self.plan):
            cloud.build_archive(archive_path)
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
        self.assertNotIn("configs/alpha-users.json", names)
        self.assertNotIn("artifacts/private.json", names)
        self.assertIn("scripts/remote_teacher_pilot.py", names)

    def test_resume_upload_includes_only_verified_completed_candidates(self):
        self.test_upload_excludes_credentials_and_other_experiments()
        report = self.report(1)
        (self.output / "images/uncommitted.png").write_bytes(b"not committed")
        archive_path = self.root / "resume.tar.gz"
        with patch.object(cloud, "ROOT", self.root), \
                patch.object(cloud, "make_plan", return_value=self.plan):
            cloud.build_archive(archive_path)
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
        self.assertIn(f"{sampler.OUTPUT}/report.json", names)
        self.assertIn(f"{sampler.OUTPUT}/{report['images'][0]['image']}", names)
        self.assertNotIn(f"{sampler.OUTPUT}/images/uncommitted.png", names)
        (self.output / report["images"][0]["image"]).write_bytes(b"corrupt")
        with patch.object(cloud, "ROOT", self.root), \
                patch.object(cloud, "make_plan", return_value=self.plan):
            with self.assertRaisesRegex(ValueError, "checksum"):
                cloud.build_archive(archive_path)

    def test_ssh_read_retries_transport_failure_but_not_remote_program_failure(self):
        transport = subprocess.CalledProcessError(255, ["ssh"])
        operation = Mock(side_effect=[transport, "recovered"])
        with patch.object(cloud, "require_live_budget") as budget, \
                patch.object(cloud.time, "sleep"):
            self.assertEqual(cloud.read_with_retries(operation, {}, self.root), "recovered")
            self.assertEqual(budget.call_count, 2)
            operation = Mock(side_effect=subprocess.CalledProcessError(1, ["ssh"]))
            with self.assertRaises(subprocess.CalledProcessError):
                cloud.read_with_retries(operation, {}, self.root)
            self.assertEqual(operation.call_count, 1)

    def test_ssh_read_retries_are_bounded_and_cannot_cross_budget_guard(self):
        operation = Mock(side_effect=subprocess.TimeoutExpired(["ssh"], 30))
        with patch.object(cloud, "require_live_budget"), patch.object(cloud.time, "sleep"):
            with self.assertRaises(subprocess.TimeoutExpired):
                cloud.read_with_retries(operation, {}, self.root)
            self.assertEqual(operation.call_count, 3)
        operation.reset_mock()
        with patch.object(cloud, "require_live_budget", side_effect=[None, TimeoutError]), \
                patch.object(cloud.time, "sleep"):
            with self.assertRaises(TimeoutError):
                cloud.read_with_retries(operation, {}, self.root)
            self.assertEqual(operation.call_count, 1)

    def test_live_budget_rejects_expiry_stale_heartbeat_spend_and_shutdown(self):
        state = {"deadline_epoch": 1400, "max_total_dollars": 1.10}
        write_json(self.root / "guard-heartbeat.json", {"time": 990, "observed_spent": .20})
        with patch.object(cloud.time, "time", return_value=1000):
            cloud.require_live_budget(state, self.root)
            with self.assertRaises(TimeoutError):
                cloud.require_live_budget({**state, "deadline_epoch": 1240}, self.root)
            for heartbeat in [{"time": 900}, {"time": 990, "observed_spent": 1.10},
                              {"time": 990, "stop_reason": "credit_guard"}]:
                write_json(self.root / "guard-heartbeat.json", heartbeat)
                with self.assertRaises((RuntimeError, TimeoutError)):
                    cloud.require_live_budget(state, self.root)


class TeacherBudgetTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "authorization.json"
        self.auth = {
            "authorized": True, "experiment": "qwen_high_five_candidates_v1",
            **cloud.locked_inputs(), "authorization_id": "testteacher1",
            "max_total_dollars": 1.50, "max_hourly_dollars": 0.80,
            "max_elapsed_seconds": 3600, "expires_epoch": time.time() + 600,
        }
        self.patcher = patch.object(cloud, "ARTIFACT_ROOT", self.root)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def load(self):
        write_json(self.path, self.auth)
        return cloud.load_authorization(self.path)

    def test_authorization_is_exact_and_consumed_before_rental_retry(self):
        self.assertEqual(self.load(), self.auth)
        write_json(self.root / "attempt-1/attempt.json", self.auth)
        with self.assertRaisesRegex(ValueError, "consumed"):
            self.load()

    def test_budget_overrides_expiry_and_changed_inputs_are_rejected(self):
        original = dict(self.auth)
        for key, value in [("authorized", 1), ("max_total_dollars", 1.51),
                           ("max_hourly_dollars", 0.81), ("max_elapsed_seconds", 3601),
                           ("expires_epoch", 0), ("guard_sha256", "changed")]:
            self.auth = {**original, key: value}
            with self.assertRaises(ValueError, msg=key):
                self.load()

    def test_offer_cannot_exceed_rate_or_reduce_memory(self):
        row = {"num_gpus": 1, "gpu_ram": 48000, "cpu_ram": 128000,
               "disk_space": 200, "compute_cap": 890, "reliability": 0.999,
               "dph_total": 0.69, "inet_down_cost": 0.003, "inet_up_cost": 0.003}
        self.assertTrue(cloud.offer_allowed(row, 0.70))
        for key, value in [("dph_total", 0.71), ("cpu_ram", 64000), ("num_gpus", 2),
                           ("gpu_ram", float("nan"))]:
            self.assertFalse(cloud.offer_allowed({**row, key: value}, 0.70))
