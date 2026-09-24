"""Run the locked 100-step LoRA pilot and its matched evaluation on one CUDA GPU."""

import argparse
import importlib.metadata
import importlib.util
import platform
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import remote_train as smoke  # noqa: E402

from emoji_studio.common import now, read_json, write_json  # noqa: E402
from emoji_studio.training_data import verify_export  # noqa: E402

CONFIG = ROOT / "configs/lora-quality-pilot.json"
OUTPUT = ROOT / "runs/lora-quality-pilot"
REPORT = ROOT / "runs/lora-quality-pilot-report.json"


def replace_arg(command, name, value):
    index = command.index(name)
    command[index + 1] = str(value)


def training_command(root=ROOT):
    config = read_json(root / "configs/lora-quality-pilot.json")
    command = smoke.training_args(root, config["max_steps"])
    replace_arg(command, "--output_dir", root / "runs/lora-quality-pilot")
    replace_arg(command, "--resolution", config["resolution"])
    replace_arg(command, "--rank", config["rank"])
    replace_arg(command, "--learning_rate", config["learning_rate"])
    replace_arg(command, "--train_batch_size", config["batch_size"])
    replace_arg(command, "--gradient_accumulation_steps", config["gradient_accumulation"])
    replace_arg(command, "--checkpointing_steps", config["checkpoint_steps"])
    replace_arg(command, "--checkpoints_total_limit", len(config["checkpoint_adapters"]))
    return command


def adapters_have_equal_tensors(first, second):
    import torch
    from safetensors.torch import load_file

    first_tensors = load_file(first)
    second_tensors = load_file(second)
    return first_tensors.keys() == second_tensors.keys() and all(
        torch.equal(first_tensors[name], second_tensors[name]) for name in first_tensors
    )


def preserve_checkpoint_adapters(config):
    adapter_dir = OUTPUT / "adapters"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    records = []
    for step in config["checkpoint_adapters"]:
        source_dir = OUTPUT / f"checkpoint-{step}"
        validated = smoke.validate_adapter(source_dir)
        destination = adapter_dir / f"step-{step}.safetensors"
        shutil.copy2(source_dir / "pytorch_lora_weights.safetensors", destination)
        records.append(
            {
                "step": step,
                "path": str(destination.relative_to(ROOT)),
                "sha256": smoke.sha256(destination),
                "tensor_count": validated["tensor_count"],
                "target_categories": validated["target_categories"],
                "all_finite": validated["all_finite"],
            }
        )
    return records


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
        config = read_json(CONFIG)
        base_config = read_json(ROOT / "configs/lora-pilot.json")
        manifest = verify_export(ROOT / "data/training/pilot-v1")
        if config["experiment"] != "lora_100_step_quality_pilot_v1":
            raise ValueError("Unexpected quality-pilot experiment identifier")
        if config["export_hash"] != manifest["export_hash"]:
            raise ValueError("Training export differs from the locked quality-pilot input")
        if config["trainer_sha256"] != smoke.sha256(smoke.TRAINER):
            raise ValueError("Pinned trainer differs from the quality-pilot configuration")
        if config["trainer_revision"] != smoke.TRAINER_REVISION:
            raise ValueError("Trainer revision differs")
        if config["model_id"] != base_config["model_id"]:
            raise ValueError("Pilot model differs from the prepared model")
        if config["model_revision"] != base_config["model_revision"]:
            raise ValueError("Pilot model revision differs from the prepared model")
        if config["mixed_precision"] != base_config["mixed_precision"]:
            raise ValueError("Pilot precision differs from the prepared configuration")
        if OUTPUT.exists():
            raise ValueError("Quality-pilot output already exists; refusing to overwrite it")

        import torch

        if not torch.cuda.is_available() or not torch.cuda.is_bf16_supported():
            raise ValueError("CUDA with BF16 support is required")
        spec = importlib.util.spec_from_file_location("pinned_klein_trainer", smoke.TRAINER)
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
            "trainer_sha256": smoke.sha256(smoke.TRAINER),
        }
        write_json(REPORT, report)

        command = training_command(ROOT)
        if any(
            flag in command for flag in ["--push_to_hub", "--random_flip", "--train_text_encoder"]
        ):
            raise ValueError("Unsafe or out-of-scope training option enabled")
        training_result = smoke.run_monitored(
            command, ROOT / "quality-pilot.log", deadline, f"checkpoint-{config['max_steps']}"
        )
        if "optimizer_step_seconds" in training_result:
            training_result["one_hundred_steps_seconds"] = training_result.pop(
                "optimizer_step_seconds"
            )
        report["phases"]["training"] = training_result
        report["checkpoint_adapters"] = preserve_checkpoint_adapters(config)
        report["final_adapter"] = smoke.validate_adapter(OUTPUT)
        step_100 = OUTPUT / "adapters/step-100.safetensors"
        final_adapter = OUTPUT / "pytorch_lora_weights.safetensors"
        if not adapters_have_equal_tensors(step_100, final_adapter):
            raise ValueError("Step-100 checkpoint tensors differ from the final adapter")
        report["step_100_matches_final_tensors"] = True
        write_json(REPORT, report)

        remaining = int(deadline - time.monotonic() - 30)
        if remaining < 300:
            raise TimeoutError("Less than five minutes remain for matched evaluation")
        evaluation = [
            sys.executable,
            str(ROOT / "scripts/evaluate_lora.py"),
            "--output",
            str(OUTPUT),
            "--max-seconds",
            str(min(1800, remaining)),
        ]
        report["phases"]["evaluation_process"] = smoke.run_monitored(
            evaluation, ROOT / "quality-pilot.log", deadline
        )
        evaluation_report = read_json(OUTPUT / "evaluation/report.json")
        if evaluation_report.get("status") != "completed":
            raise ValueError("Matched evaluation did not complete")
        if evaluation_report.get("adapter_sha256") != report["final_adapter"]["sha256"]:
            raise ValueError("Evaluation used a different adapter")
        report["evaluation"] = {
            "report": "runs/lora-quality-pilot/evaluation/report.json",
            "benchmark_sha256": evaluation_report["benchmark_sha256"],
            "adapter_sha256": evaluation_report["adapter_sha256"],
            "counts": evaluation_report["counts"],
            "matched_pairs": config["evaluation"]["expected_pairs"],
        }
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
    if not 900 <= args.max_seconds <= 3600:
        parser.error("max-seconds must be between 900 and 3600")
    main(args.max_seconds)
