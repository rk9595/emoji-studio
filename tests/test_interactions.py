import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

from emoji_studio.common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("interactions", ROOT / "scripts/evaluate_interactions.py")
interactions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(interactions)


class InteractionBaselineTest(unittest.TestCase):
    def test_matched_conditions_and_locked_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            adapter = root / "adapter.safetensors"
            adapter.write_bytes(b"fixture")
            serving = read_json(ROOT / "configs/serving.json")
            serving.update(adapter_path=adapter.name, adapter_sha256=interactions.sha256(adapter))
            write_json(root / "configs/serving.json", serving)
            write_json(root / "benchmarks/high-five-v1.json",
                       read_json(ROOT / "benchmarks/high-five-v1.json"))
            plan = interactions.make_plan(root)
            self.assertEqual(len(plan["jobs"]), 32)
            for base, styled in zip(plan["jobs"][:16], plan["jobs"][16:], strict=True):
                self.assertEqual(base["prompt"], styled["prompt"])
                self.assertEqual(base["seed"], styled["seed"])
                self.assertEqual(base["criteria"], styled["criteria"])
                self.assertNotEqual(base["variant"], styled["variant"])
            changed = copy.deepcopy(plan)
            changed["jobs"][0]["seed"] = 5
            with self.assertRaises(ValueError):
                interactions.verify_plan(changed, root)
            adapter.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "checksum"):
                interactions.verify_plan(plan, root)

    def test_resume_rejects_changed_image_or_job(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)
            (output / "images").mkdir()
            path = output / "images/base-example-17.png"
            path.write_bytes(b"fixture")
            job = {"id": "base-example-17", "seed": 17}
            row = {"job": job, "image_sha256": interactions.sha256(path)}
            self.assertTrue(interactions.completed(output, row, job))
            self.assertFalse(interactions.completed(output, row, {**job, "seed": 29}))
            path.write_bytes(b"corrupt")
            self.assertFalse(interactions.completed(output, row, job))
