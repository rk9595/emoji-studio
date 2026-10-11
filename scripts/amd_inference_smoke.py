#!/usr/bin/env python3
"""Run a matched base/LoRA inference smoke test on one ROCm GPU."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import platform
import time
from datetime import UTC, datetime
from pathlib import Path


def now() -> str:
    return datetime.now(UTC).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("configs/serving.json"))
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prompt", default="a cheerful yellow smiling face")
    parser.add_argument("--seed", type=int, default=29)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.root.resolve()
    config_path = args.config if args.config.is_absolute() else root / args.config
    output_dir = args.output_dir.resolve()
    report_path = output_dir / "report.json"
    config = json.loads(config_path.read_text())
    adapter_path = root / config["adapter_path"]
    actual_adapter_hash = sha256(adapter_path)
    if actual_adapter_hash != config["adapter_sha256"]:
        raise ValueError("Serving adapter is missing or differs from its locked checksum")

    import diffusers
    import torch
    import transformers
    from diffusers import Flux2KleinPipeline

    if torch.version.hip is None:
        raise RuntimeError("A ROCm PyTorch build is required")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("Exactly one visible ROCm GPU is required")
    if not torch.cuda.is_bf16_supported():
        raise RuntimeError("The visible ROCm GPU must support BF16")

    output_dir.mkdir(parents=True, exist_ok=True)
    prompt = args.prompt + config["style_suffix"]
    report = {
        "status": "loading_model",
        "started_at": now(),
        "model_id": config["model_id"],
        "model_revision": config["model_revision"],
        "adapter_path": str(adapter_path.relative_to(root)),
        "adapter_sha256": actual_adapter_hash,
        "prompt": args.prompt,
        "effective_prompt": prompt,
        "seed": args.seed,
        "resolution": config["resolution"],
        "steps": config["steps"],
        "guidance_scale": config["guidance_scale"],
        "environment": {
            "python": platform.python_version(),
            "torch": torch.__version__,
            "hip": torch.version.hip,
            "cuda": torch.version.cuda,
            "diffusers": diffusers.__version__,
            "transformers": transformers.__version__,
            "accelerate": importlib.metadata.version("accelerate"),
            "peft": importlib.metadata.version("peft"),
            "gpu": torch.cuda.get_device_name(0),
            "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
            "bf16_supported": torch.cuda.is_bf16_supported(),
        },
    }
    write_json(report_path, report)

    load_started = time.monotonic()
    pipeline = Flux2KleinPipeline.from_pretrained(
        config["model_id"],
        revision=config["model_revision"],
        torch_dtype=torch.bfloat16,
        use_safetensors=True,
    )
    pipeline.to("cuda")
    pipeline.set_progress_bar_config(disable=True)
    report["model_load_seconds"] = round(time.monotonic() - load_started, 4)
    report["status"] = "generating_base"
    write_json(report_path, report)

    def render(name: str) -> dict:
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        with torch.inference_mode():
            image = pipeline(
                prompt=prompt,
                width=config["resolution"],
                height=config["resolution"],
                num_inference_steps=config["steps"],
                guidance_scale=config["guidance_scale"],
                generator=torch.Generator(device="cuda").manual_seed(args.seed),
            ).images[0]
        torch.cuda.synchronize()
        image_path = output_dir / f"{name}.png"
        image.save(image_path)
        return {
            "path": image_path.name,
            "sha256": sha256(image_path),
            "generation_seconds": round(time.monotonic() - started, 4),
            "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
            "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
        }

    report["base"] = render("base")
    report["status"] = "loading_adapter"
    write_json(report_path, report)
    adapter_started = time.monotonic()
    pipeline.load_lora_weights(adapter_path.parent, weight_name=adapter_path.name)
    report["adapter_load_seconds"] = round(time.monotonic() - adapter_started, 4)
    report["status"] = "generating_adapted"
    write_json(report_path, report)
    report["adapted"] = render("adapted")
    report["status"] = "completed"
    report["finished_at"] = now()
    write_json(report_path, report)
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
