"""One-shot AMD finite-loss smoke, coverage training and bounded evaluation."""

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
OUT = ROOT / "training-results"
PLAN = ROOT / "ops/amd-training-live-plan.json"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(report):
    path = OUT / "report.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(path)


def retain(path, name, report):
    target = OUT / name
    if not target.exists():
        temporary = target.with_suffix(".tmp")
        shutil.copyfile(path, temporary)
        temporary.replace(target)
    if sha(path) != sha(target):
        raise ValueError("Retained artifact changed")
    report["files"][name] = {"sha256": sha(target), "bytes": target.stat().st_size}
    save(report)


def validate_adapter(path):
    import torch
    from safetensors.torch import load_file

    values = load_file(str(path), device="cpu")
    if len(values) != 120 or not all(torch.isfinite(value).all().item() for value in values.values()):
        raise ValueError("Adapter tensor count or finiteness failed")
    if not any("lora_B" in name and torch.count_nonzero(value).item() for name, value in values.items()):
        raise ValueError("Adapter contains no learned LoRA B values")
    return {"sha256": sha(path), "tensors": len(values), "all_finite": True}


def collect_checkpoints(report):
    for step in (125, 250, 375, 500):
        path = ROOT / f"runs/fluent-coverage-v1/checkpoint-{step}/pytorch_lora_weights.safetensors"
        name = f"step-{step}.safetensors"
        if name in report["files"] or not path.exists():
            continue
        try:
            validate_adapter(path)
        except Exception:
            continue  # A checkpoint still being written is checked on the next pass.
        retain(path, name, report)


def phase(command, deadline, report, name):
    if time.time() >= deadline:
        raise TimeoutError("No phase time remains")
    started = time.time()
    with (OUT / f"{name}.log").open("xb") as log:
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   stdin=subprocess.DEVNULL, start_new_session=True)
        try:
            while process.poll() is None:
                if time.time() >= deadline:
                    raise TimeoutError("Training phase deadline")
                collect_checkpoints(report)
                time.sleep(5)
            if process.returncode:
                raise RuntimeError(f"Phase {name} exited {process.returncode}")
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
    child = json.loads((OUT / "report.json").read_bytes())
    report["files"].update(child["files"])
    report["images"] = child["images"]
    report["phases"][name] = {"seconds": round(time.time() - started, 3), "exit_code": 0}
    save(report)


def train(bundle_name, deadline, report, name):
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator

    from emoji_studio.coverage_training import argument_values

    bundle = ROOT / "artifacts/trainers" / bundle_name
    recipe = json.loads((bundle / "recipe.json").read_bytes())
    output = ROOT / recipe["output"]
    values = {**argument_values(recipe), "dataset_name": str(ROOT / recipe["dataset"] / "train"),
              "output_dir": str(output)}
    argv = [part for key, value in values.items() for part in ("--" + key, str(value))]
    argv += ["--center_crop", "--cache_latents", "--skip_final_inference", "--gradient_checkpointing"]
    phase([sys.executable, str(bundle / "train_coverage.py"), *argv], deadline, report, name)
    events = list((output / "logs").rglob("events.out.tfevents.*"))
    losses = []
    for event in events:
        reader = EventAccumulator(str(event), size_guidance={"scalars": 0}).Reload()
        if "loss" in reader.Tags()["scalars"]:
            losses.extend(reader.Scalars("loss"))
    expected = recipe["max_steps"] * recipe["batch_size"] * recipe["gradient_accumulation"]
    if (len(losses) != expected or not all(math.isfinite(item.value) for item in losses)
            or max(item.step for item in losses) != recipe["max_steps"]):
        raise ValueError("Finite loss count or completed optimizer steps differ")
    adapter = output / "pytorch_lora_weights.safetensors"
    report["phases"][name].update(loss_values=len(losses), all_losses_finite=True,
                                  completed_steps=recipe["max_steps"], adapter=validate_adapter(adapter))
    retain(adapter, "smoke.safetensors" if name == "smoke" else "step-624.safetensors", report)
    collect_checkpoints(report)
    save(report)


