"""Run the bounded two-step LoRA save/resume smoke check on one CUDA GPU."""

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.common import now, read_json, write_json  # noqa: E402
from emoji_studio.training_data import verify_export  # noqa: E402

OUTPUT = ROOT / "runs/lora-pilot-smoke"
REPORT = ROOT / "runs/training-smoke-report.json"
TRAINER_REVISION = "d035dcd7cc7c88e0a154609b62887d50bba9fdc2"
TRAINER = ROOT / "artifacts/trainers" / TRAINER_REVISION / "train_dreambooth_lora_flux2_klein.py"
EXPECTED_EXPORT_HASH = "0eaf81532ebbc8d382d5f709df179f00652914a097001a61ffaa629fe1739581"
EXPECTED_TRAINER_HASH = "de02782d47ce4535eb9efad49bd90de1ddf9bebcd4313d344d3b1bbb5d536c53"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def training_args(root, max_steps, resume=False):
    config = read_json(root / "configs/lora-pilot.json")
    args = [
        sys.executable,
        str(
            root
            / "artifacts/trainers"
            / config["trainer_revision"]
            / Path(config["trainer_script"]).name
        ),
        "--pretrained_model_name_or_path",
        config["model_id"],
        "--revision",
        config["model_revision"],
        "--dataset_name",
        str(root / "data/training/pilot-v1/train"),
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
        str(max_steps),
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
        "--skip_final_inference",
    ]
    if config["gradient_checkpointing"]:
        args.append("--gradient_checkpointing")
    if resume:
        args.extend(["--resume_from_checkpoint", "latest"])
    return args


def gpu_memory_mib():
    result = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=used_memory",
            "--format=csv,noheader,nounits",
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    values = [int(line.strip()) for line in result.stdout.splitlines() if line.strip().isdigit()]
    return max(values, default=0)


def run_monitored(command, log_path, deadline, checkpoint_name=None):
    started = time.monotonic()
    events = {}
    lock = threading.Lock()
    with log_path.open("ab", buffering=0) as log:
        log.write(("\nCOMMAND " + json.dumps(command) + "\n").encode())
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )

        def copy_output():
            for raw in iter(process.stdout.readline, b""):
                log.write(raw)
                text = raw.decode("utf-8", errors="replace")
                with lock:
                    if "***** Running training *****" in text:
                        events.setdefault("training_started", time.monotonic())
                    if checkpoint_name and "Saved state to " in text and checkpoint_name in text:
                        events.setdefault("checkpoint_saved", time.monotonic())

        reader = threading.Thread(target=copy_output, daemon=True)
        reader.start()
        peak_mib = 0
        while process.poll() is None:
            if time.monotonic() >= deadline:
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                reader.join(timeout=10)
                raise TimeoutError("Training-smoke deadline reached")
            try:
                peak_mib = max(peak_mib, gpu_memory_mib())
            except (OSError, subprocess.SubprocessError, ValueError):
                pass
            time.sleep(1)
        reader.join(timeout=10)
    finished = time.monotonic()
    if process.returncode != 0:
        raise subprocess.CalledProcessError(process.returncode, command)
    result = {
        "wall_seconds": round(finished - started, 4),
        "peak_observed_gpu_memory_mib": peak_mib,
    }
    with lock:
        if "training_started" in events and "checkpoint_saved" in events:
            result["optimizer_step_seconds"] = round(
                events["checkpoint_saved"] - events["training_started"], 4
            )
    return result


def validate_adapter(output):
    import torch
    from safetensors.torch import load_file

    adapter = output / "pytorch_lora_weights.safetensors"
    if not adapter.is_file():
        raise ValueError("Final LoRA weights are missing")
    tensors = load_file(adapter)
    if not tensors:
        raise ValueError("Final LoRA contains no tensors")
    if not all(torch.isfinite(tensor).all().item() for tensor in tensors.values()):
        raise ValueError("Final LoRA contains non-finite values")
    categories = {
        name
        for name in ["to_k", "to_q", "to_v", "to_out", "to_qkv_mlp_proj"]
        if any(name in key for key in tensors)
    }
    expected = {"to_k", "to_q", "to_v", "to_out", "to_qkv_mlp_proj"}
    if categories != expected:
        raise ValueError(f"Saved adapter target categories differ: {sorted(categories)}")
    return {
        "path": str(adapter.relative_to(ROOT)),
        "sha256": sha256(adapter),
        "tensor_count": len(tensors),
        "target_categories": sorted(categories),
        "all_finite": True,
    }


