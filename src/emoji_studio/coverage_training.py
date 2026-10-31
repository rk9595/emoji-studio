"""Prepare and enforce a coverage experiment without changing historical exports."""

import argparse
import ast
import json
import os
import tempfile
import warnings
from pathlib import Path

from .coverage_preflight import canonical, preflight, sha256, verify_schedule
from .training_data import verify_export


def options(recipe):
    return dict(expected_hash=recipe["manifest_sha256"], seed=recipe["seed"],
                draws=recipe["max_steps"] * recipe["batch_size"] * recipe["gradient_accumulation"],
                batch_size=recipe["batch_size"], accumulation=recipe["gradient_accumulation"],
                full_coverage=True, required_caption_status=recipe["caption_status"])


def checked_indices(ids, captions, trainer_captions, raw, recipe, schedule):
    verify_schedule(schedule, raw, **options(recipe))
    train = {r["asset_id"]: r for r in json.loads(raw)["rows"]
             if r["included"] and r["split"] == "train"}
    ids, captions, trainer_captions = list(ids), list(captions), list(trainer_captions)
    if len(ids) != len(set(ids)) or set(ids) != set(train):
        raise ValueError("Loader includes missing, duplicate or non-training images")
    if len(ids) != len(captions) or captions != trainer_captions:
        raise ValueError("Trainer image/caption ordering differs")
    if any(caption != train[asset]["caption"] for asset, caption in zip(ids, captions)):
        raise ValueError("Caption differs from frozen manifest")
    positions = {asset: i for i, asset in enumerate(ids)}
    return [positions[asset] for asset in schedule["draws"]]


def argument_values(recipe):
    return {
        "pretrained_model_name_or_path": recipe["model_id"], "revision": recipe["model_revision"],
        "image_column": "image", "caption_column": "text", "instance_prompt": "3D emoji illustration",
        "resolution": 512, "rank": 16, "learning_rate": 5e-5,
        "train_batch_size": recipe["batch_size"],
        "gradient_accumulation_steps": recipe["gradient_accumulation"],
        "max_train_steps": recipe["max_steps"], "checkpointing_steps": 125,
        "checkpoints_total_limit": 4, "mixed_precision": "bf16", "max_sequence_length": 512,
        "lr_scheduler": "constant", "lr_warmup_steps": 0, "seed": recipe["seed"],
        "dataloader_num_workers": 0, "optimizer": "AdamW", "report_to": "tensorboard",
        "caption_dropout": 0,
    }


def validate_runtime(args, recipe):
    output = Path(args.output_dir)
    if not output.as_posix().endswith("/" + recipe["output"]):
        raise ValueError("Output differs from the separate experiment directory")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("Refusing to overwrite an existing training run")
    for name, expected in argument_values(recipe).items():
        if getattr(args, name) != expected:
            raise ValueError(f"Frozen trainer argument differs: {name}")
    for name in ("center_crop", "cache_latents", "skip_final_inference", "gradient_checkpointing"):
        if not getattr(args, name):
            raise ValueError(f"Required training option disabled: {name}")
    for name in ("random_flip", "with_prior_preservation", "offload", "push_to_hub",
                 "resume_from_checkpoint", "do_fp8_training"):
        if getattr(args, name):
            raise ValueError(f"Unsupported training option enabled: {name}")


def load_recipe(bundle, expected_hash):
    raw = (Path(bundle) / "recipe.json").read_bytes()
    if sha256(raw) != expected_hash:
        raise ValueError("Frozen recipe changed")
    return json.loads(raw)


def coverage_batch_sampler(dataset, dataset_path, recipe, schedule_path, world_size):
    if world_size != 1:
        raise ValueError("This schedule is for exactly one training process")
    from datasets import load_dataset
    from torch.utils.data import BatchSampler
    train_dir = Path(dataset_path)
    raw = (train_dir.parent / "manifest.json").read_bytes()
    schedule = json.loads(Path(schedule_path).read_bytes())
    verify_schedule(schedule, raw, **options(recipe))
    manifest = verify_export(train_dir.parent)
    if train_dir.name != "train" or dataset.num_instance_images != manifest["counts"]["train"]:
        raise ValueError("Unexpected training pool or repeated dataset")
    if list(dataset.buckets) != [(512, 512)]:
        raise ValueError("Expected one 512px square bucket")
    loaded = load_dataset(str(train_dir))["train"]
    indices = checked_indices(loaded["asset_id"], loaded["text"],
                              dataset.custom_instance_prompts, raw, recipe, schedule)
    return BatchSampler(indices, batch_size=recipe["batch_size"], drop_last=False)


