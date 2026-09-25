"""Generate four provenance-tracked Qwen candidates; never admit them to training."""

import argparse
import hashlib
import re
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.common import digest, now, read_json, write_json  # noqa: E402

CONFIG = "configs/high-five-teacher-pilot.json"
OUTPUT = "runs/high-five-teacher-pilot-v1"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_plan(root=ROOT):
    config = read_json(root / CONFIG)
    if config["model_id"] != "Qwen/Qwen-Image-2512" or not re.fullmatch(
        r"[0-9a-f]{40}", config["model_revision"]
    ):
        raise ValueError("Teacher model must have a pinned revision")
    rows = config["candidates"]
    if len(rows) != 4 or len({r["id"] for r in rows}) != 4:
        raise ValueError("Pilot requires exactly four unique candidate IDs")
    benchmark = read_json(root / "benchmarks/high-five-v1.json")
    frozen = [" ".join(r["prompt"].lower().split()) for r in benchmark["prompts"]]
    jobs = []
    for row in rows:
        if not re.fullmatch(r"[a-z0-9-]+", row["id"]):
            raise ValueError("Unsafe candidate ID")
        if type(row["seed"]) is not int or not 0 <= row["seed"] < 2**32:
            raise ValueError("Invalid seed")
        prompt = row["description"] + " " + config["style"]
        if any(text in " ".join(prompt.lower().split()) for text in frozen):
            raise ValueError("Candidate prompt leaks frozen evaluation text")
        jobs.append({**row, "prompt": prompt})
    payload = {
        "schema_version": 1, "config": config, "jobs": jobs,
        "benchmark_sha256": sha256(root / "benchmarks/high-five-v1.json"),
        "sampler_sha256": sha256(root / "scripts/sample_interaction_teacher.py"),
        "lockfile_sha256": sha256(root / "uv.lock"),
    }
    return {**payload, "plan_hash": digest(payload)}


def completed(output, record, job):
    path = output / "images" / f"{job['id']}.png"
    return bool(record and record.get("job") == job and path.is_file()
                and sha256(path) == record.get("image_sha256"))


def validate_report(output, plan, require_complete=True):
    report = read_json(output / "report.json")
    if report.get("plan_hash") != plan["plan_hash"]:
        raise ValueError("Teacher report is bound to another plan")
    records = report["images"]
    indexed = {r["job"]["id"]: r for r in records}
    expected = {job["id"]: job for job in plan["jobs"]}
    if len(indexed) != len(records) or not indexed.keys() <= expected.keys():
        raise ValueError("Duplicate or unexpected teacher image")
    if any(not completed(output, record, expected[key]) for key, record in indexed.items()):
        raise ValueError("Teacher image or job checksum failed")
    for key in indexed:
        with Image.open(output / "images" / f"{key}.png") as image:
            image.load()
            if image.size != (plan["config"]["width"], plan["config"]["height"]):
                raise ValueError("Teacher image dimensions differ from the plan")
    if require_complete and (report.get("status") != "completed" or indexed.keys() != expected.keys()):
        raise ValueError("Teacher pilot is incomplete")
    return report


def sample(output, max_seconds):
    plan = read_json(output / "plan.json")
    if plan != make_plan():
        raise ValueError("Teacher plan differs from locked inputs")
    import torch
    from diffusers import QwenImagePipeline
    from huggingface_hub import hf_hub_download

    if torch.cuda.device_count() != 1:
        raise ValueError("Exactly one visible GPU is required")
    if torch.cuda.get_device_properties(0).total_memory < 45 * 1024**3:
        raise ValueError("Pilot requires a GPU with at least 45 GiB VRAM")
    config = plan["config"]
    report_path = output / "report.json"
    report = {"plan_hash": plan["plan_hash"], "created_at": now(), "images": []}
    if report_path.exists():
        report = validate_report(output, plan, require_complete=False)
    report["status"] = "running"
    write_json(report_path, report)
    deadline = time.monotonic() + max_seconds

    def check_deadline(pipe, step, timestep, kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Teacher pilot sampling deadline reached")
        return kwargs

    try:
        card = Path(hf_hub_download(config["model_id"], "README.md",
                                     revision=config["model_revision"]))
        if sha256(card) != config["model_card_sha256"]:
            raise ValueError("Teacher model card differs from reviewed provenance")
        pipe = QwenImagePipeline.from_pretrained(
            config["model_id"], revision=config["model_revision"],
            torch_dtype=torch.bfloat16, use_safetensors=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        (output / "images").mkdir(exist_ok=True)
        report["environment"] = {
            "torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
            "cpu_offload": True, "vae_tiling": True,
        }
        for job in plan["jobs"]:
            prior = next((r for r in report["images"] if r["job"]["id"] == job["id"]), None)
            if completed(output, prior, job):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("Teacher pilot deadline reached before next image")
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            with torch.no_grad():
                image = pipe(
                    prompt=job["prompt"], negative_prompt=config["negative_prompt"],
                    width=config["width"], height=config["height"],
                    num_inference_steps=config["steps"], true_cfg_scale=config["true_cfg_scale"],
                    generator=torch.Generator(device="cuda").manual_seed(job["seed"]),
                    callback_on_step_end=check_deadline,
                ).images[0]
            destination = output / "images" / f"{job['id']}.png"
            temporary = destination.with_suffix(".tmp")
            image.save(temporary, format="PNG")
            temporary.replace(destination)
            report["images"].append({
                "job": job, "image": f"images/{destination.name}",
                "image_sha256": sha256(destination), "generated_at": now(),
                "seconds": time.monotonic() - started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "curation_decision": "pending",
            })
            write_json(report_path, report)
            print(f"Saved candidate {len(report['images'])}/4: {job['id']}", flush=True)
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        # Avoid copying provider/download credentials from exception messages.
        report["error_type"] = type(error).__name__
        raise
    finally:
        report["updated_at"] = now()
        write_json(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run", "verify"])
    parser.add_argument("--output", type=Path, default=ROOT / OUTPUT)
    parser.add_argument("--max-seconds", type=int, default=2400)
    args = parser.parse_args()
    plan = make_plan()
    if args.command == "plan":
        path = args.output / "plan.json"
        if path.exists() and read_json(path) != plan:
            raise ValueError("Existing plan differs; use a new output directory")
        if not path.exists():
            write_json(path, plan)
        print(f"Four candidates locked: {plan['plan_hash']}")
    elif args.command == "verify":
        if read_json(args.output / "plan.json") != plan:
            raise ValueError("Plan differs from current locked inputs")
        report = validate_report(args.output, plan)
        print(f"Verified {len(report['images'])} candidates; none approved for training")
    else:
        if not 60 <= args.max_seconds <= 3000:
            parser.error("max-seconds must be between 60 and 3000")
        sample(args.output, args.max_seconds)


if __name__ == "__main__":
    main()
