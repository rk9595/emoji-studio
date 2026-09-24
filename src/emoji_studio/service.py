import asyncio
import gc
import hashlib
import hmac
import io
import json
import random
import shutil
import threading
import time
import uuid
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageStat

from .common import now, read_json, write_json

TERMINAL_STATES = {"succeeded", "failed"}


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _background_color(image):
    rgb = image.convert("RGB")
    width, height = rgb.size
    edge = []
    for x in range(width):
        edge.extend((rgb.getpixel((x, 0)), rgb.getpixel((x, height - 1))))
    for y in range(1, height - 1):
        edge.extend((rgb.getpixel((0, y)), rgb.getpixel((width - 1, y))))
    edge_image = Image.new("RGB", (len(edge), 1))
    edge_image.putdata(edge)
    return tuple(round(value) for value in ImageStat.Stat(edge_image).median)


def make_sticker(image, size=512, padding_ratio=0.08, tolerance=20, feather=18):
    """Remove an approximately flat edge background, crop, and pad to a square canvas."""
    if not 32 <= size <= 2048:
        raise ValueError("Sticker size must be between 32 and 2048")
    rgb = image.convert("RGB")
    background = Image.new("RGB", rgb.size, _background_color(rgb))
    difference_rgb = ImageChops.difference(rgb, background)
    difference = ImageChops.lighter(
        difference_rgb.getchannel("R"),
        ImageChops.lighter(difference_rgb.getchannel("G"), difference_rgb.getchannel("B")),
    )
    low = max(0, tolerance)
    high = max(low + 1, low + feather)
    alpha = difference.point(
        lambda value: (
            0 if value <= low else 255 if value >= high else (value - low) * 255 // (high - low)
        )
    )
    alpha = alpha.filter(ImageFilter.GaussianBlur(radius=max(0.5, feather / 8)))
    rgba = rgb.convert("RGBA")
    rgba.putalpha(alpha)
    box = alpha.getbbox()
    if box is None:
        raise ValueError("Background removal found no foreground")
    cropped = rgba.crop(box)
    padding = max(1, round(size * padding_ratio))
    available = size - 2 * padding
    cropped.thumbnail((available, available), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - cropped.width) // 2
    y = (size - cropped.height) // 2
    canvas.alpha_composite(cropped, (x, y))
    return canvas


