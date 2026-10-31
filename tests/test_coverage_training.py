import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from emoji_studio.coverage_preflight import canonical, preflight, sha256
from emoji_studio.coverage_training import (
    argument_values,
    checked_indices,
    coverage_batch_sampler,
    load_recipe,
    options,
    patch_trainer,
    validate_runtime,
)


class CoverageTrainingTest(unittest.TestCase):
    def setUp(self):
        rows = [{"asset_id": f"asset-{i}", "concept": f"concept-{i}", "tone": "Default",
                 "family_id": f"family-{i}", "caption": f"caption-{i}",
                 "caption_status": "fixture", "included": True,
                 "split": "train" if i < 5 else "validation",
                 **{k: sha256(f"{k}-{i}".encode())
                    for k in ("sha256", "source_sha256", "pixel_sha256")}} for i in range(6)]
        self.raw = canonical({"rows": rows})
        self.recipe = {"manifest_sha256": sha256(self.raw), "seed": 29, "max_steps": 2,
                       "batch_size": 1, "gradient_accumulation": 4, "caption_status": "fixture",
                       "model_id": "test-model", "model_revision": "test-revision",
                       "output": "runs/coverage-fixture"}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.schedule = preflight(self.raw, **options(self.recipe))["schedule"]
        self.ids = [f"asset-{i}" for i in reversed(range(5))]
        self.captions = [f"caption-{i}" for i in reversed(range(5))]

    def indices(self, **changes):
        values = dict(ids=self.ids, captions=self.captions, trainer_captions=self.captions,
                      raw=self.raw, recipe=self.recipe, schedule=self.schedule)
        return checked_indices(**(values | changes))

    def test_reordered_loader_preserves_asset_sequence(self):
        self.assertEqual([self.ids[i] for i in self.indices()], self.schedule["draws"])
        self.assertEqual(len(set(self.indices()[:5])), 5)

    def test_loader_contamination_or_missing_ids_rejected(self):
        for ids in (self.ids[:-1], self.ids[:-1] + ["asset-5"], self.ids[:-1] + [self.ids[0]]):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                self.indices(ids=ids)

    def test_caption_content_and_order_rejected(self):
        for changed in (self.captions[:-1], list(reversed(self.captions)), ["wrong"] * 5):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                self.indices(captions=changed)
        with self.assertRaises(ValueError):
            self.indices(trainer_captions=list(reversed(self.captions)))
        with self.assertRaises(ValueError):
            self.indices(captions=["wrong"] * 5, trainer_captions=["wrong"] * 5)

    def test_schedule_budget_order_and_holdout_tampering_rejected(self):
        for change in ("asset-5", "asset-0"):
            schedule = copy.deepcopy(self.schedule)
            schedule["draws"] = [change] * 8
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.indices(schedule=schedule)
        with self.assertRaises(ValueError):
            self.indices(recipe=self.recipe | {"max_steps": 3})
        with self.assertRaises(ValueError):
            self.indices(raw=self.raw + b" ")

    def runtime(self):
        return SimpleNamespace(**argument_values(self.recipe), center_crop=True,
                               output_dir=str(Path(self.temp.name) / self.recipe["output"]),
                               cache_latents=True, skip_final_inference=True,
                               gradient_checkpointing=True, random_flip=False,
                               with_prior_preservation=False, offload=False,
                               push_to_hub=False, resume_from_checkpoint=None, do_fp8_training=False)

    def test_runtime_rejects_step_extension_resume_and_recipe_changes(self):
        validate_runtime(self.runtime(), self.recipe)
        for key, value in (("max_train_steps", 5000), ("resume_from_checkpoint", "latest"),
                           ("random_flip", True), ("train_batch_size", 2), ("seed", 30),
                           ("gradient_checkpointing", False), ("revision", "other")):
            args = self.runtime()
            setattr(args, key, value)
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_runtime(args, self.recipe)

    def test_existing_run_and_wrong_output_are_rejected(self):
        args = self.runtime()
        path = Path(args.output_dir)
        path.mkdir(parents=True)
        (path / "adapter.safetensors").write_bytes(b"preserve")
        with self.assertRaisesRegex(ValueError, "overwrite"):
            validate_runtime(args, self.recipe)
        self.assertEqual((path / "adapter.safetensors").read_bytes(), b"preserve")
        args.output_dir = str(Path(self.temp.name) / "pilot")
        with self.assertRaisesRegex(ValueError, "Output differs"):
            validate_runtime(args, self.recipe)

    def test_recipe_pin_rejects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "recipe.json"
            data = canonical(self.recipe)
            path.write_bytes(data)
            self.assertEqual(load_recipe(temp, sha256(data)), self.recipe)
            path.write_bytes(data + b" ")
            with self.assertRaises(ValueError):
                load_recipe(temp, sha256(data))

    def test_patch_refuses_unrecognized_trainer(self):
        with self.assertRaises(ValueError):
            patch_trainer("def main(args):\n    pass\n", "0" * 64)

    def test_world_size_rejected_before_loading_dataset(self):
        # No Torch dependency in the lightweight suite: the guard is before imports.
        with self.assertRaisesRegex(ValueError, "exactly one"):
            coverage_batch_sampler(None, "/missing", self.recipe, "/missing", 2)


if __name__ == "__main__":
    unittest.main()
