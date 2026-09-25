import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from emoji_studio.common import read_json, write_json
from emoji_studio.interactions import CONTROL_GESTURES, REVIEW_CHECKS, interaction_preflight

ROOT = Path(__file__).resolve().parents[1]


class InteractionDataTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        benchmark = self.root / "benchmarks/high-five-v1.json"
        write_json(benchmark, read_json(ROOT / "benchmarks/high-five-v1.json"))
        self.path = self.root / "manifest.json"
        rows = []
        for index in range(36):
            path = self.root / f"{index}.png"
            Image.new("RGB", (32, 32), (index, 0, 0)).save(path)
            checksum = hashlib.sha256(path.read_bytes()).hexdigest()
            rows.append({
                "id": str(index), "path": path.name, "sha256": checksum,
                "decision": "keep", "split": "validation" if 24 <= index < 32 else "train",
                "gesture": "high_five" if index < 32 else CONTROL_GESTURES[index - 32],
                "lineage_group": str(index), "pose_group": str(index),
                "tone_pair": [["light", "medium"], ["medium", "dark"]][index % 2],
                "caption": f"Reviewed fixture caption {index}", "allow_low_resolution": True,
                "source": {"kind": "licensed_artwork", "origin": "test fixture",
                           "creator": "test", "terms": "fixture", "terms_evidence": "fixture",
                           "training_permitted": True, "redistribution_permitted": True},
                "review": {"reviewer": "test", "image_sha256": checksum,
                           **dict.fromkeys(REVIEW_CHECKS, True),
                           "palm_contact": True, "wrists_separated": True},
            })
        self.document = {"schema_version": 1, "rows": rows,
                         "benchmark_sha256": hashlib.sha256(benchmark.read_bytes()).hexdigest()}

    def check(self):
        write_json(self.path, self.document)
        return interaction_preflight(self.root, self.path)

    def reasons(self):
        return {reason for issue in self.check()["blocking_issues"] for reason in issue["reasons"]}

    def test_valid_review_is_ready_but_does_not_authorize_training(self):
        result = self.check()
        self.assertTrue(result["data_ready"], result)
        self.assertFalse(result["training_authorized"])
        self.assertEqual(result["accepted_counts"]["train/high_five"], 24)

    def test_recolored_or_edited_pose_cannot_cross_splits(self):
        self.document["rows"][24]["lineage_group"] = "0"
        self.assertIn("pose_or_lineage_split_leakage", self.reasons())

    def test_unknown_permissions_and_stale_review_block(self):
        row = self.document["rows"][0]
        row["source"]["training_permitted"] = "yes"
        row["review"]["image_sha256"] = "stale"
        self.assertIn("unverified_source_permissions", self.reasons())
        self.assertIn("missing_or_stale_review", self.reasons())

    def test_evaluation_images_and_exact_prompts_block(self):
        row = self.document["rows"][0]
        write_json(self.root / "runs/high-five-baseline-v1/report.json",
                   {"images": [{"image_sha256": row["sha256"]}]})
        row["caption"] = read_json(self.root / "benchmarks/high-five-v1.json")["prompts"][0]["prompt"]
        self.assertIn("evaluation_image_leakage", self.reasons())
        self.assertIn("evaluation_prompt_leakage", self.reasons())
        row["caption"] += ", rendered in an emoji style"
        self.assertIn("evaluation_prompt_leakage", self.reasons())

    def test_insufficient_data_and_anatomy_failure_block(self):
        self.document["rows"][0]["review"]["anatomy_correct"] = False
        reasons = self.reasons()
        self.assertIn("visual_review_incomplete_or_failed", reasons)
        self.assertIn("need_24_reviewed_high_fives", reasons)

    def test_unreviewed_candidates_do_not_count(self):
        for row in self.document["rows"]:
            row["decision"] = "pending"
        result = self.check()
        self.assertEqual(result["accepted_counts"], {})
        self.assertFalse(result["data_ready"])