def main(max_seconds):
    started = time.monotonic()
    deadline = started + max_seconds
    report = {
        "status": "running",
        "started_at": now(),
        "max_seconds": max_seconds,
        "training_authorized_by_remote_code": False,
        "phases": {},
    }
    write_json(REPORT, report)
    try:
        config = read_json(ROOT / "configs/lora-pilot.json")
        manifest = verify_export(ROOT / "data/training/pilot-v1")
        if manifest["export_hash"] != EXPECTED_EXPORT_HASH:
            raise ValueError("Training export hash differs from the locked smoke input")
        if sha256(TRAINER) != EXPECTED_TRAINER_HASH:
            raise ValueError("Pinned trainer hash differs")
        if config["trainer_revision"] != TRAINER_REVISION:
            raise ValueError("Trainer revision differs")

        import torch

        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise ValueError("CUDA with BF16 support is required")
        spec = importlib.util.spec_from_file_location("pinned_klein_trainer", TRAINER)
        trainer_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(trainer_module)
        report["environment"] = {
            "python": platform.python_version(),
            "platform": platform.platform(),
            "gpu": torch.cuda.get_device_name(0),
            "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
            "cuda": torch.version.cuda,
            "packages": {
                name: importlib.metadata.version(name)
                for name in [
                    "accelerate",
                    "datasets",
                    "diffusers",
                    "peft",
                    "safetensors",
                    "tensorboard",
                    "torch",
                    "torchvision",
                    "transformers",
                ]
            },
            "full_trainer_import": True,
            "export_hash": manifest["export_hash"],
            "trainer_sha256": sha256(TRAINER),
        }
        write_json(REPORT, report)

        log_path = ROOT / "training.log"
        first = training_args(ROOT, 1)
        if "--push_to_hub" in first or "--random_flip" in first:
            raise ValueError("Unsafe training option enabled")
        report["phases"]["first_step"] = run_monitored(first, log_path, deadline, "checkpoint-1")
        if not (OUTPUT / "checkpoint-1").is_dir():
            raise ValueError("First checkpoint was not saved")
        report["first_adapter"] = validate_adapter(OUTPUT)
        write_json(REPORT, report)

        resumed = training_args(ROOT, 2, resume=True)
        report["phases"]["resumed_step"] = run_monitored(
            resumed, log_path, deadline, "checkpoint-2"
        )
        if not (OUTPUT / "checkpoint-2").is_dir():
            raise ValueError("Resumed checkpoint was not saved")
        log_text = log_path.read_text(errors="replace")
        if "Resuming from checkpoint checkpoint-1" not in log_text:
            raise ValueError("Trainer did not confirm checkpoint reload")
        report["final_adapter"] = validate_adapter(OUTPUT)
        if report["first_adapter"]["sha256"] == report["final_adapter"]["sha256"]:
            raise ValueError("Adapter did not change after the resumed optimizer step")
        write_json(REPORT, report)

        inference = [
            sys.executable,
            str(ROOT / "scripts/verify_lora_adapter.py"),
            "--output",
            str(OUTPUT),
        ]
        report["phases"]["adapter_inference"] = run_monitored(inference, log_path, deadline)
        inference_report = read_json(OUTPUT / "adapter-inference.json")
        if inference_report.get("adapter_sha256") != report["final_adapter"]["sha256"]:
            raise ValueError("Inference did not use the final adapter")
        report["adapter_inference"] = inference_report
        report["status"] = "completed"
    except BaseException as error:
        report["status"] = "failed"
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        report["finished_at"] = now()
        report["total_wall_seconds"] = round(time.monotonic() - started, 4)
        write_json(REPORT, report)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds", type=int, required=True)
    args = parser.parse_args()
    if not 60 <= args.max_seconds <= 7200:
        parser.error("max-seconds must be between 60 and 7200")
    main(args.max_seconds)
