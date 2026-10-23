import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "check_amd_api_smoke_plan", ROOT / "scripts/check_amd_api_smoke_plan.py"
)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class AmdApiSmokePlanTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        for relative in checker.FILES | {checker.PLAN}:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.plan_path = self.root / checker.PLAN
        self.plan = json.loads(self.plan_path.read_text())

    def save_plan(self):
        self.plan_path.write_text(json.dumps(self.plan))

    def test_real_repository_plan_is_prepared_only(self):
        result = checker.check_plan(ROOT)
        self.assertEqual(result["status"], "prepared_only")
        self.assertFalse(result["execution_authorized"])
        self.assertEqual(result["locked_files_verified"], 18)
        self.assertEqual(result["blockers"], checker.BLOCKERS)

    def test_missing_private_adapter_is_explicit_not_execution_ready(self):
        result = checker.check_plan(self.root)
        self.assertEqual(result["adapter"], "missing_private_artifact")
        self.assertFalse(result["execution_authorized"])

    def test_source_drift_rejected(self):
        source = self.root / "src/emoji_studio/durable_api.py"
        source.write_text(source.read_text() + "\n# changed\n")
        with self.assertRaisesRegex(ValueError, "Locked file drift"):
            checker.check_plan(self.root)

    def test_authority_budget_runtime_and_campaign_changes_rejected(self):
        changes = {
            "execution_authorized": True,
            "approved_allowance_usd": 3,
            "plan_id": "amd-comparison-v1",
            "status": "ready",
            "schema_version": True,
            "blockers": [],
            "network": {"bind": "0.0.0.0"},
            "runtime": {"status": "resolved", "oci_digest": "sha256:pretend"},
            "proposed_limits": {**self.plan["proposed_limits"], "allocations": 2},
            "requests": [{"prompt": "more work", "seed": 9}],
        }
        original = self.plan.copy()
        for key, value in changes.items():
            with self.subTest(key=key):
                self.plan = {**original, key: value}
                self.save_plan()
                with self.assertRaisesRegex(ValueError, "Prepared-only constraint changed"):
                    checker.check_plan(self.root)

    def test_inventory_and_unsafe_path_rejected(self):
        self.plan["source_sha256"]["../outside"] = "0" * 64
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "inventory"):
            checker.check_plan(self.root)
        for relative in ("../outside", "/outside"):
            with self.subTest(relative=relative), self.assertRaisesRegex(ValueError, "Unsafe"):
                checker.safe_path(self.root, relative)

    def test_symlink_rejected_even_when_bytes_match(self):
        target = self.root / "src/emoji_studio/common.py"
        target.unlink()
        target.symlink_to(ROOT / "src/emoji_studio/common.py")
        with self.assertRaisesRegex(ValueError, "Symlinks"):
            checker.check_plan(self.root)

    def test_bad_private_adapter_rejected(self):
        target = self.root / checker.ADAPTER
        target.parent.mkdir(parents=True)
        target.write_bytes(b"not the reviewed adapter")
        with self.assertRaisesRegex(ValueError, "adapter checksum"):
            checker.check_plan(self.root)

    def test_serving_metadata_mismatch_rejected(self):
        self.plan["serving"]["selected_step"] = 500
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "Serving identity"):
            checker.check_plan(self.root)

    def test_duplicate_json_keys_rejected(self):
        text = self.plan_path.read_text()
        self.plan_path.write_text(text.replace('"execution_authorized": false',
                                              '"execution_authorized": true, '
                                              '"execution_authorized": false'))
        with self.assertRaisesRegex(ValueError, "Duplicate JSON"):
            checker.check_plan(self.root)

    def test_receipt_cannot_be_relocked_without_matching_sources(self):
        target = self.root / "reports/local-http-smoke.json"
        receipt = json.loads(target.read_text())
        receipt["source_sha256"]["durable_api.py"] = "0" * 64
        target.write_text(json.dumps(receipt))
        self.plan["source_sha256"]["reports/local-http-smoke.json"] = checker.digest(target)
        self.save_plan()
        with self.assertRaisesRegex(ValueError, "Local smoke source drift"):
            checker.check_plan(self.root)