class JobStore:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def create(self, prompts, seeds, request_id, owner_id="default-admin"):
        job_id = uuid.uuid4().hex
        created_at = now()
        job = {
            "id": job_id,
            "request_id": request_id,
            "owner_id": owner_id,
            "status": "queued",
            "prompts": prompts,
            "seeds": seeds,
            "created_at": created_at,
            "updated_at": created_at,
            "results": [],
            "error": None,
        }
        with self._lock:
            write_json(self.root / job_id / "job.json", job)
            write_json(
                self.root / ".usage" / owner_id / f"{job_id}.json",
                {
                    "job_id": job_id,
                    "owner_id": owner_id,
                    "created_at": created_at,
                    "image_count": len(seeds),
                },
            )
        return job

    def list(self, owner_id, limit=50):
        jobs = []
        for path in self.root.glob("*/job.json"):
            try:
                job = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if job.get("owner_id", "default-admin") == owner_id:
                jobs.append(job)
        jobs.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return jobs[:limit]

    def images_created_since(self, owner_id, since):
        count = 0
        for path in (self.root / ".usage" / owner_id).glob("*.json"):
            try:
                event = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if event.get("created_at", "") >= since:
                count += int(event.get("image_count", 0))
        return count

    def total_images_created(self):
        count = 0
        for path in (self.root / ".usage").glob("*/*.json"):
            try:
                event = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            count += int(event.get("image_count", 0))
        return count

    def get(self, job_id):
        if not isinstance(job_id, str) or not job_id.isalnum():
            return None
        path = self.root / job_id / "job.json"
        if not path.is_file():
            return None
        with self._lock:
            return read_json(path)

    def update(self, job_id, **changes):
        with self._lock:
            path = self.root / job_id / "job.json"
            job = read_json(path)
            job.update(changes)
            job["updated_at"] = now()
            write_json(path, job)
        return job

    def pending_ids(self):
        result = []
        for path in sorted(self.root.glob("*/job.json")):
            try:
                job = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if job.get("status") in {"queued", "running"}:
                if job["status"] == "running":
                    self.update(job["id"], status="queued", error=None)
                result.append(job["id"])
        return result

    def artifact(self, job_id, filename):
        if not filename or Path(filename).name != filename:
            return None
        path = self.root / job_id / "images" / filename
        return path if path.is_file() else None

    def save_feedback(self, job_id, owner_id, feedback):
        with self._lock:
            job = read_json(self.root / job_id / "job.json")
            if job.get("owner_id", "default-admin") != owner_id:
                return None
            write_json(self.root / job_id / "feedback.json", feedback)
        return feedback

    def delete(self, job_id, owner_id=None):
        with self._lock:
            folder = self.root / job_id
            path = folder / "job.json"
            if not path.is_file():
                return False
            job = read_json(path)
            if owner_id is not None and job.get("owner_id", "default-admin") != owner_id:
                return False
            if job.get("status") not in TERMINAL_STATES:
                raise ValueError("Only completed or failed jobs can be deleted")
            shutil.rmtree(folder)
        return True

    def delete_expired(self, cutoff):
        deleted = []
        for path in sorted(self.root.glob("*/job.json")):
            try:
                job = read_json(path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if job.get("status") in TERMINAL_STATES and job.get("finished_at", "") < cutoff:
                if self.delete(job["id"]):
                    deleted.append(job["id"])
        return deleted


class Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self.counters = Counter()
        self.gauges = {
            "emoji_studio_queue_depth": 0,
            "emoji_studio_queue_depth_max": 0,
            "emoji_studio_model_loaded": 0,
        }
        self.generation_seconds = []
        self.cost_dollars = 0.0
        self.peak_vram_bytes = 0

    def record_job(self, status):
        with self._lock:
            self.counters[f"emoji_studio_jobs_total:{status}"] += 1

    def record_image(self, seconds, cost, peak_vram_bytes=0):
        with self._lock:
            self.counters["emoji_studio_images_generated_total:ok"] += 1
            self.generation_seconds.append(seconds)
            self.cost_dollars += cost
            self.peak_vram_bytes = max(self.peak_vram_bytes, peak_vram_bytes or 0)

    def set_gauge(self, name, value):
        with self._lock:
            self.gauges[name] = value

    def prometheus(self):
        with self._lock:
            lines = [
                "# HELP emoji_studio_queue_depth Jobs waiting for the GPU worker.",
                "# TYPE emoji_studio_queue_depth gauge",
                f"emoji_studio_queue_depth {self.gauges['emoji_studio_queue_depth']}",
                "# HELP emoji_studio_queue_depth_max Highest observed queued-job count.",
                "# TYPE emoji_studio_queue_depth_max gauge",
                f"emoji_studio_queue_depth_max {self.gauges['emoji_studio_queue_depth_max']}",
                "# HELP emoji_studio_model_loaded Whether model weights are resident.",
                "# TYPE emoji_studio_model_loaded gauge",
                f"emoji_studio_model_loaded {self.gauges['emoji_studio_model_loaded']}",
                "# TYPE emoji_studio_jobs_total counter",
            ]
            for key, value in sorted(self.counters.items()):
                name, label = key.split(":", 1)
                if name == "emoji_studio_jobs_total":
                    lines.append(f'{name}{{status="{label}"}} {value}')
            lines.extend(
                [
                    "# TYPE emoji_studio_images_generated_total counter",
                    f'emoji_studio_images_generated_total{{status="ok"}} {self.counters["emoji_studio_images_generated_total:ok"]}',
                    "# TYPE emoji_studio_generation_seconds summary",
                    f"emoji_studio_generation_seconds_count {len(self.generation_seconds)}",
                    f"emoji_studio_generation_seconds_sum {sum(self.generation_seconds):.6f}",
                    "# TYPE emoji_studio_estimated_cost_dollars counter",
                    f"emoji_studio_estimated_cost_dollars {self.cost_dollars:.8f}",
                    "# TYPE emoji_studio_peak_vram_bytes gauge",
                    f"emoji_studio_peak_vram_bytes {self.peak_vram_bytes}",
                ]
            )
        return "\n".join(lines) + "\n"


class MockRenderer:
    """Deterministic renderer used only for local integration and load tests."""

    loaded = False

    def render(self, prompt, seed):
        started = time.monotonic()
        self.loaded = True
        digest = hashlib.sha256(f"{prompt}\0{seed}".encode()).digest()
        image = Image.new("RGB", (512, 512), (250, 248, 243))
        draw = ImageDraw.Draw(image)
        color = tuple(40 + value % 180 for value in digest[:3])
        inset = 80 + digest[3] % 45
        draw.rounded_rectangle((inset, inset, 512 - inset, 512 - inset), radius=70, fill=color)
        draw.ellipse((196, 200, 224, 228), fill="black")
        draw.ellipse((288, 200, 316, 228), fill="black")
        draw.arc((190, 210, 322, 350), 20, 160, fill="black", width=12)
        return image, {
            "generation_seconds": round(time.monotonic() - started, 6),
            "peak_vram_bytes": 0,
            "renderer": "mock",
        }

    def unload(self):
        self.loaded = False


class FluxRenderer:
    def __init__(self, root, config_path):
        self.root = Path(root)
        self.config = read_json(config_path)
        self.pipeline = None
        adapter = self.root / self.config["adapter_path"]
        if not adapter.is_file() or _sha256(adapter) != self.config["adapter_sha256"]:
            raise ValueError("Serving adapter is missing or differs from its locked checksum")
        self.adapter = adapter

    @property
    def loaded(self):
        return self.pipeline is not None

    def _load(self):
        if self.pipeline is not None:
            return
        import torch
        from diffusers import Flux2KleinPipeline

        if not torch.cuda.is_available():
            raise RuntimeError("CUDA is required for the FLUX renderer")
        if torch.cuda.device_count() != 1:
            raise RuntimeError("The initial serving milestone requires exactly one visible GPU")
        pipeline = Flux2KleinPipeline.from_pretrained(
            self.config["model_id"],
            revision=self.config["model_revision"],
            torch_dtype=torch.bfloat16,
            use_safetensors=True,
        )
        pipeline.load_lora_weights(self.adapter.parent, weight_name=self.adapter.name)
        pipeline.to("cuda")
        pipeline.set_progress_bar_config(disable=True)
        self.pipeline = pipeline

    def render(self, prompt, seed):
        import torch

        self._load()
        torch.cuda.reset_peak_memory_stats()
        torch.cuda.synchronize()
        started = time.monotonic()
        with torch.inference_mode():
            image = self.pipeline(
                prompt=prompt + self.config["style_suffix"],
                width=self.config["resolution"],
                height=self.config["resolution"],
                num_inference_steps=self.config["steps"],
                guidance_scale=self.config["guidance_scale"],
                generator=torch.Generator(device="cuda").manual_seed(seed),
            ).images[0]
        torch.cuda.synchronize()
        return image, {
            "generation_seconds": round(time.monotonic() - started, 6),
            "peak_vram_bytes": torch.cuda.max_memory_allocated(),
            "renderer": "flux2-klein-lora",
        }

    def unload(self):
        if self.pipeline is None:
            return
        import torch

        self.pipeline = None
        gc.collect()
        torch.cuda.empty_cache()


class VastServerlessRenderer:
    """Synchronous renderer facade for a Vast @remote function."""

    def __init__(self, deployment_app=None, remote_render=None):
        if deployment_app is None or remote_render is None:
            from deployment.vast_flux import app, render

            deployment_app = app
            remote_render = render
        self.deployment_app = deployment_app
        self.remote_render = remote_render
        self._ready = False
        self._lock = threading.Lock()

    @property
    def loaded(self):
        return self._ready

    def render(self, prompt, seed):
        with self._lock:
            if not self._ready:
                self.deployment_app.ensure_ready()
                self._ready = True
        result = asyncio.run(self.remote_render(prompt, seed))
        payload = result.pop("png")
        image = Image.open(io.BytesIO(payload)).convert("RGB")
        return image, result

    def unload(self):
        # Vast owns worker idling and endpoint teardown. Clearing local readiness makes the
        # next request re-resolve the deployment instead of assuming a stale endpoint.
        self._ready = False


@dataclass
class WorkerSettings:
    hourly_cost_dollars: float = 0.0
    idle_unload_seconds: float = 300.0
    transparent: bool = True


class GenerationWorker:
    def __init__(self, store, renderer, metrics, settings=None):
        self.store = store
        self.renderer = renderer
        self.metrics = metrics
        self.settings = settings or WorkerSettings()
        self.queue = asyncio.Queue()
        self.task = None
        self._stopping = False

    async def start(self):
        self._stopping = False
        for job_id in self.store.pending_ids():
            await self.queue.put(job_id)
        self._queue_metric()
        self.task = asyncio.create_task(self._run(), name="emoji-studio-gpu-worker")

    async def stop(self):
        self._stopping = True
        if self.task:
            await self.queue.put(None)
            await self.task
        await asyncio.to_thread(self.renderer.unload)
        self.metrics.set_gauge("emoji_studio_model_loaded", 0)

    async def enqueue(self, job_id):
        await self.queue.put(job_id)
        self._queue_metric()

    def _queue_metric(self):
        depth = self.queue.qsize()
        self.metrics.set_gauge("emoji_studio_queue_depth", depth)
        self.metrics.set_gauge(
            "emoji_studio_queue_depth_max",
            max(depth, self.metrics.gauges["emoji_studio_queue_depth_max"]),
        )

    async def _run(self):
        while True:
            try:
                job_id = await asyncio.wait_for(
                    self.queue.get(), timeout=self.settings.idle_unload_seconds
                )
            except TimeoutError:
                if self.renderer.loaded:
                    await asyncio.to_thread(self.renderer.unload)
                    self.metrics.set_gauge("emoji_studio_model_loaded", 0)
                continue
            if job_id is None:
                return
            self._queue_metric()
            try:
                await self._execute(job_id)
            finally:
                self.queue.task_done()
            if self._stopping:
                return

    async def _execute(self, job_id):
        job = self.store.get(job_id)
        if not job or job["status"] in TERMINAL_STATES:
            return
        self.store.update(job_id, status="running", started_at=now())
        self.metrics.record_job("running")
        results = []
        try:
            for index, (prompt, seed) in enumerate(zip(job["prompts"], job["seeds"], strict=True)):
                image, render_metrics = await asyncio.to_thread(self.renderer.render, prompt, seed)
                self.metrics.set_gauge("emoji_studio_model_loaded", int(self.renderer.loaded))
                output = make_sticker(image) if self.settings.transparent else image.convert("RGBA")
                folder = self.store.root / job_id / "images"
                folder.mkdir(parents=True, exist_ok=True)
                png_name = f"{index:02d}-{seed}.png"
                webp_name = f"{index:02d}-{seed}.webp"
                png_buffer = io.BytesIO()
                output.save(png_buffer, format="PNG", optimize=True)
                self._commit_artifact(folder / png_name, png_buffer.getvalue())
                webp_buffer = io.BytesIO()
                output.save(webp_buffer, format="WEBP", lossless=True, quality=100)
                self._commit_artifact(folder / webp_name, webp_buffer.getvalue())
                seconds = float(render_metrics["generation_seconds"])
                cost = seconds * self.settings.hourly_cost_dollars / 3600
                result = {
                    "prompt": prompt,
                    "seed": seed,
                    "png_url": f"/v1/generations/{job_id}/artifacts/{png_name}",
                    "webp_url": f"/v1/generations/{job_id}/artifacts/{webp_name}",
                    "width": output.width,
                    "height": output.height,
                    "transparent": self.settings.transparent,
                    "metrics": {**render_metrics, "estimated_cost_dollars": round(cost, 8)},
                }
                results.append(result)
                self.store.update(job_id, results=results)
                self.metrics.record_image(seconds, cost, render_metrics.get("peak_vram_bytes", 0))
            self.store.update(job_id, status="succeeded", finished_at=now(), results=results)
            self.metrics.record_job("succeeded")
        except Exception as error:
            self.store.update(
                job_id,
                status="failed",
                finished_at=now(),
                results=results,
                error=f"{type(error).__name__}: {error}",
            )
            self.metrics.record_job("failed")

    @staticmethod
    def _commit_artifact(path, payload):
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_bytes(payload)
        temporary.replace(path)


class RetentionManager:
    def __init__(self, store, retention_days=7, interval_seconds=3600):
        if not 1 <= retention_days <= 365:
            raise ValueError("Retention days must be between 1 and 365")
        self.store = store
        self.retention_days = retention_days
        self.interval_seconds = max(1, interval_seconds)
        self.task = None
        self._stopping = asyncio.Event()

    def cleanup(self):
        cutoff = (datetime.now(UTC) - timedelta(days=self.retention_days)).isoformat()
        return self.store.delete_expired(cutoff)

    async def start(self):
        self._stopping.clear()
        self.task = asyncio.create_task(self._run(), name="emoji-studio-retention")

    async def stop(self):
        self._stopping.set()
        if self.task:
            await self.task

    async def _run(self):
        while not self._stopping.is_set():
            await asyncio.to_thread(self.cleanup)
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_seconds)
            except TimeoutError:
                pass


def create_seeds(count, explicit_seed=None):
    if explicit_seed is not None:
        if not 0 <= explicit_seed <= 2**32 - 1:
            raise ValueError("Seed must fit an unsigned 32-bit integer")
        return [(explicit_seed + offset) % 2**32 for offset in range(count)]
    source = random.SystemRandom()
    return [source.randrange(0, 2**32) for _ in range(count)]


def authorized(header, expected):
    if not expected or not header or not header.startswith("Bearer "):
        return False
    return hmac.compare_digest(header[7:], expected)
