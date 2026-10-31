"""CPU integration: ImageFolder -> patched trainer sampler -> Accelerate loader."""

import ast
import json
from collections import Counter
from pathlib import Path
from types import SimpleNamespace

import accelerate
import datasets
import torch
from accelerate import Accelerator
from datasets import load_dataset
from PIL import Image
from torch.utils.data import DataLoader

from emoji_studio.coverage_preflight import canonical, sha256
from emoji_studio.coverage_training import coverage_batch_sampler

ROOT = Path(__file__).resolve().parents[1]


def main():
    bundle = ROOT / "artifacts/trainers/coverage-v1"
    recipe = json.loads((bundle / "recipe.json").read_bytes())
    train_dir = ROOT / recipe["dataset"] / "train"
    manifest = json.loads((train_dir.parent / "manifest.json").read_bytes())
    rows = {r["asset_id"]: r for r in manifest["rows"]}
    loaded = load_dataset(str(train_dir))["train"]
    # Verify the ImageFolder decoder associates the actual pixels with each ID.
    for record in loaded:
        with Image.open(train_dir.parent / rows[record["asset_id"]]["path"]) as original:
            if (record["image"].size != (512, 512) or record["image"].mode != "RGB"
                    or record["image"].tobytes() != original.tobytes()):
                raise ValueError("Decoded image/ID association differs")
    dataset = SimpleNamespace(num_instance_images=len(loaded), buckets=[(512, 512)],
                              custom_instance_prompts=list(loaded["text"]))
    sampler = coverage_batch_sampler(dataset, str(train_dir), recipe,
                                     bundle / "schedule.json", world_size=1)
    accelerator = Accelerator(cpu=True, gradient_accumulation_steps=recipe["gradient_accumulation"])
    loader = accelerator.prepare(DataLoader(list(range(len(loaded))), batch_sampler=sampler))
    ids = list(loaded["asset_id"])
    actual, optimizer_boundaries = [], 0
    for batch in loader:
        with accelerator.accumulate():
            actual.extend(ids[int(index)] for index in batch)
            optimizer_boundaries += int(accelerator.sync_gradients)
    schedule = json.loads((bundle / "schedule.json").read_bytes())
    if actual != schedule["draws"] or optimizer_boundaries != recipe["max_steps"]:
        raise ValueError("Accelerate changed the sequence or optimizer-step boundaries")
    # Exercise the four cache assignments in the patched trainer, not reimplementations.
    source = (bundle / "train_coverage.py").read_text()
    tested = set()
    names = {"instance_latents_cache", "class_latents_cache", "prompt_embeds_cache", "text_ids_cache"}
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or not isinstance(node.targets[0], ast.Subscript):
            continue
        target = node.targets[0]
        if not isinstance(target.value, ast.Name) or target.value.id not in names:
            continue
        name = target.value.id
        values = torch.ones((1, 2, 3), requires_grad=True)
        ns = {"idx": 0, "i": 0, name: [None], **{k: values for k in
              ("instance_latents", "class_latents", "prompt_embeds", "text_ids")}}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "patched-cache", "exec"), ns)
        cached = ns[name][0]
        if (cached.requires_grad or cached.device.type != "cpu" or cached.data_ptr() == values.data_ptr()
                or not torch.equal(cached, values)):
            raise ValueError("Cache assignment did not preserve detached CPU copy")
        tested.add(name)
    if tested != names:
        raise ValueError("Not all cache assignments exercised")
    counts = Counter(actual)
    report = {"status": "passed", "device": "cpu", "model_weights_loaded": False,
              "torch": torch.__version__, "datasets": datasets.__version__,
              "accelerate": accelerate.__version__, "image_caption_pixel_associations": len(loaded),
              "draws": len(actual), "unique_images": len(counts),
              "optimizer_boundaries": optimizer_boundaries,
              "step_500_unique_images": len(set(actual[:2000])),
              "minimum_repeats": min(counts.values()), "maximum_repeats": max(counts.values()),
              "sequence_matches": True, "cpu_cache_assignments": sorted(tested),
              "trainer_sha256": sha256(source.encode()),
              "helper_sha256": sha256((ROOT / "src/emoji_studio/coverage_training.py").read_bytes()),
              "recipe_sha256": sha256((bundle / "recipe.json").read_bytes()),
              "schedule_sha256": sha256((bundle / "schedule.json").read_bytes()),
              "gpu_forward_backward_tested": False}
    (ROOT / "reports/coverage-training-cpu-check.json").write_bytes(canonical(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
