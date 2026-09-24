"""Render a fixed, matched base-versus-LoRA development evaluation on CUDA."""

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

CONFIG = ROOT / "configs/lora-quality-pilot.json"
OUTPUT = ROOT / "runs/lora-quality-pilot"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def evaluation_jobs(root=ROOT):
    config = read_json(root / "configs/lora-quality-pilot.json")
    settings = config["evaluation"]
    benchmark_path = root / settings["benchmark"]
    benchmark = validate_benchmark(read_json(benchmark_path))
    seeds = settings["seeds"]
    if not seeds or len(seeds) != len(set(seeds)):
        raise ValueError("Evaluation seeds must be a non-empty unique list")
    jobs = []
    for row in benchmark["prompts"]:
        for seed in seeds:
            job = {
                "prompt_id": row["id"],
                "category": row["category"],
                "prompt": row["prompt"],
                "criteria": row["criteria"],
                "seed": seed,
            }
            job["pair_id"] = digest(job)[:20]
            jobs.append(job)
    if len(jobs) != settings["expected_pairs"]:
        raise ValueError("Evaluation pair count differs from the locked configuration")
    return config, benchmark_path, jobs


def completed_record(output, record, expected):
    if not record or any(record.get(key) != value for key, value in expected.items()):
        return False
    image_path = output / record.get("image", "")
    return image_path.is_file() and sha256(image_path) == record.get("image_sha256")


def evaluate(output, max_seconds):
    import torch
    from diffusers import Flux2KleinPipeline

    config, benchmark_path, pairs = evaluation_jobs(ROOT)
    adapter = output / "pytorch_lora_weights.safetensors"
    if not adapter.is_file():
        raise ValueError("Final adapter is missing")
    adapter_hash = sha256(adapter)
    settings = config["evaluation"]
    report_path = output / "evaluation/report.json"
    report = {
        "status": "running",
        "created_at": now(),
        "benchmark": str(benchmark_path.relative_to(ROOT)),
        "benchmark_sha256": sha256(benchmark_path),
        "adapter_sha256": adapter_hash,
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "settings": {
            "seeds": settings["seeds"],
            "steps": settings["steps"],
            "guidance_scale": settings["guidance_scale"],
            "resolution": settings["resolution"],
            "expected_pairs": settings["expected_pairs"],
        },
        "images": [],
    }
    if report_path.exists():
        prior = read_json(report_path)
        locked = ["benchmark_sha256", "adapter_sha256", "model_id", "model_revision", "settings"]
        if any(prior.get(key) != report[key] for key in locked):
            raise ValueError("Existing evaluation belongs to different locked inputs")
        report["created_at"] = prior.get("created_at", report["created_at"])
        report["images"] = prior.get("images", [])
    output.joinpath("evaluation/base").mkdir(parents=True, exist_ok=True)
    output.joinpath("evaluation/adapted").mkdir(parents=True, exist_ok=True)
    write_json(report_path, report)

    started = time.monotonic()
    deadline = started + max_seconds
    pipeline = Flux2KleinPipeline.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
        torch_dtype=torch.bfloat16,
        use_safetensors=True,
    )
    pipeline.enable_model_cpu_offload()
    pipeline.set_progress_bar_config(disable=True)

    def check_deadline(pipe, step, timestep, callback_kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Evaluation deadline reached during sampling")
        return callback_kwargs

    try:
        for condition in ["base", "adapted"]:
            if condition == "adapted":
                pipeline.load_lora_weights(output, weight_name="pytorch_lora_weights.safetensors")
            for pair in pairs:
                expected = {
                    "pair_id": pair["pair_id"],
                    "prompt_id": pair["prompt_id"],
                    "seed": pair["seed"],
                    "condition": condition,
                    "prompt": pair["prompt"],
                }
                prior = next(
                    (
                        row
                        for row in report["images"]
                        if row.get("pair_id") == pair["pair_id"]
                        and row.get("condition") == condition
                    ),
                    None,
                )
                if completed_record(output, prior, expected):
                    continue
                if time.monotonic() >= deadline:
                    raise TimeoutError("Evaluation deadline reached before the next image")
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                image_started = time.monotonic()
                with torch.inference_mode():
                    image = pipeline(
                        prompt=pair["prompt"],
                        width=settings["resolution"],
                        height=settings["resolution"],
                        num_inference_steps=settings["steps"],
                        guidance_scale=settings["guidance_scale"],
                        generator=torch.Generator(device="cuda").manual_seed(pair["seed"]),
                        callback_on_step_end=check_deadline,
                    ).images[0]
                torch.cuda.synchronize()
                relative = (
                    Path("evaluation")
                    / condition
                    / (f"{pair['prompt_id']}-seed-{pair['seed']}.png")
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
                        row.get("pair_id") == pair["pair_id"] and row.get("condition") == condition
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

    expected_images = settings["expected_pairs"] * 2
    if len(report["images"]) != expected_images:
        raise ValueError("Evaluation did not produce every matched image")
    counts = {
        condition: sum(row["condition"] == condition for row in report["images"])
        for condition in ["base", "adapted"]
    }
    if set(counts.values()) != {settings["expected_pairs"]}:
        raise ValueError("Evaluation conditions are unbalanced")
    report["status"] = "completed"
    report["counts"] = counts
    report["finished_at"] = now()
    report["wall_seconds"] = round(time.monotonic() - started, 4)
    write_json(report_path, report)
    print(json.dumps(report, indent=2), flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--max-seconds", type=int, required=True)
    args = parser.parse_args()
    if not 300 <= args.max_seconds <= 3600:
        parser.error("max-seconds must be between 300 and 3600")
    evaluate(args.output.resolve(), args.max_seconds)