def render(kind, deadline):
    import torch
    from diffusers import Flux2KleinPipeline

    report = json.loads((OUT / "report.json").read_bytes())
    recipe = json.loads((ROOT / "configs/lora-coverage-v1.json").read_bytes())
    pipeline = Flux2KleinPipeline.from_pretrained(recipe["model_id"], revision=recipe["model_revision"],
                                                 torch_dtype=torch.bfloat16, use_safetensors=True).to("cuda")
    pipeline.set_progress_bar_config(disable=True)

    def cutoff(pipe, step, timestep, values):
        if time.time() >= deadline:
            raise TimeoutError("Render cutoff")
        return values

    if kind == "reload":
        smoke = json.loads((ROOT / "configs/lora-coverage-smoke-v1.json").read_bytes())["evaluation"]
        conditions = [("smoke", [{"id": "smoke", "prompt": smoke["reload_prompt"]}], [0], 4)]
    else:
        prompts = json.loads((ROOT / recipe["evaluation"]["benchmark"]).read_bytes())["prompts"]
        conditions = [(f"step-{step}", prompts, [0, 1], 50) for step in (500, 624)]
    index = 0
    for condition, prompts, seeds, steps in conditions:
        pipeline.load_lora_weights(str(OUT), weight_name=f"{condition}.safetensors")
        for prompt in prompts:
            for seed in seeds:
                if time.time() >= deadline:
                    raise TimeoutError("Render cutoff")
                filename = "smoke.png" if kind == "reload" else f"evaluation-{index:02d}.png"
                if (OUT / filename).exists() or index >= 48:
                    raise ValueError("Render claim already consumed or image cap exceeded")
                # Claim before invoking a GPU render; no retry after interruption.
                (OUT / (filename + ".claim")).touch(exist_ok=False)
                started = time.time()
                with torch.inference_mode():
                    image = pipeline(prompt=prompt["prompt"], width=512, height=512,
                                     num_inference_steps=steps, guidance_scale=4,
                                     generator=torch.Generator(device="cuda").manual_seed(seed),
                                     callback_on_step_end=cutoff).images[0]
                if image.size != (512, 512):
                    raise ValueError("Wrong evaluation dimensions")
                image.save(OUT / filename, format="PNG")
                report["images"].append({"file": filename, "condition": condition,
                                         "adapter_sha256": report["files"][f"{condition}.safetensors"]["sha256"],
                                         "prompt_id": prompt["id"], "prompt": prompt["prompt"],
                                         "seed": seed, "steps": steps, "seconds": time.time() - started})
                retain(OUT / filename, filename, report)
                index += 1
        pipeline.unload_lora_weights()


def inventory():
    return {dist.metadata["Name"].lower().replace("_", "-"): dist.version
            for dist in importlib.metadata.distributions()}


def run(deadline, allocation):
    import torch

    os.umask(0o077)
    OUT.mkdir(mode=0o700, exist_ok=False)
    plan = json.loads(PLAN.read_bytes())
    for name, checksum in plan["source_files"].items():
        if sha(ROOT / name) != checksum:
            raise ValueError("Frozen input checksum differs")
    if (not torch.version.hip or torch.version.cuda is not None or torch.cuda.device_count() != 1
            or not torch.cuda.is_bf16_supported()):
        raise ValueError("Exactly one BF16 AMD GPU required")
    if torch.cuda.get_device_properties(0).total_memory < 48 * 1024**3:
        raise ValueError("Insufficient GPU memory")
    if os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") < 96 * 1024**3:
        raise ValueError("Insufficient host memory")
    before, after = json.loads(Path("training-base-packages.json").read_bytes()), inventory()
    protected = {name for name in before if name.startswith(("torch", "triton", "pytorch-triton", "rocm", "hip", "amd", "nvidia", "cuda")) or name == "apex"}
    if any(before[name] != after.get(name) for name in protected):
        raise ValueError("Provider GPU stack changed")
    report = {"status": "running", "allocation_id": allocation, "plan_sha256": sha(PLAN),
              "recipe_sha256": sha("configs/lora-coverage-v1.json"), "files": {}, "images": [],
              "phases": {}, "environment": {"torch": torch.__version__, "hip": torch.version.hip,
                                             "gpu": torch.cuda.get_device_name(0)},
              "protected_packages_unchanged": sorted(protected), "gpu_count": 1}
    save(report)
    try:
        train("coverage-smoke-v1", min(deadline - 1800, time.time() + 900), report, "smoke")
        phase([sys.executable, __file__, "reload", "--deadline", str(min(deadline - 1500, time.time() + 300))],
              min(deadline - 1500, time.time() + 300), report, "reload")
        # Child render process adds image records; reload before publishing later state.
        rendered = json.loads((OUT / "report.json").read_bytes())
        report["files"], report["images"] = rendered["files"], rendered["images"]
        train("coverage-v1", deadline - 600, report, "training")
        phase([sys.executable, __file__, "evaluate", "--deadline", str(deadline)], deadline, report, "evaluation")
        rendered = json.loads((OUT / "report.json").read_bytes())
        report["files"], report["images"] = rendered["files"], rendered["images"]
        if len(report["images"]) != 49:
            raise ValueError("Expected one smoke image and 48 development images")
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=type(error).__name__ + ": " + str(error)[:500])
        raise
    finally:
        child = json.loads((OUT / "report.json").read_bytes())
        report["files"].update(child["files"])
        report["images"] = child["images"]
        save(report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["inventory", "run", "reload", "evaluate"])
    parser.add_argument("--deadline", type=float)
    parser.add_argument("--allocation", type=int)
    args = parser.parse_args()
    if args.command == "inventory":
        Path("training-base-packages.json").write_text(json.dumps(inventory()))
    elif args.command == "run":
        run(args.deadline, args.allocation)
    else:
        render(args.command, args.deadline)
