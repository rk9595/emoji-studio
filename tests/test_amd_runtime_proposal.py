import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("runtime_checker", ROOT / "scripts/check_amd_runtime_proposal.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class RuntimeProposalTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for relative in checker.FILES | {"configs/amd-runtime-proposal.json"}:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        self.path = self.root / "configs/amd-runtime-proposal.json"
        self.proposal = json.loads(self.path.read_text())

    def save(self):
        self.path.write_text(json.dumps(self.proposal))

    def rehash(self, relative):
        self.proposal["files_sha256"][relative] = checker.digest((self.root / relative).read_bytes())
        self.save()

    def test_repository_metadata_and_overlay_integrity_only(self):
        result = checker.check(ROOT)
        self.assertEqual(result["status"], "prepared_only")
        self.assertFalse(result["execution_authorized"])
        self.assertFalse(result["runtime_validated"])
        self.assertEqual(result["overlay_packages"], 45)
        self.assertEqual(result["base"]["compressed_layer_bytes"], 12763439494)
        self.assertFalse(result["base"]["layers_downloaded"])

    def test_authority_and_completion_claims_rejected(self):
        original = self.proposal.copy()
        for key, value in (("execution_authorized", True), ("runtime_validated", True),
                           ("approved_allowance_usd", 3), ("derived_image_digest", "sha256:any"),
                           ("status", "ready"), ("schema_version", True), ("blockers", [])):
            with self.subTest(key=key):
                self.proposal = {**original, key: value}
                self.save()
                with self.assertRaises(ValueError):
                    checker.check(self.root)

    def test_input_drift_fails_without_relocking(self):
        path = self.root / "configs/amd-overlay-linux-py312.txt"
        path.write_text(path.read_text() + "# changed\n")
        with self.assertRaisesRegex(ValueError, "drift"):
            checker.check(self.root)

    def test_rehashed_registry_bytes_cannot_bless_wrong_digest(self):
        relative = "reports/amd-runtime-registry.json"
        path = self.root / relative
        receipt = json.loads(path.read_text())
        receipt["config_json"] += " "
        path.write_text(json.dumps(receipt))
        self.rehash(relative)
        with self.assertRaisesRegex(ValueError, "Config digest"):
            checker.check(self.root)

    def test_gpu_or_cuda_packages_cannot_enter_overlay(self):
        for name in ("torch", "torchvision", "triton", "nvidia-cublas-cu12", "cuda-python"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "base-provided"):
                checker.lock_packages(f"{name}==1.0 --hash=sha256:" + "a" * 64)

    def test_missing_hash_unpinned_duplicate_or_options_rejected(self):
        for value in ("pillow==12.2.0", "pillow>=12", "--index-url https://example.com",
                      "pillow==12 --hash=sha256:" + "a" * 64 + "\npillow==12 --hash=sha256:" + "a" * 64):
            with self.subTest(value=value), self.assertRaises(ValueError):
                checker.lock_packages(value)

    def test_rehashed_exclusion_change_is_rejected(self):
        relative = "configs/amd-base-provided.in"
        path = self.root / relative
        path.write_text(path.read_text().replace("torch\n", ""))
        self.rehash(relative)
        with self.assertRaisesRegex(ValueError, "exclusions"):
            checker.check(self.root)

    def test_rehashed_direct_pin_change_is_rejected(self):
        relative = "configs/amd-overlay.in"
        path = self.root / relative
        path.write_text(path.read_text().replace("diffusers==0.40.0", "diffusers==0.41.0"))
        self.rehash(relative)
        with self.assertRaisesRegex(ValueError, "dependency pin"):
            checker.check(self.root)

    def test_symlinks_and_inventory_changes_rejected(self):
        target = self.root / "configs/amd-overlay.in"
        target.unlink()
        target.symlink_to(ROOT / "configs/amd-overlay.in")
        with self.assertRaisesRegex(ValueError, "Symlink"):
            checker.check(self.root)
        self.proposal["files_sha256"]["../outside"] = "a" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "inventory"):
            checker.check(self.root)

    def test_installed_claim_is_rejected_without_evidence(self):
        self.proposal["overlay"]["installed"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "installation claim"):
            checker.check(self.root)
