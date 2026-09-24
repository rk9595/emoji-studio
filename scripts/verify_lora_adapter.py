"""Load the saved adapter into the pinned base pipeline and render one smoke image."""

import argparse
import hashlib
import json
import time
from pathlib import Path

import torch
from diffusers import Flux2KleinPipeline

MODEL_ID = "black-forest-labs/FLUX.2-klein-base-4B"
MODEL_REVISION = "a3b4f4849157f664bdbc776fd7453c2783562f4d"
PROMPT = "A compact blue backpack, 3D emoji illustration, centered on a white background"


def main(output):
    adapter = output / "pytorch_lora_weights.safetensors"
    if not adapter.is_file():
        raise ValueError("Adapter weights are missing")
    adapter_sha256 = hashlib.sha256(adapter.read_bytes()).hexdigest()
    started = time.monotonic()
    pipeline = Flux2KleinPipeline.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        torch_dtype=torch.bfloat16,
        use_safetensors=True,
    )
    pipeline.load_lora_weights(output)
    pipeline.enable_model_cpu_offload()
    loaded_seconds = time.monotonic() - started
    torch.cuda.reset_peak_memory_stats()
    generation_started = time.monotonic()
    with torch.inference_mode():
        image = pipeline(
            prompt=PROMPT,
            width=512,
            height=512,
            num_inference_steps=4,
            guidance_scale=4.0,
            generator=torch.Generator(device="cuda").manual_seed(0),
        ).images[0]
    torch.cuda.synchronize()
    image_path = output / "adapter-inference.png"
    temporary = image_path.with_suffix(".tmp")
    image.save(temporary, format="PNG")
    temporary.replace(image_path)
    report = {
        "adapter_sha256": adapter_sha256,
        "image": image_path.name,
        "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
        "prompt": PROMPT,
        "seed": 0,
        "steps": 4,
        "guidance_scale": 4.0,
        "model_load_and_adapter_seconds": round(loaded_seconds, 4),
        "generation_seconds": round(time.monotonic() - generation_started, 4),
        "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
        "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
    }
    report_path = output / "adapter-inference.json"
    temporary_report = report_path.with_suffix(".tmp")
    temporary_report.write_text(json.dumps(report, indent=2) + "\n")
    temporary_report.replace(report_path)
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    main(args.output.resolve())