def patch_trainer(source, recipe_hash):
    replacements = {
        "def main(args):":
        "def main(args):\n"
        "    from emoji_studio.coverage_training import load_recipe, validate_runtime\n"
        f"    coverage_recipe = load_recipe(Path(__file__).parent, {recipe_hash!r})\n"
        "    validate_runtime(args, coverage_recipe)",
        "batch_sampler = BucketBatchSampler(train_dataset, batch_size=args.train_batch_size, "
        "drop_last=True, seed=args.seed)":
        "from emoji_studio.coverage_training import coverage_batch_sampler\n"
        "    batch_sampler = coverage_batch_sampler(train_dataset, args.dataset_name, "
        "coverage_recipe, Path(__file__).with_name('schedule.json'), accelerator.num_processes)",
    }
    for cache, value in (("instance_latents_cache", "instance_latents"),
                         ("class_latents_cache", "class_latents"),
                         ("prompt_embeds_cache", "prompt_embeds"), ("text_ids_cache", "text_ids")):
        anchor = f"{cache}[idx] = {value}[i : i + 1]"
        replacements[anchor] = anchor + '.detach().to("cpu", copy=True)'
    for value, cache in (("prompt_embeds", "prompt_embeds_cache"),
                         ("text_ids", "text_ids_cache"), ("model_input", "instance_latents_cache")):
        anchor = f"{value} = torch.cat([{cache}[idx] for idx in sample_indices], dim=0)"
        replacements[anchor] = anchor + ".to(accelerator.device)"
    for old, new in replacements.items():
        if source.count(old) != 1:
            raise ValueError("Pinned upstream patch anchor differs")
        source = source.replace(old, new)
    ast.parse(source)
    return source


def prepare(root, recipe_path, output):
    root, output = Path(root).resolve(), Path(output).resolve()
    recipe_raw = Path(recipe_path).read_bytes()
    recipe = json.loads(recipe_raw)
    dataset = root / recipe["dataset"]
    raw = (dataset / "manifest.json").read_bytes()
    proposal = preflight(raw, **options(recipe))
    if proposal["status"] != "prototype_passed":
        raise ValueError(f"Coverage preflight blocked: {proposal['blockers']}")
    manifest = verify_export(dataset)
    # The bitmap hashes and manifest row hashes must refer to the same files.
    for row in manifest["rows"]:
        if manifest["files"].get(row["path"]) != row["sha256"]:
            raise ValueError("Manifest row/file hashes differ")
    benchmark_raw = (root / recipe["evaluation"]["benchmark"]).read_bytes()
    if sha256(benchmark_raw) != recipe["evaluation"]["sha256"]:
        raise ValueError("Evaluation benchmark changed")
    for prompt in json.loads(benchmark_raw)["prompts"]:
        matches = [r for r in manifest["rows"] if r["included"] and r["concept"] == prompt["concept"]]
        category = prompt["category"]
        if category.startswith("heldout_") and (not matches or any(r["split"] != "validation" for r in matches)
                                               or prompt["tone"] not in {r["tone"] for r in matches}):
            raise ValueError("Held-out evaluation label differs from split")
        if category == "novel_composition_challenge" and matches:
            raise ValueError("Novel challenge is present in training data")
        if category == "trained_geometry_control" and (not matches or any(r["split"] != "train" for r in matches)):
            raise ValueError("Trained geometry control differs from split")
    source_dir = root / "artifacts/trainers" / recipe["trainer_revision"]
    source = (source_dir / "train_dreambooth_lora_flux2_klein.py").read_bytes()
    if sha256(source) != recipe["trainer_sha256"]:
        raise ValueError("Upstream trainer checksum differs")
    patched = patch_trainer(source.decode(), sha256(recipe_raw))
    values = {**argument_values(recipe), "dataset_name": str(dataset / "train"),
              "output_dir": str(root / recipe["output"])}
    argv = [item for name, value in values.items() for item in ("--" + name, str(value))]
    argv += ["--center_crop", "--cache_latents", "--skip_final_inference", "--gradient_checkpointing"]
    parse = next(n for n in ast.parse(patched).body if isinstance(n, ast.FunctionDef) and n.name == "parse_args")
    namespace = {"argparse": argparse, "os": os, "warnings": warnings}
    exec(compile(ast.Module(body=[parse], type_ignores=[]), "pinned-parser", "exec"), namespace)
    validate_runtime(namespace["parse_args"](argv), recipe)
    files = {"recipe.json": recipe_raw, "schedule.json": canonical(proposal["schedule"]),
             "train_coverage.py": patched.encode(), "LICENSE": (source_dir / "LICENSE").read_bytes()}
    report = {
        "status": "prepared_offline", "training_started": False, "gpu_allocated": False,
        "manifest_sha256": sha256(raw), "recipe_sha256": sha256(recipe_raw),
        "files_verified": len(manifest["files"]), "validation_images": manifest["counts"]["validation"],
        "draws": proposal["draw_budget"], "unique_images": proposal["coverage"]["unique_assets"],
        "maximum_repeats": proposal["coverage"]["maximum_repeats"], "omitted_images": len(proposal["coverage"]["omitted_assets"]),
        "caption_status_counts": proposal["caption_status_counts"],
        "bundle_sha256": {name: sha256(data) for name, data in files.items()},
        "runtime_helper_sha256": sha256(Path(__file__).read_bytes()),
        "argv": argv, "upstream_parser_passed": True,
        "limitations": ["GPU forward/backward untested on AMD", "Captions remain provisional",
                        "Development evaluation, not a sealed test", "Requires a new bounded cloud lifecycle"],
    }
    if output.exists():
        if {p.name: p.read_bytes() for p in output.iterdir()} != files:
            raise ValueError("Existing bundle differs; choose a new version")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=output.parent, prefix=".coverage-") as temp:
            stage = Path(temp) / "bundle"
            stage.mkdir()
            for name, data in files.items():
                (stage / name).write_bytes(data)
            stage.rename(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--recipe", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = prepare(args.root, args.recipe, args.output)
    args.report.write_bytes(canonical(report))
    print(json.dumps({k: report[k] for k in ("status", "files_verified", "draws", "unique_images", "omitted_images")}))


if __name__ == "__main__":
    main()
