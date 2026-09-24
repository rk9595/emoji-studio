import hashlib
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from emoji_studio.common import digest, read_json, write_json
from emoji_studio.curation import create_curation, training_preflight
from emoji_studio.training_data import export_training, verify_export


class CurationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.references = []
        for index, color in enumerate(["red", "green"]):
            path = self.root / f"asset-{index}.png"
            Image.new("RGB", (32, 32), color).save(path)
            self.references.append(
                {
                    "id": str(index),
                    "concept": f"Concept {index}",
                    "concept_family": str(index),
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "caption": f"Draft {index}",
                    "license": "MIT",
                }
            )
        write_json(self.root / "data/references.json", self.references)
        (self.root / "LICENSE").write_text("MIT fixture notice")
        write_json(self.root / "data/asset-audit.json", {"license_path": "LICENSE"})
        self.config = self.root / "config.json"
        write_json(
            self.config,
            {
                "resolution": 64,
                "allowed_source_licenses": ["MIT"],
                "minimum_split_counts": {"train": 1, "validation": 1},
            },
        )
        self.path = self.root / "curation.json"
        create_curation(self.root, self.path)

    def approve(self):
        document = read_json(self.path)
        document["reference_manifest_hash"] = digest(self.references)
        for row, split in zip(document["rows"], ["train", "validation"], strict=True):
            row.update(
                decision="keep",
                caption_reviewed=True,
                reviewer="test reviewer",
                split=split,
                allow_low_resolution=True,
            )
        write_json(self.path, document)
        return document

    def check(self):
        return training_preflight(self.root, self.path, self.config)

    def test_drafts_block_and_template_never_overwrites(self):
        self.assertFalse(self.check()["data_ready"])
        with self.assertRaises(ValueError):
            create_curation(self.root, self.path)

    def test_reviewed_data_can_pass_without_authorizing_training(self):
        self.approve()
        result = self.check()
        self.assertTrue(result["data_ready"])
        self.assertEqual(result["accepted_counts"], {"train": 1, "validation": 1})
        self.assertFalse(result["training_authorized"])

    def test_low_resolution_requires_explicit_boolean(self):
        document = self.approve()
        document["rows"][0]["allow_low_resolution"] = "yes"
        write_json(self.path, document)
        self.assertIn(
            "low_resolution_not_acknowledged", self.check()["blocking_issues"][0]["reasons"]
        )

    def test_concept_family_split_leakage_blocks(self):
        self.references[1]["concept_family"] = self.references[0]["concept_family"]
        write_json(self.root / "data/references.json", self.references)
        self.approve()
        self.assertIn("concept_family_leakage", self.check()["blocking_issues"][0]["reasons"])

    def test_corrupt_source_blocks(self):
        self.approve()
        (self.root / "asset-0.png").write_bytes(b"changed")
        self.assertIn("source_checksum_failed", self.check()["blocking_issues"][0]["reasons"])

    def test_stale_manifest_rejected(self):
        self.references[0]["caption"] = "Changed upstream metadata"
        write_json(self.root / "data/references.json", self.references)
        with self.assertRaisesRegex(ValueError, "different reference manifest"):
            self.check()

    def test_missing_decisions_and_license_block(self):
        document = self.approve()
        document["rows"].pop()
        write_json(self.path, document)
        (self.root / "LICENSE").unlink()
        reasons = [
            reason for issue in self.check()["blocking_issues"] for reason in issue["reasons"]
        ]
        self.assertIn("reference_decisions_missing", reasons)
        self.assertIn("source_license_notice_missing", reasons)

    def export(self, name="export"):
        return export_training(self.root, self.path, self.config, self.root / name)

    def test_export_blocks_pending_and_never_overwrites(self):
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.export()
        self.assertFalse((self.root / "export").exists())
        self.approve()
        self.export()
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.export()

    def test_export_deterministic_separate_splits_and_captions(self):
        import json

        self.approve()
        first = self.export()
        second = self.export("export-2")
        self.assertEqual(first["export_hash"], second["export_hash"])
        self.assertFalse(first["training_authorized"])
        manifest = verify_export(self.root / "export")
        self.assertEqual(manifest["counts"], {"train": 1, "validation": 1})
        for row in manifest["rows"]:
            metadata = self.root / "export" / row["split"] / "metadata.jsonl"
            record = json.loads(metadata.read_text())
            self.assertEqual(record["text"], row["caption"])
            self.assertEqual(record["file_name"], Path(row["path"]).name)
        self.assertEqual(
            (self.root / "export/LICENSE.source.txt").read_text(), "MIT fixture notice"
        )

    def test_export_composites_alpha_and_keeps_original(self):
        source = self.root / "asset-0.png"
        image = Image.new("RGBA", (32, 32), (255, 0, 0, 128))
        image.putpixel((0, 0), (0, 0, 0, 0))
        image.save(source)
        original = source.read_bytes()
        self.references[0]["sha256"] = hashlib.sha256(original).hexdigest()
        write_json(self.root / "data/references.json", self.references)
        self.path.unlink()
        create_curation(self.root, self.path)
        self.approve()
        config = read_json(self.config)
        config["resolution"] = 32
        write_json(self.config, config)
        self.export()
        manifest = verify_export(self.root / "export")
        target = next(row for row in manifest["rows"] if row["asset_id"] == "0")
        with Image.open(self.root / "export" / target["path"]) as rendered:
            self.assertEqual(rendered.mode, "RGB")
            self.assertEqual(rendered.getpixel((0, 0)), (255, 255, 255))
            self.assertEqual(rendered.getpixel((16, 16)), (255, 127, 127))
        self.assertEqual(source.read_bytes(), original)

    def test_export_verification_rejects_corruption_and_extra_images(self):
        self.approve()
        self.export()
        extra = self.root / "export/train/extra.png"
        extra.write_bytes(b"unexpected")
        with self.assertRaisesRegex(ValueError, "unexpected files"):
            verify_export(self.root / "export")
        extra.unlink()
        (self.root / "export/train/metadata.jsonl").write_text("changed")
        with self.assertRaisesRegex(ValueError, "checksum failed"):
            verify_export(self.root / "export")

    def test_export_rejects_outside_project(self):
        self.approve()
        with self.assertRaisesRegex(ValueError, "inside the project"):
            export_training(self.root, self.path, self.config, self.root.parent / "outside")


if __name__ == "__main__":
    unittest.main()
