import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


compare = load("amd_compare")
with patch.dict(sys.modules, {"amd_compare": compare}):
    sheets = load("build_amd_review_sheets")


class ReviewSummaryTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.output = Path(self.directory.name)
        self.observations_path = self.output / "observations.json"
        self.conditions = [f"condition-{index}" for index in range(6)]
        self.config = {"conditions": [{"id": name} for name in self.conditions]}
        self.pairs = [{"pair_id": "pair"}]
        self.lock = {"config_sha256": "recipe"}
        self.report = {"images": [
            {"pair_id": "pair", "condition": name, "sha256": str(index)}
            for index, name in enumerate(self.conditions)
        ]}
        compare.save(self.output / "report.json", self.report)
        self.mapping = {
            **self.lock, "source_report_sha256": compare.sha256(self.output / "report.json"),
            "pairs": {"pair": {label: {"condition": name, "image_sha256": str(index)}
                               for index, (label, name) in enumerate(zip("ABCDEF", self.conditions))}},
        }
        self.observations = {"label_order": "ABCDEF", "reviewer": "AI", "method": "diagnostic",
                             "scoring": {}, "observations": {"pair": {"scores": [0, 1, 2, 0, 1, 2]}}}
        self.plan_patch = patch.object(sheets, "plan", return_value=(self.config, self.pairs, self.lock))
        self.verify_patch = patch.object(sheets, "verify", return_value=self.report)
        self.plan_patch.start()
        self.verify_patch.start()
        self.addCleanup(self.plan_patch.stop)
        self.addCleanup(self.verify_patch.stop)

    def summarize(self):
        compare.save(self.output / "sheets/map.json", self.mapping)
        compare.save(self.observations_path, self.observations)
        return sheets.summarize(self.output, self.observations_path)

    def test_counts_and_provenance(self):
        result = self.summarize()
        self.assertEqual(result["verified_images"], 6)
        self.assertEqual(result["conditions"]["condition-2"]["major_details_met"], 1)
        self.assertEqual(result["observations_sha256"], compare.sha256(self.observations_path))

    def test_missing_observation_rejected(self):
        self.observations["observations"] = {}
        with self.assertRaisesRegex(ValueError, "Incomplete"):
            self.summarize()

    def test_stale_report_rejected(self):
        self.mapping["source_report_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "source report"):
            self.summarize()

    def test_corrupt_mapping_rejected(self):
        self.mapping["pairs"]["pair"]["A"]["image_sha256"] = "wrong"
        with self.assertRaisesRegex(ValueError, "image mapping"):
            self.summarize()

    def test_boolean_or_out_of_range_score_rejected(self):
        for score in (True, -1, 3, "2"):
            self.observations["observations"]["pair"]["scores"][0] = score
            with self.assertRaisesRegex(ValueError, "Invalid labels or scores"):
                self.summarize()
