import hashlib
import importlib.util
import io
import json
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = PROJECT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


remote = load_script("remote_train.py")
vast = load_script("vast_train.py")


class TrainingCommandTest(unittest.TestCase):
    def test_first_step_is_bounded_and_does_not_publish(self):
        command = remote.training_args(PROJECT, 1)
        self.assertEqual(command[command.index("--max_train_steps") + 1], "1")
        self.assertEqual(command[command.index("--checkpointing_steps") + 1], "1")
        self.assertIn("--skip_final_inference", command)
        self.assertNotIn("--push_to_hub", command)
        self.assertNotIn("--random_flip", command)
        self.assertNotIn("--resume_from_checkpoint", command)

    def test_second_step_must_resume_latest_checkpoint(self):
        command = remote.training_args(PROJECT, 2, resume=True)
        self.assertEqual(command[command.index("--max_train_steps") + 1], "2")
        self.assertEqual(command[command.index("--resume_from_checkpoint") + 1], "latest")


class TrainingAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = {
            "authorization_id": "test123",
            "authorized": True,
            "experiment": vast.EXPERIMENT,
            "export_hash": vast.EXPORT_HASH,
            "trainer_sha256": vast.TRAINER_HASH,
            "max_total_dollars": 3.0,
            "max_hourly_dollars": 0.7,
            "max_elapsed_seconds": 5400,
            "expires_epoch": time.time() + 3600,
        }
        self.path = self.root / "authorization.json"
        write_json(self.path, self.auth)
        self.patch = patch.object(vast, "ARTIFACT_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_exact_unexpired_authorization_passes(self):
        self.assertEqual(vast.load_authorization(self.path), self.auth)

    def test_false_or_expired_authorization_fails(self):
        for key, value in [("authorized", False), ("expires_epoch", time.time() - 1)]:
            changed = dict(self.auth)
            changed[key] = value
            write_json(self.path, changed)
            with self.assertRaises(ValueError):
                vast.load_authorization(self.path)

    def test_hard_budget_bounds_fail_closed(self):
        for key, value in [
            ("max_total_dollars", 5.01),
            ("max_hourly_dollars", 0.71),
            ("max_elapsed_seconds", 7201),
            ("max_total_dollars", float("nan")),
            ("max_elapsed_seconds", True),
        ]:
            changed = dict(self.auth)
            changed[key] = value
            write_json(self.path, changed)
            with self.assertRaises(ValueError):
                vast.load_authorization(self.path)

    def test_authorization_is_single_allocation(self):
        allocation = self.root / "old-run/allocation.json"
        write_json(allocation, {"authorization_id": self.auth["authorization_id"]})
        with self.assertRaisesRegex(ValueError, "already used"):
            vast.load_authorization(self.path)

    def test_extra_fields_fail_closed(self):
        changed = {**self.auth, "note": "unexpected"}
        write_json(self.path, changed)
        with self.assertRaisesRegex(ValueError, "unexpected or missing"):
            vast.load_authorization(self.path)


class TrainingVastSafetyTest(unittest.TestCase):
    def test_offer_checks_use_authorized_hourly_cap(self):
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
        self.assertTrue(vast.offer_allowed(offer, 0.70))
        self.assertFalse(vast.offer_allowed(offer, 0.60))
        self.assertFalse(vast.offer_allowed({**offer, "num_gpus": 2}, 0.70))
        self.assertFalse(vast.offer_allowed({**offer, "dph_total": float("nan")}, 0.70))

    def test_training_archive_contains_only_needed_project_inputs(self):
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "project.tar.gz"
            vast.build_archive(archive_path)
            with tarfile.open(archive_path) as archive:
                names = archive.getnames()
        self.assertIn("data/training/pilot-v1/manifest.json", names)
        self.assertIn(f"artifacts/trainers/{vast.TRAINER_REVISION}/LICENSE", names)
        self.assertIn("scripts/remote_train.py", names)
        self.assertIn("scripts/vast_train.py", names)
        self.assertFalse(
            any("vast_api_key" in name or name.startswith(".config") for name in names)
        )

    def test_final_archive_requires_matching_adapter_and_image_hashes(self):
        adapter = b"final adapter fixture"
        image = b"inference image fixture"
        adapter_hash = hashlib.sha256(adapter).hexdigest()
        image_hash = hashlib.sha256(image).hexdigest()
        files = {
            "runs/training-smoke-report.json": json.dumps(
                {"status": "completed", "final_adapter": {"sha256": adapter_hash}}
            ).encode(),
            "runs/lora-pilot-smoke/pytorch_lora_weights.safetensors": adapter,
            "runs/lora-pilot-smoke/adapter-inference.json": json.dumps(
                {"adapter_sha256": adapter_hash, "image_sha256": image_hash}
            ).encode(),
            "runs/lora-pilot-smoke/adapter-inference.png": image,
            "training.log": b"complete",
            "training-bootstrap.log": b"complete",
            "training.exit": b"0",
        }
        with tempfile.TemporaryDirectory() as directory:
            archive_path = Path(directory) / "final.tar.gz"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            report = vast.validate_final_archive(archive_path)
            self.assertEqual(report["final_adapter"]["sha256"], adapter_hash)
            files["training.exit"] = b"1"
            with tarfile.open(archive_path, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            with self.assertRaises(tarfile.TarError):
                vast.validate_final_archive(archive_path)


if __name__ == "__main__":
    unittest.main()
