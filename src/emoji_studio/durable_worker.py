"""Local single-renderer adapter for the opt-in durable API; no provisioning."""

import asyncio
import hashlib
import io
import math
import time
import uuid

from PIL import Image

from .service import make_sticker
from .worker_queue import LeaseLost


def render_pack(renderer, lease, hourly_cost=0.0):
    outputs, results = {}, []
    for index, (prompt, seed) in enumerate(
        zip(lease.payload["prompts"], lease.payload["seeds"], strict=True)
    ):
        image, raw_metrics = renderer.render(prompt, seed)
        if not isinstance(image, Image.Image) or not all(32 <= size <= 2048 for size in image.size):
            raise ValueError("Renderer returned an unsupported image")
        seconds = float(raw_metrics["generation_seconds"])
        peak = raw_metrics.get("peak_vram_bytes", 0)
        name = raw_metrics.get("renderer", type(renderer).__name__)
        if (
            not math.isfinite(seconds)
            or seconds < 0
            or type(peak) is not int
            or peak < 0
            or not isinstance(name, str)
            or not 1 <= len(name) <= 128
        ):
            raise ValueError("Renderer metrics are invalid")
        sticker = make_sticker(image)
        paths = {}
        for extension in ("png", "webp"):
            buffer = io.BytesIO()
            sticker.save(buffer, format=extension.upper(), lossless=True)
            content = buffer.getvalue()
            with Image.open(io.BytesIO(content)) as decoded:
                decoded.load()
                if (
                    decoded.format != extension.upper()
                    or decoded.mode != "RGBA"
                    or decoded.size != (512, 512)
                    or decoded.getchannel("A").getextrema()[0] != 0
                ):
                    raise ValueError("Invalid encoded sticker")
            filename = f"{index:02d}-{seed}.{extension}"
            outputs[filename] = content
            paths[f"{extension}_url"] = f"/v1/generations/{lease.job_id}/artifacts/{filename}"
        results.append(
            {
                "prompt": prompt,
                "seed": seed,
                **paths,
                "width": 512,
                "height": 512,
                "transparent": True,
                "metrics": {
                    "generation_seconds": seconds,
                    "peak_vram_bytes": peak,
                    "renderer": name,
                    "estimated_cost_dollars": round(seconds * hourly_cost / 3600, 8),
                },
            }
        )
    return outputs, results


class DurableWorker:
    def __init__(
        self,
        store,
        renderer,
        metrics,
        *,
        ttl=60,
        poll_seconds=0.1,
        idle_unload_seconds=300,
        hourly_cost=0.0,
    ):
        if type(ttl) is not int or not 1 <= ttl <= 3600:
            raise ValueError("Invalid lease TTL")
        if not all(math.isfinite(v) and v > 0 for v in (poll_seconds, idle_unload_seconds)):
            raise ValueError("Invalid worker interval")
        if not math.isfinite(hourly_cost) or hourly_cost < 0:
            raise ValueError("Invalid hourly cost")
        self.store, self.renderer, self.metrics = store, renderer, metrics
        self.ttl, self.poll_seconds = ttl, poll_seconds
        self.idle_unload_seconds, self.hourly_cost = idle_unload_seconds, hourly_cost
        self.worker_id = "local-" + uuid.uuid4().hex
        self.stopping = asyncio.Event()
        self.task = None
        self.last_error = None

    async def start(self):
        self.stopping.clear()
        self.task = asyncio.create_task(self._run(), name="emoji-durable-local-worker")

    async def stop(self):
        self.stopping.set()
        try:
            if self.task:
                await self.task
        finally:
            await asyncio.to_thread(self.renderer.unload)
            self.metrics.set_gauge("emoji_studio_model_loaded", 0)

    async def _renew(self, lease, finished):
        while not finished.is_set():
            try:
                await asyncio.wait_for(finished.wait(), self.ttl / 3)
            except TimeoutError:
                await asyncio.to_thread(self.store.heartbeat, lease, ttl=self.ttl)

    async def _execute(self, lease):
        finished = asyncio.Event()
        renewal = asyncio.create_task(self._renew(lease, finished))
        self.metrics.record_job("running")
        try:
            try:
                outputs, results = await asyncio.to_thread(
                    render_pack, self.renderer, lease, self.hourly_cost
                )
            finally:
                finished.set()
                await renewal
            hashes = {
                name: hashlib.sha256(content).hexdigest() for name, content in outputs.items()
            }
            await asyncio.to_thread(self.store.complete, lease, outputs, hashes, results=results)
            self.metrics.record_job("succeeded")
            for result in results:
                metrics = result["metrics"]
                self.metrics.record_image(
                    metrics["generation_seconds"],
                    metrics["estimated_cost_dollars"],
                    metrics["peak_vram_bytes"],
                )
        except LeaseLost:
            # The old process may finish rendering, but it cannot publish stale outputs.
            self.metrics.record_job("lease_lost")
        except Exception as error:
            self.last_error = type(error).__name__
            try:
                await asyncio.to_thread(
                    self.store.fail, lease, error=self.last_error + ": worker failed"
                )
                self.metrics.record_job("failed")
            except LeaseLost:
                pass
        finally:
            self.metrics.set_gauge("emoji_studio_model_loaded", int(self.renderer.loaded))

    async def _run(self):
        last_work = time.monotonic()
        while not self.stopping.is_set():
            try:
                lease = await asyncio.to_thread(self.store.claim, self.worker_id, ttl=self.ttl)
                depth = await asyncio.to_thread(self.store.pending_count)
                self.metrics.set_gauge("emoji_studio_queue_depth", depth)
                self.metrics.set_gauge(
                    "emoji_studio_queue_depth_max",
                    max(depth, self.metrics.gauges["emoji_studio_queue_depth_max"]),
                )
                if lease:
                    self.last_error = None
                    await self._execute(lease)
                    last_work = time.monotonic()
                    continue
                if (
                    self.renderer.loaded
                    and time.monotonic() - last_work >= self.idle_unload_seconds
                ):
                    await asyncio.to_thread(self.renderer.unload)
                    self.metrics.set_gauge("emoji_studio_model_loaded", 0)
            except Exception as error:
                # Preserve the lease for expiry recovery after a storage failure.
                self.last_error = type(error).__name__
            try:
                await asyncio.wait_for(self.stopping.wait(), self.poll_seconds)
            except TimeoutError:
                pass
