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


evaluation = load_script("evaluate_lora.py")
remote = load_script("remote_quality_pilot.py")
vast = load_script("vast_quality_pilot.py")


class QualityPilotPlanTest(unittest.TestCase):
    def test_evaluation_has_twelve_fixed_pairs(self):
        config, benchmark_path, jobs = evaluation.evaluation_jobs(PROJECT)
        self.assertEqual(len(jobs), 12)
        self.assertEqual(len({job["pair_id"] for job in jobs}), 12)
        self.assertEqual({job["seed"] for job in jobs}, {0, 1})
        self.assertEqual(benchmark_path.name, "lora-quality-eval.json")
        self.assertEqual(config["max_steps"], 100)

    def test_training_command_is_locked_and_does_not_publish(self):
        command = remote.training_command(PROJECT)
        values = {
            name: command[command.index(name) + 1]
            for name in [
                "--max_train_steps",
                "--checkpointing_steps",
                "--checkpoints_total_limit",
                "--output_dir",
            ]
        }
        self.assertEqual(values["--max_train_steps"], "100")
        self.assertEqual(values["--checkpointing_steps"], "25")
        self.assertEqual(values["--checkpoints_total_limit"], "4")
        self.assertTrue(values["--output_dir"].endswith("runs/lora-quality-pilot"))
        self.assertIn("--skip_final_inference", command)
        self.assertNotIn("--push_to_hub", command)
        self.assertNotIn("--random_flip", command)
        self.assertNotIn("--train_text_encoder", command)


class QualityPilotAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = {
            "authorization_id": "qualitytest1",
            "authorized": True,
            "experiment": vast.EXPERIMENT,
            "export_hash": vast.EXPORT_HASH,
            "trainer_sha256": vast.TRAINER_HASH,
            "config_sha256": vast.CONFIG_HASH,
            "evaluation_sha256": vast.EVALUATION_HASH,
            "max_total_dollars": 1.0,
            "max_hourly_dollars": 0.7,
            "max_elapsed_seconds": 2700,
            "expires_epoch": time.time() + 3600,
        }
        self.path = self.root / "authorization.json"
        write_json(self.path, self.auth)
        self.patch = patch.object(vast, "ARTIFACT_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_exact_unexpired_authorization_passes(self):
        self.assertEqual(vast.load_authorization(self.path), self.auth)

    def test_changed_lock_or_unsafe_bound_fails(self):
        for key, value in [
            ("evaluation_sha256", "0" * 64),
            ("max_total_dollars", 2.01),
            ("max_elapsed_seconds", 1799),
            ("max_elapsed_seconds", 3601),
            ("expires_epoch", time.time() - 1),
        ]:
            changed = dict(self.auth)
            changed[key] = value
            write_json(self.path, changed)
            with self.assertRaises(ValueError):
                vast.load_authorization(self.path)

    def test_authorization_is_single_use(self):
        write_json(self.root / "prior/allocation.json", {"authorization_id": "qualitytest1"})
        with self.assertRaisesRegex(ValueError, "already used"):
            vast.load_authorization(self.path)


class QualityPilotArchiveTest(unittest.TestCase):
    def test_project_archive_contains_locked_inputs_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "project.tar.gz"
            vast.build_archive(target)
            with tarfile.open(target) as archive:
                names = archive.getnames()
        self.assertIn("configs/lora-quality-pilot.json", names)
        self.assertIn("benchmarks/lora-quality-eval.json", names)
        self.assertIn("benchmarks/development.json", names)
        self.assertIn("scripts/remote_train.sh", names)
        self.assertIn("scripts/remote_quality_pilot.py", names)
        self.assertIn("scripts/vast_quality_pilot.py", names)
        self.assertFalse(
            any("vast_api_key" in name or name.startswith(".config") for name in names)
        )

    def test_final_archive_requires_twelve_verified_pairs(self):
        adapter = b"final adapter"
        adapter_hash = hashlib.sha256(adapter).hexdigest()
        files = {
            "runs/lora-quality-pilot/pytorch_lora_weights.safetensors": adapter,
            "quality-pilot.log": b"complete",
            "quality-bootstrap.log": b"complete",
            "quality.exit": b"0",
        }
        checkpoints = []
        for step in [25, 50, 75, 100]:
            payload = adapter if step == 100 else f"adapter {step}".encode()
            path = f"runs/lora-quality-pilot/adapters/step-{step}.safetensors"
            files[path] = payload
            checkpoints.append(
                {"step": step, "path": path, "sha256": hashlib.sha256(payload).hexdigest()}
            )
        images = []
        for pair in range(12):
            for condition in ["base", "adapted"]:
                payload = f"image {pair} {condition}".encode()
                relative = f"evaluation/{condition}/pair-{pair}.png"
                files[f"runs/lora-quality-pilot/{relative}"] = payload
                images.append(
                    {
                        "pair_id": f"pair{pair}",
                        "condition": condition,
                        "image": relative,
                        "image_sha256": hashlib.sha256(payload).hexdigest(),
                    }
                )
        report = {
            "status": "completed",
            "final_adapter": {"sha256": adapter_hash},
            "checkpoint_adapters": checkpoints,
            "step_100_matches_final_tensors": True,
        }
        evaluation_report = {
            "status": "completed",
            "adapter_sha256": adapter_hash,
            "images": images,
        }
        files["runs/lora-quality-pilot-report.json"] = json.dumps(report).encode()
        files["runs/lora-quality-pilot/evaluation/report.json"] = json.dumps(
            evaluation_report
        ).encode()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "final.tar.gz"
            with tarfile.open(target, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            result = vast.validate_final_archive(target)
            self.assertEqual(result["final_adapter"]["sha256"], adapter_hash)
            files["quality.exit"] = b"1"
            with tarfile.open(target, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            with self.assertRaises(tarfile.TarError):
                vast.validate_final_archive(target)


if __name__ == "__main__":
    unittest.main()
