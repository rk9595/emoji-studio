"""Eight matched FLUX samples with/without actual reference input; no training."""

import argparse
import sys
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from sample_interaction_teacher import completed, sha256, validate_report  # noqa: E402

from emoji_studio.common import digest, now, read_json, write_json  # noqa: E402

CONFIG = "configs/high-five-reference-control.json"
OUTPUT = "runs/high-five-reference-control-v1"
REFERENCES = {
    "004": ("docs/images/high-five-teacher/qwen-hi5-004.png",
            "c51db19bc58a3a77f77cb8b699b5fc4bb4f9705a8f410aa394ec60a7d30aae4f",
            "qwen-hi5-004"),
    "1401": ("docs/images/high-five-golden/golden-d-1401.png",
             "bf424e729d5a1e49a2c63294768edd6a86238c4ff05eef35940176544263d22d",
             "golden-d-1401"),
}


def make_plan(root=ROOT):
    config = read_json(root / CONFIG)
    if (config["model_id"] != "black-forest-labs/FLUX.2-klein-base-4B"
            or config["model_revision"] != "a3b4f4849157f664bdbc776fd7453c2783562f4d"
            or config["adapter"] is not None
            or (config["width"], config["height"], config["reference_size"]) != (1024,) * 3
            or config["steps"] != 50 or config["guidance_scale"] != 4.0):
        raise ValueError("Reference comparison requires the pinned, unadapted FLUX settings")
    refs = config["references"]
    if len(refs) != 2 or {r["id"] for r in refs} != REFERENCES.keys():
        raise ValueError("Exactly the two human-selected references are required")
    tasks = config["tasks"]
    if (len(tasks) != 2 or {t["id"] for t in tasks} != {"compact", "elevated"}
            or any(t["counts_as_new_pose"] is not False for t in tasks)):
        raise ValueError("Two diagnostic tasks only; no automatic new-pose credit")
    frozen = [" ".join(r["prompt"].lower().split())
              for r in read_json(root / "benchmarks/high-five-v1.json")["prompts"]]
    jobs = []
    seeds = set()
    for ref in refs:
        if (ref["path"], ref["image_sha256"], ref["lineage"]) != REFERENCES[ref["id"]]:
            raise ValueError("Reference path, lineage or selection hash changed")
        if sha256(root / ref["path"]) != ref["image_sha256"]:
            raise ValueError("Reference image checksum failed")
        with Image.open(root / ref["path"]) as image:
            image.load()
            if image.size != (1328, 1328):
                raise ValueError("Unexpected source reference dimensions")
        for task in tasks:
            seed = ref["seed"] + task["seed_offset"]
            if type(seed) is not int or not 0 <= seed < 2**32 or seed in seeds:
                raise ValueError("Each comparison pair needs a distinct valid seed")
            seeds.add(seed)
            prompt = " ".join([config["style"], ref["composition"], task["description"]])
            if any(text in " ".join(prompt.lower().split()) for text in frozen):
                raise ValueError("Reference prompt leaks frozen evaluation text")
            pair = f"ref-{ref['id']}-{task['id']}"
            # Shared lineage also groups the paired control conservatively at curation time.
            for condition in ("text", "image"):
                jobs.append({"id": f"{pair}-{condition}", "pair_id": pair,
                             "condition": condition, "reference_id": ref["id"],
                             "reference_sha256": ref["image_sha256"] if condition == "image" else None,
                             "lineage": ref["lineage"], "task": task["id"],
                             "seed": seed, "prompt": prompt})
    payload = {"schema_version": 1, "config": config, "jobs": jobs,
               "benchmark_sha256": sha256(root / "benchmarks/high-five-v1.json"),
               "sampler_sha256": sha256(root / "scripts/sample_reference_control.py"),
               "validation_helper_sha256": sha256(root / "scripts/sample_interaction_teacher.py"),
               "lockfile_sha256": sha256(root / "uv.lock")}
    return {**payload, "plan_hash": digest(payload)}


def sample(output, max_seconds):
    plan = read_json(output / "plan.json")
    if plan != make_plan():
        raise ValueError("Reference plan differs from locked inputs")
    import torch
    from diffusers import Flux2KleinPipeline
    from huggingface_hub import hf_hub_download

    if (torch.cuda.device_count() != 1
            or torch.cuda.get_device_properties(0).total_memory < 45 * 1024**3):
        raise ValueError("This bounded trial requires exactly one GPU with at least 45 GiB")
    config = plan["config"]
    report_path = output / "report.json"
    report = (validate_report(output, plan, require_complete=False) if report_path.exists()
              else {"plan_hash": plan["plan_hash"], "created_at": now(), "images": []})
    if len(report["images"]) == len(plan["jobs"]):
        report.update(status="completed", updated_at=now())
        write_json(report_path, report)
        return
    report["status"] = "running"
    write_json(report_path, report)
    deadline = time.monotonic() + max_seconds

    def check_deadline(pipe, step, timestep, kwargs):
        if time.monotonic() >= deadline:
            raise TimeoutError("Reference comparison sampling deadline reached")
        return kwargs

    try:
        card = Path(hf_hub_download(config["model_id"], "README.md",
                                    revision=config["model_revision"]))
        if sha256(card) != config["model_card_sha256"]:
            raise ValueError("Model card differs from reviewed provenance")
        pipe = Flux2KleinPipeline.from_pretrained(
            config["model_id"], revision=config["model_revision"],
            torch_dtype=torch.bfloat16, use_safetensors=True,
        )
        pipe.enable_model_cpu_offload()
        pipe.vae.enable_tiling()
        pipe.set_progress_bar_config(disable=True)
        references = {}
        for ref in config["references"]:
            with Image.open(ROOT / ref["path"]) as image:
                references[ref["id"]] = image.convert("RGB").resize(
                    (config["reference_size"],) * 2, Image.Resampling.LANCZOS)
        (output / "images").mkdir(exist_ok=True)
        environment = {"torch": torch.__version__, "gpu": torch.cuda.get_device_name(0),
                       "cpu_offload": True, "vae_tiling": True, "adapter": None}
        report["environment"] = environment
        for job in plan["jobs"]:
            prior = next((r for r in report["images"] if r["job"]["id"] == job["id"]), None)
            if completed(output, prior, job):
                continue
            check_deadline(None, None, None, {})
            torch.cuda.reset_peak_memory_stats()
            started = time.monotonic()
            kwargs = {"prompt": job["prompt"], "width": config["width"],
                      "height": config["height"], "num_inference_steps": config["steps"],
                      "guidance_scale": config["guidance_scale"],
                      "generator": torch.Generator(device="cuda").manual_seed(job["seed"]),
                      "callback_on_step_end": check_deadline}
            if job["condition"] == "image":
                kwargs["image"] = references[job["reference_id"]].copy()
            with torch.no_grad():
                result = pipe(**kwargs).images[0]
            if result.size != (config["width"], config["height"]):
                raise ValueError("Output dimensions differ from the plan")
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
            print(f"Saved comparison {len(report['images'])}/8: {job['id']}", flush=True)
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
        print(f"Eight matched samples locked: {plan['plan_hash']}")
    elif args.command == "verify":
        if read_json(output / "plan.json") != plan:
            raise ValueError("Plan differs from locked inputs")
        report = validate_report(output, plan)
        print(f"Verified {len(report['images'])} samples; none approved for training")
    else:
        if not 60 <= args.max_seconds <= 3000:
            parser.error("max-seconds must be 60..3000")
        sample(output, args.max_seconds)


if __name__ == "__main__":
    main()
