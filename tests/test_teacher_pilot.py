import copy
import importlib.util
import io
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

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


class TeacherBudgetTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.path = self.root / "authorization.json"
        self.auth = {
            "authorized": True, "experiment": "qwen_high_five_candidates_v1",
            **cloud.locked_inputs(), "authorization_id": "testteacher1",
            "max_total_dollars": 1.50, "max_hourly_dollars": 0.70,
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
                           ("max_hourly_dollars", 0.71), ("max_elapsed_seconds", 3601),
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
