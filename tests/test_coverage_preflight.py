import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from emoji_studio.coverage_preflight import canonical, preflight, sha256, verify_schedule


def fixture():
    rows = []
    for index in range(10):
        rows.append({
            "asset_id": f"asset-{index}", "concept": "apple" if index < 7 else "hand",
            "tone": "Default" if index < 8 else "Light", "family_id": f"family-{index}",
            "sha256": sha256(f"export-{index}".encode()),
            "source_sha256": sha256(f"source-{index}".encode()),
            "pixel_sha256": sha256(f"pixels-{index}".encode()),
            "caption": f"fixture caption {index}", "caption_status": "synthetic_reviewed",
            "included": True, "split": "train" if index < 9 else "validation",
        })
    return {"rows": rows}


class CoveragePreflightTest(unittest.TestCase):
    def run_plan(self, manifest=None, **kwargs):
        raw = canonical(manifest or fixture())
        options = {"expected_hash": sha256(raw), "seed": 29, "draws": 12}
        options.update(kwargs)
        return preflight(raw, **options)

    def test_passes_cover_every_asset_before_repeating(self):
        for size in (9, 10, 18, 23, 36):
            with self.subTest(size=size):
                plan = self.run_plan(draws=size, accumulation=1)
                sequence = plan["schedule"]["draws"]
                eligible = {f"asset-{i}" for i in range(9)}
                self.assertEqual(set(sequence), eligible)
                for start in range(0, size, 9):
                    segment = sequence[start:start + 9]
                    self.assertEqual(len(set(segment)), len(segment))
                    if len(segment) == 9:
                        self.assertEqual(set(segment), eligible)
                counts = Counter(sequence)
                self.assertLessEqual(max(counts.values()) - min(counts.values()), 1)
                self.assertFalse(plan["training_authorized"])

    def test_deterministic_bytes_and_row_order_independent_draws(self):
        manifest = fixture()
        before = copy.deepcopy(manifest)
        first = self.run_plan(manifest)
        self.assertEqual(manifest, before)
        self.assertEqual(canonical(first), canonical(self.run_plan(manifest)))
        manifest["rows"].reverse()
        reversed_plan = self.run_plan(manifest)
        self.assertEqual(first["schedule"]["draws"], reversed_plan["schedule"]["draws"])
        self.assertNotEqual(first["manifest_sha256"], reversed_plan["manifest_sha256"])
        self.assertEqual(before, fixture())
        self.assertEqual(first["schedule_sha256"], sha256(canonical(first["schedule"])))
        self.assertNotEqual(first["schedule"]["draws"], self.run_plan(seed=30)["schedule"]["draws"])

    def test_supplied_schedule_rejects_drift_leakage_and_unauthorized_repetition(self):
        raw = canonical(fixture())
        options = {"expected_hash": sha256(raw), "seed": 29, "draws": 12}
        plan = preflight(raw, **options)
        self.assertEqual(verify_schedule(plan["schedule"], raw, **options), plan["schedule_sha256"])
        for value in ("asset-9", "unknown", plan["schedule"]["draws"][1]):
            with self.subTest(value=value):
                changed = copy.deepcopy(plan["schedule"])
                changed["draws"][0] = value
                with self.assertRaises(ValueError):
                    verify_schedule(changed, raw, **options)
        for field, value in (("seed", 30), ("manifest_sha256", "0" * 64),
                             ("policy", "other-policy")):
            with self.subTest(field=field):
                changed = {**plan["schedule"], field: value}
                with self.assertRaises(ValueError):
                    verify_schedule(changed, raw, **options)
        with self.assertRaises(ValueError):
            verify_schedule(plan["schedule"], raw, **{**options, "draws": 8})

    def test_bucket_interleaving_does_not_multiply_small_groups(self):
        plan = self.run_plan(draws=9, accumulation=1)
        sequence = plan["schedule"]["draws"]
        rows = {row["asset_id"]: row for row in fixture()["rows"]}
        self.assertEqual(len({(rows[key]["concept"], rows[key]["tone"]) for key in sequence[:3]}), 3)
        self.assertEqual({b["concept"] + b["tone"]: b["draws"]
                          for b in plan["coverage"]["bucket_draws"]},
                         {"appleDefault": 7, "handDefault": 1, "handLight": 1})

    def test_full_claim_insufficient_budget_refuses_schedule_without_increasing_draws(self):
        result = self.run_plan(draws=8)
        self.assertEqual(result["status"], "blocked")
        self.assertIn("draw_budget_below_full_coverage", result["blockers"])
        self.assertIsNone(result["schedule"])
        self.assertEqual(result["draw_budget"], 8)
        self.assertEqual(result["arithmetic"]["minimum_aligned_full_coverage_draws"], 12)

    def test_partial_diagnostic_reports_omitted_assets_and_zero_counts(self):
        result = self.run_plan(draws=4, full_coverage=False)
        self.assertEqual(result["status"], "prototype_passed")
        self.assertFalse(result["full_coverage_claim"])
        self.assertEqual(result["coverage"]["unique_assets"], 4)
        self.assertEqual(len(result["coverage"]["omitted_assets"]), 5)
        self.assertEqual(result["coverage"]["minimum_repeats"], 0)
        self.assertEqual(len(result["coverage"]["asset_draws"]), 9)

    def test_optimizer_arithmetic_never_pads_or_drops_draws(self):
        result = self.run_plan(draws=10, batch_size=2, accumulation=2)
        self.assertIn("draw_budget_not_whole_optimizer_steps", result["blockers"])
        self.assertEqual(result["arithmetic"]["leftover_draws"], 2)
        self.assertIsNone(result["schedule"])

    def test_missing_or_validation_only_buckets_block(self):
        result = self.run_plan(required_buckets=[("high five", "Default"), ("hand", "Dark")])
        self.assertEqual(len(result["missing_required_buckets"]), 2)
        self.assertIsNone(result["schedule"])
        manifest = fixture()
        manifest["rows"][-1]["concept"] = "held-out"
        self.assertIn("missing_required_buckets", self.run_plan(
            manifest, required_buckets=[("held-out", "Light")],
        )["blockers"])

    def test_required_bucket_present_but_undrawn_blocks_partial_claim(self):
        result = self.run_plan(draws=1, accumulation=1, full_coverage=False,
                               required_buckets=[("apple", "Default"), ("hand", "Light")])
        self.assertIn("required_buckets_not_drawn", result["blockers"])
        self.assertIsNone(result["schedule"])

    def test_excluded_assets_and_holdouts_never_sampled(self):
        manifest = fixture()
        manifest["rows"][0]["included"] = False
        result = self.run_plan(manifest, draws=16)
        self.assertEqual(result["excluded_assets"], 1)
        self.assertEqual(result["validation_assets"], 1)
        self.assertNotIn("asset-0", result["schedule"]["draws"])
        self.assertNotIn("asset-9", result["schedule"]["draws"])

    def test_cross_split_hash_and_family_leaks_block(self):
        for field in ("family_id", "sha256", "source_sha256", "pixel_sha256"):
            with self.subTest(field=field):
                manifest = fixture()
                manifest["rows"][-1][field] = manifest["rows"][0][field]
                result = self.run_plan(manifest)
                self.assertIn("train_validation_leakage", result["blockers"])
                self.assertEqual(result["leakage_counts"][field], 1)

    def test_review_status_is_explicit_not_inferred_or_promoted(self):
        result = self.run_plan(required_caption_status="human_reviewed")
        self.assertIn("required_caption_status_not_met", result["blockers"])
        self.assertEqual(result["caption_status_counts"], {"synthetic_reviewed": 9})
        self.assertEqual(self.run_plan(required_caption_status="synthetic_reviewed")["status"],
                         "prototype_passed")

    def test_bad_manifest_hash_duplicate_ids_keys_and_metadata_rejected(self):
        with self.assertRaises(ValueError):
            self.run_plan(expected_hash="0" * 64)
        for field, value in (("asset_id", "asset-0"), ("included", "true"),
                             ("split", "test"), ("source_sha256", None), ("caption", "")):
            with self.subTest(field=field):
                manifest = fixture()
                manifest["rows"][-1][field] = value
                with self.assertRaises(ValueError):
                    self.run_plan(manifest)
        raw = b'{"rows": [], "rows": []}'
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            preflight(raw, expected_hash=sha256(raw), seed=0, draws=4)

    def test_empty_pool_and_bad_options_fail_closed(self):
        manifest = fixture()
        for row in manifest["rows"]:
            row["split"] = "validation"
        self.assertIn("empty_training_pool", self.run_plan(manifest)["blockers"])
        for options in ({"seed": True}, {"draws": 0}, {"draws": 1_000_001},
                        {"accumulation": 0}, {"full_coverage": "yes"},
                        {"required_buckets": ["hand"]}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_plan(**options)

    def test_cli_is_read_only_and_returns_blocked_exit_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            raw = canonical(fixture())
            path.write_bytes(raw)
            command = [sys.executable, "-m", "emoji_studio.coverage_preflight", str(path),
                       "--manifest-sha256", sha256(raw), "--seed", "29", "--draws", "8"]
            result = subprocess.run(command, capture_output=True, text=True, timeout=10,
                                    env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"})
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertEqual(json.loads(result.stdout)["status"], "blocked")
            self.assertEqual(path.read_bytes(), raw)
            self.assertEqual(list(Path(temporary).iterdir()), [path])

    def test_separate_interpreter_reproduces_identical_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "manifest.json"
            raw = canonical(fixture())
            path.write_bytes(raw)
            command = [sys.executable, "-m", "emoji_studio.coverage_preflight", str(path),
                       "--manifest-sha256", sha256(raw), "--seed", "29", "--draws", "12"]
            outputs = [subprocess.run(command, capture_output=True, check=True, timeout=10).stdout
                       for _ in range(2)]
            self.assertEqual(outputs[0], outputs[1])
            self.assertEqual(outputs[0], canonical(self.run_plan()))
