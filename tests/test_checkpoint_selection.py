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

from PIL import Image

from emoji_studio.common import read_json, write_json

PROJECT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = PROJECT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evaluation = load_script("evaluate_checkpoints.py")
review_builder = load_script("build_checkpoint_review.py")
review_analysis = load_script("analyze_checkpoint_review.py")
vast = load_script("vast_checkpoint_eval.py")


class CheckpointPlanTest(unittest.TestCase):
    def test_plan_is_concept_disjoint_balanced_and_locked(self):
        config, benchmark_path, pairs = evaluation.evaluation_plan(PROJECT)
        self.assertEqual(benchmark_path.name, "checkpoint-selection.json")
        self.assertEqual(len(pairs), 12)
        self.assertEqual(len({pair["pair_id"] for pair in pairs}), 12)
        self.assertEqual({pair["seed"] for pair in pairs}, {17, 29})
        self.assertEqual([row["step"] for row in config["checkpoints"]], [25, 50, 75, 100])
        self.assertEqual(len(pairs) * len(config["checkpoints"]), 48)


class CheckpointAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = {
            "authorization_id": "checkpointtest1",
            "authorized": True,
            "experiment": vast.EXPERIMENT,
            **vast.locked_hashes(),
            "max_total_dollars": 1.0,
            "max_hourly_dollars": 0.7,
            "max_elapsed_seconds": 3600,
            "expires_epoch": time.time() + 3600,
        }
        self.path = self.root / "authorization.json"
        write_json(self.path, self.auth)
        self.patch = patch.object(vast, "ARTIFACT_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_exact_single_use_authorization(self):
        self.assertEqual(vast.load_authorization(self.path), self.auth)
        write_json(self.root / "prior/allocation.json", {"authorization_id": "checkpointtest1"})
        with self.assertRaisesRegex(ValueError, "already used"):
            vast.load_authorization(self.path)

    def test_changed_lock_expiry_or_unsafe_cap_fails(self):
        for key, value in [
            ("benchmark_sha256", "0" * 64),
            ("expires_epoch", time.time() - 1),
            ("max_total_dollars", 1.01),
            ("max_elapsed_seconds", 1799),
        ]:
            changed = dict(self.auth)
            changed[key] = value
            write_json(self.path, changed)
            with self.assertRaises(ValueError):
                vast.load_authorization(self.path)


class CheckpointReviewTest(unittest.TestCase):
    def test_blind_review_has_all_pairings_and_decodes_complete_review(self):
        config, _, pairs = evaluation.evaluation_plan(PROJECT)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            rows = []
            for checkpoint in config["checkpoints"]:
                folder = output / f"step-{checkpoint['step']}"
                folder.mkdir()
                for pair in pairs:
                    path = folder / f"{pair['prompt_id']}-seed-{pair['seed']}.png"
                    Image.new("RGB", (4, 4), (checkpoint["step"], pair["seed"], 0)).save(path)
                    rows.append(
                        {
                            **pair,
                            "checkpoint_step": checkpoint["step"],
                            "adapter_sha256": checkpoint["sha256"],
                            "image": path.relative_to(output).as_posix(),
                            "image_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        }
                    )
            write_json(output / "report.json", {"status": "completed", "images": rows})
            result = review_builder.build(output)
            self.assertEqual(result["pairs"], 12)
            self.assertEqual(result["comparisons"], 72)
            mapping = read_json(output / "blind-map.json")
            html = (output / "checkpoint-review.html").read_text()
            self.assertNotIn("step-25", html)
            export = {
                "schema_version": 1,
                "review_id": mapping["review_id"],
                "reviews": {
                    row["id"]: {"preference": "tie", "left_severe": False, "right_severe": False}
                    for row in mapping["comparisons"]
                },
            }
            export_path = output / "review.json"
            write_json(export_path, export)
            selection = review_analysis.analyze(export_path, output)
            self.assertEqual(selection["recommended_step"], 25)
            self.assertEqual(selection["comparisons"], 72)


class CheckpointArchiveTest(unittest.TestCase):
    def test_final_archive_requires_all_verified_images(self):
        config = read_json(PROJECT / "configs/checkpoint-selection.json")
        files = {
            "checkpoint-eval.log": b"complete",
            "checkpoint-bootstrap.log": b"complete",
            "checkpoint.exit": b"0",
        }
        rows = []
        for index in range(config["expected_images"]):
            payload = f"image-{index}".encode()
            relative = f"step-{[25, 50, 75, 100][index % 4]}/image-{index}.png"
            files[f"runs/checkpoint-selection/{relative}"] = payload
            rows.append(
                {
                    "pair_id": f"pair-{index // 4}",
                    "checkpoint_step": [25, 50, 75, 100][index % 4],
                    "image": relative,
                    "image_sha256": hashlib.sha256(payload).hexdigest(),
                }
            )
        report = {
            "status": "completed",
            "config_sha256": vast.sha256(PROJECT / "configs/checkpoint-selection.json"),
            "benchmark_sha256": vast.sha256(PROJECT / "benchmarks/checkpoint-selection.json"),
            "images": rows,
        }
        files["runs/checkpoint-selection/report.json"] = json.dumps(report).encode()
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "results.tar.gz"
            with tarfile.open(target, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            self.assertEqual(len(vast.validate_final_archive(target)["images"]), 48)
            files["checkpoint.exit"] = b"1"
            with tarfile.open(target, "w:gz") as archive:
                for name, payload in files.items():
                    member = tarfile.TarInfo(name)
                    member.size = len(payload)
                    archive.addfile(member, io.BytesIO(payload))
            with self.assertRaises(tarfile.TarError):
                vast.validate_final_archive(target)


if __name__ == "__main__":
    unittest.main()
