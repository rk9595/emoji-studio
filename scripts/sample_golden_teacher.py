"""Generate eight golden candidates without changing the historical four-image sampler."""

import argparse
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from sample_interaction_teacher import completed, sha256, validate_report  # noqa: E402

from emoji_studio.common import digest, now, read_json, write_json  # noqa: E402

CONFIG = "configs/high-five-golden-audition.json"
OUTPUT = "runs/high-five-golden-audition-v1"


def make_plan(root=ROOT):
    config = read_json(root / CONFIG)
    if (config["model_id"] != "Qwen/Qwen-Image-2512"
            or config["model_revision"] != "25468b98e3276ca6700de15c6628e51b7de54a26"):
        raise ValueError("Golden audition requires the reviewed pinned teacher")
    reference = config["reference"]
    if (reference["use"] != "visual_review_only_not_model_input"
            or reference["image_sha256"] !=
            "c51db19bc58a3a77f77cb8b699b5fc4bb4f9705a8f410aa394ec60a7d30aae4f"
            or reference["human_gesture_approved"] is not True
            or reference["human_style_approved"] is not True):
        raise ValueError("Reference must retain the exact human-approved gesture/style binding")
    frozen = [" ".join(r["prompt"].lower().split())
              for r in read_json(root / "benchmarks/high-five-v1.json")["prompts"]]
    compositions = config["compositions"]
    if len(compositions) != 4 or len({r["pose_group"] for r in compositions}) != 4:
        raise ValueError("Exactly four intended pose groups required")
    jobs = []
    for row in compositions:
        if not re.fullmatch(r"[a-z0-9-]+", row["id"]) or len(row["seeds"]) != 2:
            raise ValueError("Each safe composition ID requires two seeds")
        prompt = row["description"] + " " + config["style"]
        if any(text in " ".join(prompt.lower().split()) for text in frozen):
            raise ValueError("Golden prompt leaks frozen evaluation text")
        for seed in row["seeds"]:
            if type(seed) is not int or not 0 <= seed < 2**32:
                raise ValueError("Invalid seed")
            jobs.append({"id": f"{row['id']}-{seed}", "seed": seed,
                         "pose_group": row["pose_group"], "tone_pair": ["yellow", "yellow"],
                         "description": row["description"], "prompt": prompt})
    if len({r["id"] for r in jobs}) != 8 or len({r["seed"] for r in jobs}) != 8:
        raise ValueError("Eight unique jobs and seeds required")
    payload = {
        "schema_version": 1, "config": config, "jobs": jobs,
        "benchmark_sha256": sha256(root / "benchmarks/high-five-v1.json"),
        "sampler_sha256": sha256(root / "scripts/sample_golden_teacher.py"),
        "validation_helper_sha256": sha256(root / "scripts/sample_interaction_teacher.py"),
        "lockfile_sha256": sha256(root / "uv.lock"),
    }
    return {**payload, "plan_hash": digest(payload)}


def sample(output, max_seconds):
    plan = read_json(output / "plan.json")
    if plan != make_plan():
        raise ValueError("Golden plan differs from locked inputs")
    import torch
    from diffusers import QwenImagePipeline
    from huggingface_hub import hf_hub_download

    if torch.cuda.device_count() != 1:
        raise ValueError("Exactly one visible GPU is required")
    if torch.cuda.get_device_properties(0).total_memory < 45 * 1024**3:
        raise ValueError("Audition requires at least 45 GiB VRAM")
    config = plan["config"]
    report_path = output / "report.json"
    report = (validate_report(output, plan, require_complete=False) if report_path.exists()
              else {"plan_hash": plan["plan_hash"], "created_at": now(), "images": []})
    report["status"] = "running"
    write_json(report_path, report)
    deadline = time.monotonic() + max_seconds

    def check_deadline(pipe, step, timestep, kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Golden audition sampling deadline reached")
        return kwargs

    try:
        card = Path(hf_hub_download(config["model_id"], "README.md",
                                    revision=config["model_revision"]))
        if sha256(card) != config["model_card_sha256"]:
            raise ValueError("Model card differs from reviewed provenance")
        pipe = QwenImagePipeline.from_pretrained(
            config["model_id"], revision=config["model_revision"],
            torch_dtype=torch.bfloat16, use_safetensors=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        (output / "images").mkdir(exist_ok=True)
        environment = {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
                       "cpu_offload": True, "vae_tiling": True}
        report["environment"] = environment
        for job in plan["jobs"]:
            prior = next((r for r in report["images"] if r["job"]["id"] == job["id"]), None)
            if completed(output, prior, job):
                continue
            if time.monotonic() >= deadline:
                raise TimeoutError("Golden deadline reached before next image")
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            with torch.no_grad():
                result = pipe(
                    prompt=job["prompt"], negative_prompt=config["negative_prompt"],
                    width=config["width"], height=config["height"],
                    num_inference_steps=config["steps"], true_cfg_scale=config["true_cfg_scale"],
                    generator=torch.Generator(device="cuda").manual_seed(job["seed"]),
                    callback_on_step_end=check_deadline,
                ).images[0]
            destination = output / "images" / f"{job['id']}.png"
            temporary = destination.with_suffix(".tmp")
            result.save(temporary, format="PNG")
            temporary.replace(destination)
            report["images"].append({
                "job": job, "image": f"images/{destination.name}",
                "image_sha256": sha256(destination), "generated_at": now(),
                "seconds": time.monotonic() - started,
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "environment": environment, "curation_decision": "pending",
            })
            write_json(report_path, report)
            print(f"Saved candidate {len(report['images'])}/{len(plan['jobs'])}: {job['id']}",
                  flush=True)
        report["status"] = "completed"
    except Exception as error:
        report["status"] = "failed"
        report["error_type"] = type(error).__name__
        raise
    finally:
        report["updated_at"] = now()
        write_json(report_path, report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan", "run", "verify"])
    parser.add_argument("--max-seconds", type=int, default=2400)
    args = parser.parse_args()
    output = ROOT / OUTPUT
    plan = make_plan()
    if args.command == "plan":
        if (output / "plan.json").exists() and read_json(output / "plan.json") != plan:
            raise ValueError("Existing plan differs; never overwrite an experiment")
        write_json(output / "plan.json", plan)
        print(f"Eight candidates locked: {plan['plan_hash']}")
    elif args.command == "verify":
        if read_json(output / "plan.json") != plan:
            raise ValueError("Plan differs from locked inputs")
        report = validate_report(output, plan)
        print(f"Verified {len(report['images'])} candidates; none approved for training")
    else:
        if not 60 <= args.max_seconds <= 3000:
            parser.error("max-seconds must be 60..3000")
        sample(output, args.max_seconds)


if __name__ == "__main__":
    main()
