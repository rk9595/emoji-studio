"""Locked base/style interaction baseline; no provisioning and no training."""

import argparse
import hashlib
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.benchmark import validate_benchmark  # noqa: E402
from emoji_studio.common import digest, now, read_json, write_json  # noqa: E402


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_plan(root=ROOT):
    serving = read_json(root / "configs/serving.json")
    if serving.get("selected_step") != 25:
        raise ValueError("This baseline is locked to the selected step-25 adapter")
    benchmark = validate_benchmark(read_json(root / "benchmarks/high-five-v1.json"))
    adapter = root / serving["adapter_path"]
    if sha256(adapter) != serving["adapter_sha256"]:
        raise ValueError("Selected adapter checksum differs")
    jobs = []
    for variant in ("base", "style_step25"):
        for prompt in benchmark["prompts"]:
            for seed in (17, 29):
                jobs.append({
                    "id": f"{variant}-{prompt['id']}-{seed}",
                    "variant": variant,
                    "prompt_id": prompt["id"],
                    "category": prompt["category"],
                    "prompt": prompt["prompt"] + serving["style_suffix"],
                    "criteria": prompt["criteria"],
                    "seed": seed,
                })
    plan = {
        "schema_version": 1,
        "experiment": "high-five-base-style-v1",
        "benchmark_sha256": sha256(root / "benchmarks/high-five-v1.json"),
        "serving_sha256": sha256(root / "configs/serving.json"),
        "model_id": serving["model_id"],
        "model_revision": serving["model_revision"],
        "adapter_path": serving["adapter_path"],
        "adapter_sha256": serving["adapter_sha256"],
        "resolution": serving["resolution"],
        "steps": serving["steps"],
        "guidance_scale": serving["guidance_scale"],
        "jobs": jobs,
    }
    return {**plan, "plan_hash": digest(plan)}


def verify_plan(plan, root=ROOT):
    if plan != make_plan(root):
        raise ValueError("Plan differs from locked benchmark, settings, or adapter")


def completed(output, row, job):
    if not row or row.get("job") != job:
        return False
    path = output / "images" / f"{job['id']}.png"
    return path.is_file() and sha256(path) == row.get("image_sha256")


def evaluate(output, max_seconds):
    plan = read_json(output / "plan.json")
    verify_plan(plan)
    # Validate the complete plan before importing GPU dependencies or loading weights.
    import torch
    from diffusers import Flux2KleinPipeline

    if torch.cuda.device_count() != 1:
        raise ValueError("Exactly one visible CUDA GPU required")
    report_path = output / "report.json"
    report = {"plan_hash": plan["plan_hash"], "created_at": now(), "images": []}
    if report_path.exists():
        report = read_json(report_path)
        if report["plan_hash"] != plan["plan_hash"]:
            raise ValueError("Report belongs to another plan")
    report["status"] = "running"
    write_json(report_path, report)
    deadline = time.monotonic() + max_seconds

    def check_deadline(pipe, step, timestep, callback_kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Interaction evaluation deadline reached")
        return callback_kwargs

    try:
        pipe = Flux2KleinPipeline.from_pretrained(
            plan["model_id"], revision=plan["model_revision"],
            torch_dtype=torch.bfloat16, use_safetensors=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.set_progress_bar_config(disable=True)
        adapter_loaded = False
        (output / "images").mkdir(exist_ok=True)
        for job in plan["jobs"]:
            prior = next((r for r in report["images"] if r["job"]["id"] == job["id"]), None)
            if completed(output, prior, job):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("Interaction evaluation deadline reached")
            if job["variant"] == "style_step25" and not adapter_loaded:
                path = ROOT / plan["adapter_path"]
                pipe.load_lora_weights(path.parent, weight_name=path.name)
                adapter_loaded = True
            # All base jobs precede adapter jobs, including on resume.
            started = time.monotonic()
            with torch.no_grad():
                img = pipe(
                    prompt=job["prompt"], width=plan["resolution"], height=plan["resolution"],
                    num_inference_steps=plan["steps"], guidance_scale=plan["guidance_scale"],
                    generator=torch.Generator(device="cuda").manual_seed(job["seed"]),
                    callback_on_step_end=check_deadline,
                ).images[0]
            path = output / "images" / f"{job['id']}.png"
            temporary = path.with_suffix(".tmp")
            img.save(temporary, format="PNG")
            temporary.replace(path)
            record = {
                "job": job, "image": f"images/{path.name}", "image_sha256": sha256(path),
                "seconds": time.monotonic() - started,
            }
            report["images"] = [r for r in report["images"] if r["job"]["id"] != job["id"]]
            report["images"].append(record)
            write_json(report_path, report)
            print(f"Saved {len(report['images'])}/{len(plan['jobs'])}: {job['id']}", flush=True)
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["updated_at"] = now()
        write_json(report_path, report)


def verify_results(output):
    plan = read_json(output / "plan.json")
    verify_plan(plan)
    report = read_json(output / "report.json")
    rows = report["images"]
    if report["plan_hash"] != plan["plan_hash"] or report["status"] != "completed":
        raise ValueError("Incomplete or mismatched evaluation")
    if len(rows) != len(plan["jobs"]) or len({r["job"]["id"] for r in rows}) != len(rows):
        raise ValueError("Missing or repeated image records")
    indexed = {r["job"]["id"]: r for r in rows}
    if not all(completed(output, indexed.get(job["id"]), job) for job in plan["jobs"]):
        raise ValueError("Image missing, changed, or bound to a different job")
    return {"verified_images": len(rows), "plan_hash": plan["plan_hash"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run", "verify"])
    parser.add_argument("--output", type=Path, default=ROOT / "runs/high-five-baseline-v1")
    parser.add_argument("--max-seconds", type=int, default=1200)
    args = parser.parse_args()
    if args.command == "plan":
        path = args.output / "plan.json"
        if path.exists():
            verify_plan(read_json(path))
        else:
            write_json(path, make_plan())
        print(f"Locked 32 images: {path}")
    elif args.command == "verify":
        print(verify_results(args.output))
    else:
        if not 1 <= args.max_seconds <= 2400:
            parser.error("max-seconds must be between 1 and 2400")
        evaluate(args.output, args.max_seconds)


if __name__ == "__main__":
    main()
