import importlib.util
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "training_preflight", Path(__file__).resolve().parents[1] / "ops/amd_training_preflight.py")
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


class TrainingPreflightTest(unittest.TestCase):
    def test_real_provider_conflict_and_corrected_version(self):
        records = [{"name": "langchain-core", "version": "0.3.83",
                    "requires": ["packaging<26.0.0,>=23.2.0"]},
                   {"name": "packaging", "version": "25.0"}]
        bad = preflight.audit(records, {"packaging": "26.3"})
        self.assertEqual(bad["status"], "blocked")
        self.assertEqual(bad["conflicts"][0]["package"], "langchain-core")
        self.assertEqual(preflight.audit(records, {"packaging": "25.0"})["conflicts"], [])

    def test_replaced_metadata_is_not_applied_to_new_version(self):
        records = [{"name": "changed", "version": "1", "requires": ["missing<2"]}]
        self.assertEqual(preflight.audit(records, {"changed": "2"})["conflicts"], [])
        self.assertEqual(len(preflight.audit(records, {})["conflicts"]), 1)

    def test_platform_and_optional_extra_markers(self):
        records = [{"name": "package", "version": "1", "requires": [
            'missing; sys_platform == "win32"', 'optional; extra == "gpu"']}]
        self.assertEqual(preflight.audit(records, {}, {"sys_platform": "linux"})["conflicts"], [])
        self.assertEqual(len(preflight.audit(records, {}, {"sys_platform": "win32"})["conflicts"]), 1)

    def test_rocm_local_version_satisfies_public_torch_pin(self):
        records = [{"name": "torchvision", "version": "0.25.0", "requires": ["torch==2.10.0"]},
                   {"name": "torch", "version": "2.10.0+rocm7.2"}]
        self.assertEqual(preflight.audit(records, {})["conflicts"], [])

    def test_duplicate_distribution_and_gpu_overlay_rejected(self):
        with self.assertRaises(ValueError):
            preflight.audit([{"name": "my-package", "version": "1"},
                             {"name": "my_package", "version": "1"}], {})
        for text in ("torch==2.10.0 --hash=sha256:" + "a" * 64, "packaging>=25"):
            with self.assertRaises(ValueError):
                preflight.overlay_versions(text)

    def test_candidate_changes_only_the_confirmed_conflict(self):
        root = Path(__file__).resolve().parents[1]
        old = preflight.overlay_versions((root / "configs/amd-training-overlay-linux-py312.txt").read_text())
        new = preflight.overlay_versions((root / "configs/amd-training-overlay-linux-py312-v2.txt").read_text())
        self.assertEqual(len(new), 74)
        self.assertEqual(new, old | {"packaging": "25.0"})


if __name__ == "__main__":
    unittest.main()
