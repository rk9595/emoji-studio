"""Render a resumable, matched four-checkpoint evaluation on one CUDA GPU."""

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.benchmark import validate_benchmark  # noqa: E402
from emoji_studio.common import digest, now, read_json, write_json  # noqa: E402

CONFIG = ROOT / "configs/checkpoint-selection.json"
OUTPUT = ROOT / "runs/checkpoint-selection"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_plan(root=ROOT):
    config = read_json(root / "configs/checkpoint-selection.json")
    benchmark_path = root / config["benchmark"]
    benchmark = validate_benchmark(read_json(benchmark_path))
    if len(benchmark["prompts"]) != config["expected_prompts"]:
        raise ValueError("Checkpoint benchmark prompt count differs from locked configuration")
    if len(config["seeds"]) != len(set(config["seeds"])) or not config["seeds"]:
        raise ValueError("Checkpoint evaluation seeds must be non-empty and unique")
    curation = read_json(root / "data/curation.json")
    trained_concepts = {
        row["concept"].casefold() for row in curation["rows"] if row.get("decision") == "keep"
    }
    selection_concepts = [row.get("concept", "").casefold() for row in benchmark["prompts"]]
    if any(not concept for concept in selection_concepts):
        raise ValueError("Every checkpoint-selection prompt needs an explicit concept")
    overlap = trained_concepts.intersection(selection_concepts)
    if overlap:
        raise ValueError(f"Checkpoint selection leaks trained concepts: {sorted(overlap)}")
    if [row["step"] for row in config["checkpoints"]] != [25, 50, 75, 100]:
        raise ValueError("Checkpoint steps must be exactly 25, 50, 75, and 100")
    for checkpoint in config["checkpoints"]:
        path = root / checkpoint["path"]
        if not path.is_file() or sha256(path) != checkpoint["sha256"]:
            raise ValueError(f"Checkpoint {checkpoint['step']} is missing or differs from its lock")
    jobs = []
    for prompt in benchmark["prompts"]:
        for seed in config["seeds"]:
            pair = {
                "prompt_id": prompt["id"],
                "category": prompt["category"],
                "prompt": prompt["prompt"],
                "criteria": prompt["criteria"],
                "seed": seed,
            }
            pair["pair_id"] = digest(pair)[:20]
            jobs.append(pair)
    expected = len(jobs) * len(config["checkpoints"])
    if expected != config["expected_images"]:
        raise ValueError("Expected checkpoint image count differs from the locked configuration")
    return config, benchmark_path, jobs


def completed(output, record, expected):
    if not record or any(record.get(key) != value for key, value in expected.items()):
        return False
    path = output / record.get("image", "")
    return path.is_file() and sha256(path) == record.get("image_sha256")


