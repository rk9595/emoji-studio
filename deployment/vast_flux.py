"""Bounded one-worker Vast Deployment for the selected Emoji Studio adapter."""

import asyncio
import gc
import hashlib
import io
import json
import time
from pathlib import Path

from vastai import Deployment
from vastai.data.query import (
    compute_cap,
    dph_total,
    gpu_ram,
    num_gpus,
    reliability,
)

ROOT = Path(__file__).resolve().parents[1]
REMOTE_ROOT = Path("/opt/emoji-studio")
SERVING_CONFIG = REMOTE_ROOT / "serving.json"
ADAPTER = REMOTE_ROOT / "step-25.safetensors"
IMAGE = "pytorch/pytorch@sha256:b85566342b86d13a67712e9315d40cdc2dad7f8d86df1aff3831f80835edbcca"

# The endpoint is destroyed after an unattended client disappears. The worker itself can
# scale to zero sooner. Re-running ensure_ready recreates the same named deployment.
app = Deployment(name="emoji-studio-flux", tag="alpha-v1", version_label="0.1.0", ttl=1800)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@app.context()
class FluxContext:
    async def __aenter__(self):
        import torch
        from diffusers import Flux2KleinPipeline

        config = json.loads(SERVING_CONFIG.read_text())
        if _sha256(ADAPTER) != config["adapter_sha256"]:
            raise ValueError("Deployed adapter differs from the locked serving checksum")
        if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Emoji Studio serverless inference requires exactly one CUDA GPU")
        pipeline = Flux2KleinPipeline.from_pretrained(
            config["model_id"],
            revision=config["model_revision"],
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
        )
        pipeline.load_lora_weights(ADAPTER.parent, weight_name=ADAPTER.name)
        pipeline.to("cuda")
        pipeline.set_progress_bar_config(disable=True)
        self.config = config
        self.pipeline = pipeline
        self.lock = asyncio.Lock()
        return self

    async def __aexit__(self, *exc):
        import torch

        self.pipeline = None
        gc.collect()
        torch.cuda.empty_cache()


@app.remote(
    benchmark_dataset=[{"prompt": "a smiling apple", "seed": 7}],
    benchmark_runs=1,
)
async def render(prompt: str, seed: int) -> dict:
    import torch

    if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 500:
        raise ValueError("Prompt must contain 1 to 500 characters")
    if type(seed) is not int or not 0 <= seed <= 2**32 - 1:
        raise ValueError("Seed must fit an unsigned 32-bit integer")
    context = app.get_context(FluxContext)
    async with context.lock:
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        with torch.inference_mode():
            image = await asyncio.to_thread(
                context.pipeline,
                prompt=prompt.strip() + context.config["style_suffix"],
                width=context.config["resolution"],
                height=context.config["resolution"],
                num_inference_steps=context.config["steps"],
                guidance_scale=context.config["guidance_scale"],
                generator=torch.Generator(device="cuda").manual_seed(seed),
            )
        torch.cuda.synchronize()
        buffer = io.BytesIO()
        image.images[0].convert("RGB").save(buffer, format="PNG", optimize=True)
        return {
            "png": buffer.getvalue(),
            "generation_seconds": round(time.monotonic() - started, 6),
            "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            "renderer": "vast-serverless-flux2-klein-lora",
            "adapter_sha256": context.config["adapter_sha256"],
        }


image = app.image(IMAGE, 80)
image.pip_install(
    "torch==2.10.0",
    "diffusers==0.40.0",
    "peft>=0.17,<1",
    "transformers==5.17.0",
    "accelerate>=1.10,<2",
    "safetensors>=0.5,<1",
    "sentencepiece>=0.2,<1",
    "pillow>=11.3,<13",
)
image.copy(str(ROOT / "configs/serving.json"), str(SERVING_CONFIG))
image.copy(str(ROOT / "runs/lora-quality-pilot/adapters/step-25.safetensors"), str(ADAPTER))
image.require(
    num_gpus == 1,
    gpu_ram >= 40_000,
    compute_cap >= 800,
    reliability >= 0.98,
    dph_total <= 0.70,
)
app.configure_autoscaling(
    cold_workers=0,
    max_workers=1,
    min_load=0,
    min_cold_load=0,
    cold_mult=0,
    target_util=0.9,
    max_queue_time=180.0,
    target_queue_time=30.0,
    inactivity_timeout=600,
)
