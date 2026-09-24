"""Fetch and check the pinned trainer without importing models or starting training."""

import argparse
import ast
import hashlib
import json
import os
import warnings
from pathlib import Path
from urllib.request import urlopen

from datasets import load_dataset

from emoji_studio.common import digest, now, read_json, write_json
from emoji_studio.training_data import verify_export


def fetch_verified(url, target, checksum=None):
    content = target.read_bytes() if target.exists() else urlopen(url, timeout=60).read()
    actual = hashlib.sha256(content).hexdigest()
    if checksum is not None and actual != checksum:
        raise ValueError(f"Upstream checksum mismatch: {target.name}")
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--dataset", type=Path, default=Path("data/training/pilot-v1"))
    args = parser.parse_args()
    root = args.root.resolve()
    dataset_path = (root / args.dataset).resolve()
    config = read_json(root / "configs/lora-pilot.json")
    manifest = verify_export(dataset_path)
    if manifest["config_hash"] != digest(config):
        raise ValueError("Export belongs to a different pilot configuration")
    if manifest["curation_hash"] != digest(read_json(root / "data/curation.json")):
        raise ValueError("Export belongs to stale curation")
    revision = config["trainer_revision"]
    base_url = f"https://raw.githubusercontent.com/{config['trainer_repository']}/{revision}"
    artifact = root / "artifacts/trainers" / revision
    trainer = artifact / Path(config["trainer_script"]).name
    trainer_hash = fetch_verified(
        f"{base_url}/{config['trainer_script']}", trainer, config["trainer_sha256"]
    )
    license_hash = fetch_verified(f"{base_url}/LICENSE", artifact / "LICENSE")

    # Match the official trainer's load_dataset call, pointing ONLY at train/.
    dataset = load_dataset(
        str(dataset_path / "train"), None, cache_dir=str(root / "artifacts/dataset-cache")
    )
    if set(dataset) != {"train"}:
        raise ValueError("Unexpected splits exposed to trainer")
    expected = [row for row in manifest["rows"] if row["split"] == "train"]
    loaded = dataset["train"]
    if len(loaded) != len(expected):
        raise ValueError("Training loader count differs from manifest")
    expected_captions = sorted(row["caption"] for row in expected)
    if sorted(loaded["text"]) != expected_captions:
        raise ValueError("Per-image captions were lost")
    # Verify image-caption associations, not just equal sets of images and captions.
    expected_pixels = {}
    from PIL import Image

    for row in expected:
        with Image.open(dataset_path / row["path"]) as image:
            expected_pixels[row["caption"]] = hashlib.sha256(image.tobytes()).hexdigest()
    for row in loaded:
        image = row["image"]
        if image.mode != "RGB" or image.size != (config["resolution"],) * 2:
            raise ValueError("Training loader changed image dimensions or mode")
        if hashlib.sha256(image.tobytes()).hexdigest() != expected_pixels[row["text"]]:
            raise ValueError("Image-caption association differs from manifest")

    training_args = [
        "--pretrained_model_name_or_path",
        config["model_id"],
        "--revision",
        config["model_revision"],
        "--dataset_name",
        str(dataset_path / "train"),
        "--image_column",
        "image",
        "--caption_column",
        "text",
        "--instance_prompt",
        "3D emoji illustration",
        "--output_dir",
        str(root / "runs/lora-pilot-smoke"),
        "--resolution",
        str(config["resolution"]),
        "--rank",
        str(config["proposed_rank"]),
        "--learning_rate",
        str(config["proposed_learning_rate"]),
        "--train_batch_size",
        str(config["proposed_batch_size"]),
        "--gradient_accumulation_steps",
        str(config["proposed_gradient_accumulation"]),
        "--max_train_steps",
        "2",
        "--checkpointing_steps",
        "1",
        "--checkpoints_total_limit",
        "2",
        "--mixed_precision",
        config["mixed_precision"],
        "--lr_scheduler",
        "constant",
        "--lr_warmup_steps",
        "0",
        "--seed",
        "0",
        "--dataloader_num_workers",
        "0",
        "--optimizer",
        "AdamW",
        "--report_to",
        "tensorboard",
        "--center_crop",
        "--cache_latents",
        "--offload",
    ]
    if config["gradient_checkpointing"]:
        training_args.append("--gradient_checkpointing")
    # Exercise the hash-verified upstream parser only. Full imports require a GPU stack.
    tree = ast.parse(trainer.read_text())
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "parse_args"
    )
    namespace = {"argparse": argparse, "os": os, "warnings": warnings}
    exec(compile(ast.Module(body=[function], type_ignores=[]), str(trainer), "exec"), namespace)
    parsed = namespace["parse_args"](training_args)
    if config["train_text_encoder"] or parsed.push_to_hub or parsed.random_flip:
        raise ValueError("Unexpected training behavior enabled")
    freezes = {
        node.func.value.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "requires_grad_"
        and isinstance(node.func.value, ast.Name)
        and len(node.args) == 1
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value is False
    }
    if not {"text_encoder", "transformer", "vae"}.issubset(freezes):
        raise ValueError("Expected frozen base components missing from pinned trainer")
    report = {
        "checked_at": now(),
        "training_authorized": False,
        "training_started": False,
        "export_hash": manifest["export_hash"],
        "trainer_sha256": trainer_hash,
        "trainer_license_sha256": license_hash,
        "dependency_lock_sha256": hashlib.sha256((root / "uv.lock").read_bytes()).hexdigest(),
        "checks": {
            "imagefolder_loaded": True,
            "training_images": len(loaded),
            "validation_images_excluded": manifest["counts"].get("validation", 0),
            "caption_image_pairs_verified": True,
            "upstream_parser_passed": True,
            "full_trainer_import_tested": False,
            "gpu_forward_backward_tested": False,
            "adapter_save_reload_tested": False,
        },
        "proposed_smoke_steps": 2,
        "proposed_pilot_step_ceiling": config["proposed_max_steps"],
        "draft_argv_not_executed": ["python", str(trainer), *training_args],
        "note": "Local paths must be regenerated on the GPU host. No model weights loaded. Separate training budget, wall-clock watchdog, GPU import/step/save/reload checks required before a pilot.",
    }
    write_json(root / "reports/trainer-preparation.json", report)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