def evaluate(output=OUTPUT, max_seconds=2400):
    import torch
    from diffusers import Flux2KleinPipeline

    config, benchmark_path, pairs = evaluation_plan(ROOT)
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "report.json"
    locked = {
        "benchmark_sha256": sha256(benchmark_path),
        "config_sha256": sha256(CONFIG),
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "settings": {
            key: config[key] for key in ["seeds", "steps", "guidance_scale", "resolution"]
        },
        "checkpoints": config["checkpoints"],
    }
    report = {
        "status": "running",
        "created_at": now(),
        **locked,
        "images": [],
    }
    if report_path.exists():
        prior = read_json(report_path)
        if any(prior.get(key) != value for key, value in locked.items()):
            raise ValueError("Existing checkpoint evaluation belongs to different locked inputs")
        report["created_at"] = prior.get("created_at", report["created_at"])
        report["images"] = prior.get("images", [])
    write_json(report_path, report)

    started = time.monotonic()
    deadline = started + max_seconds

    def check_deadline(pipe, step, timestep, callback_kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Checkpoint evaluation deadline reached during sampling")
        return callback_kwargs

    try:
        pipeline = Flux2KleinPipeline.from_pretrained(
            config["model_id"],
            revision=config["model_revision"],
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
        )
        pipeline.enable_model_cpu_offload()
        pipeline.set_progress_bar_config(disable=True)
        adapter_names = []
        for checkpoint in config["checkpoints"]:
            adapter_name = f"checkpoint_{checkpoint['step']}"
            path = ROOT / checkpoint["path"]
            pipeline.load_lora_weights(
                path.parent, weight_name=path.name, adapter_name=adapter_name
            )
            adapter_names.append(adapter_name)
        for checkpoint, adapter_name in zip(config["checkpoints"], adapter_names, strict=True):
            pipeline.set_adapters(adapter_name)
            image_dir = output / f"step-{checkpoint['step']}"
            image_dir.mkdir(parents=True, exist_ok=True)
            for pair in pairs:
                expected = {
                    "pair_id": pair["pair_id"],
                    "prompt_id": pair["prompt_id"],
                    "seed": pair["seed"],
                    "checkpoint_step": checkpoint["step"],
                    "prompt": pair["prompt"],
                    "adapter_sha256": checkpoint["sha256"],
                }
                prior = next(
                    (
                        row
                        for row in report["images"]
                        if row.get("pair_id") == pair["pair_id"]
                        and row.get("checkpoint_step") == checkpoint["step"]
                    ),
                    None,
                )
                if completed(output, prior, expected):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("Checkpoint evaluation deadline reached before next image")
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                image_started = time.monotonic()
                # PEFT toggles adapter parameters between checkpoints. no_grad prevents
                # autograd without creating inference-only tensors that cannot be reactivated.
                with torch.no_grad():
                    image = pipeline(
                        prompt=pair["prompt"],
                        width=config["resolution"],
                        height=config["resolution"],
                        num_inference_steps=config["steps"],
                        guidance_scale=config["guidance_scale"],
                        generator=torch.Generator(device="cuda").manual_seed(pair["seed"]),
                        callback_on_step_end=check_deadline,
                    ).images[0]
                torch.cuda.synchronize()
                relative = Path(f"step-{checkpoint['step']}") / (
                    f"{pair['prompt_id']}-seed-{pair['seed']}.png"
                )
                destination = output / relative
                temporary = destination.with_suffix(".tmp")
                image.save(temporary, format="PNG")
                temporary.replace(destination)
                record = {
                    **expected,
                    "category": pair["category"],
                    "criteria": pair["criteria"],
                    "image": relative.as_posix(),
                    "image_sha256": sha256(destination),
                    "generation_seconds": round(time.monotonic() - image_started, 4),
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                    "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                }
                report["images"] = [
                    row
                    for row in report["images"]
                    if not (
                        row.get("pair_id") == pair["pair_id"]
                        and row.get("checkpoint_step") == checkpoint["step"]
                    )
                ]
                report["images"].append(record)
                write_json(report_path, report)
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished_at"] = now()
        report["wall_seconds"] = round(time.monotonic() - started, 4)
        write_json(report_path, report)

    if len(report["images"]) != config["expected_images"]:
        raise ValueError("Checkpoint evaluation did not produce every locked image")
    counts = {
        str(step): sum(row["checkpoint_step"] == step for row in report["images"])
        for step in [25, 50, 75, 100]
    }
    if len(set(counts.values())) != 1:
        raise ValueError("Checkpoint evaluation is unbalanced")
    report["status"] = "completed"
    report["counts"] = counts
    report["finished_at"] = now()
    report["wall_seconds"] = round(time.monotonic() - started, 4)
    report.pop("error", None)
    write_json(report_path, report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-seconds", type=int, required=True)
    args = parser.parse_args()
    if not 900 <= args.max_seconds <= 3600:
        parser.error("--max-seconds must be between 900 and 3600")
    evaluate(args.output.resolve(), args.max_seconds)
