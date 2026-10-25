import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


builder = load("builder", "scripts/prepare_amd_build_context.py")
audit = load("audit", "ops/runtime/audit_runtime.py")


class BuilderTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name).resolve()

    def copy_inputs(self):
        root = self.directory / "repo"
        proposal, _, _ = builder.verify(ROOT)
        for name in set(proposal["files_sha256"]) | {builder.RECIPE}:
            destination = root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / name, destination)
        return root

    def test_staging_copies_only_reviewed_public_inputs_without_building(self):
        output = self.directory / "context"
        result = builder.stage(output)
        proposal, app, raw = builder.verify()
        self.assertFalse(result["image_built"])
        self.assertFalse(result["gpu_execution_authorized"])
        actual = {str(p.relative_to(output / "app")) for p in (output / "app").rglob("*") if p.is_file()}
        self.assertEqual(actual, app)
        for name in app:
            self.assertEqual((output / "app" / name).read_bytes(), raw[name])
        self.assertFalse((output / "app/runs").exists())
        self.assertFalse((output / "app/.git").exists())
        self.assertEqual((output / "Dockerfile").read_bytes(), raw["ops/runtime/Dockerfile"])
        self.assertEqual(json.loads((output / "builder-proposal.json").read_text()), proposal)

    def test_existing_destination_is_never_overwritten(self):
        output = self.directory / "context"
        builder.stage(output)
        with self.assertRaises(FileExistsError):
            builder.stage(output)

    def test_input_drift_rejected_before_output_creation(self):
        root = self.copy_inputs()
        (root / "src/emoji_studio/smoke_export.py").write_text("changed")
        output = self.directory / "context"
        with self.assertRaisesRegex(ValueError, "input changed"):
            builder.stage(output, root)
        self.assertFalse(output.exists())

    def test_input_symlink_rejected(self):
        root = self.copy_inputs()
        path = root / "ops/runtime/Dockerfile"
        path.unlink()
        path.symlink_to(ROOT / "ops/runtime/Dockerfile")
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            builder.verify(root)

    def test_output_symlink_parent_rejected(self):
        alias = self.directory / "alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "Symlinked"):
            builder.stage(alias / "context")

    def test_paid_gpu_or_changed_bounds_rejected(self):
        root = self.copy_inputs()
        path = root / builder.RECIPE
        original = json.loads(path.read_text())
        for key, value in (("paid_execution_authorized", True), ("gpu_execution_authorized", True),
                           ("minimum_free_gib", 10), ("max_minutes", 90), ("target", "linux/arm64")):
            with self.subTest(key=key):
                path.write_text(json.dumps({**original, key: value}))
                with self.assertRaises(ValueError):
                    builder.verify(root)

    def test_missing_and_extra_inventory_entries_rejected(self):
        root = self.copy_inputs()
        path = root / builder.RECIPE
        original = json.loads(path.read_text())
        for change in ("missing", "extra"):
            proposal = json.loads(json.dumps(original))
            if change == "missing":
                proposal["files_sha256"].pop("ops/runtime/Dockerfile")
            else:
                proposal["files_sha256"]["runs/private.safetensors"] = "a" * 64
            path.write_text(json.dumps(proposal))
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, "inventory"):
                builder.verify(root)

    def test_cpu_guard_refuses_mac_before_creating_audit_output(self):
        from unittest.mock import patch

        with patch.object(audit.sys, "argv", ["audit", "base"]), \
                patch.object(audit.platform, "system", return_value="Darwin"), \
                patch.object(audit, "inventory") as inventory:
            with self.assertRaisesRegex(RuntimeError, "Linux/amd64"):
                audit.main()
            inventory.assert_not_called()


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.before = {"torch": "2.10.0+rocm7.2", "torchvision": "0.25.0+rocm7.2",
                       "torchaudio": "2.10.0", "triton": "3.5.0", "apex": "1.0",
                       "pytorch-triton-rocm": "3.5.0", "pillow": "11.0.0"}
        self.overlay = {"pillow": "12.2.0", "fastapi": "0.141.1"}
        self.after = {**self.before, **self.overlay}

    def test_matching_overlay_and_protected_stack_pass(self):
        protected = audit.validate_inventory(self.before, self.after, self.overlay)
        self.assertIn("pytorch-triton-rocm", protected)
        self.assertNotIn("pillow", protected)

    def test_missing_or_changed_gpu_packages_fail(self):
        for name in audit.PROTECTED | {"pytorch-triton-rocm"}:
            for value in (None, "changed"):
                after = self.after.copy()
                if value is None:
                    del after[name]
                else:
                    after[name] = value
                with self.subTest(name=name, value=value), self.assertRaises(RuntimeError):
                    audit.validate_inventory(self.before, after, self.overlay)

    def test_missing_base_exclusion_is_not_silently_accepted(self):
        before = self.before.copy()
        del before["apex"]
        with self.assertRaisesRegex(RuntimeError, "missing"):
            audit.validate_inventory(before, self.after, self.overlay)

    def test_overlay_drift_cuda_and_protected_replacement_fail(self):
        for after, overlay in (({**self.after, "fastapi": "different"}, self.overlay),
                               ({**self.after, "nvidia-cublas": "1.0"}, self.overlay),
                               (self.after, {**self.overlay, "torch": self.after["torch"]})):
            with self.subTest(overlay=overlay), self.assertRaises(RuntimeError):
                audit.validate_inventory(self.before, after, overlay)


if __name__ == "__main__":
    unittest.main()
