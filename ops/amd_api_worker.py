"""One-process, two-render real HTTP acceptance test on the AMD image.

The legacy API is deliberately tested without changing its production defaults.
No restart or POST retry is supported. The GPU is deleted by external controllers.
"""

import argparse
import hashlib
import io
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

from emoji_studio.render_budget import RenderBudget

PROMPTS = ["a cheerful red apple sticker", "a happy yellow smiling face emoji"]


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


class BoundedRenderer:
    def __init__(self, renderer, budget, deadline, clock=time.time):
        self.renderer, self.budget, self.deadline, self.clock = renderer, budget, deadline, clock

    @property
    def loaded(self):
        return self.renderer.loaded

    def unload(self):
        self.renderer.unload()

    def render(self, prompt, seed):
        if self.clock() >= self.deadline:
            raise RuntimeError("smoke_deadline_reached")
        index = self.budget.snapshot()["consumed"]
        request_hash = digest(json.dumps([prompt, seed]).encode())

        def invoke():
            if self.clock() >= self.deadline:
                raise RuntimeError("smoke_deadline_reached")
            result = self.renderer.render(prompt, seed)
            if self.clock() >= self.deadline:
                raise RuntimeError("smoke_deadline_reached")
            return result

        return self.budget.run(f"image-{index}", request_hash, invoke)


def serve(args):
    import uvicorn

    from emoji_studio.api import create_app
    from emoji_studio.service import FluxRenderer, MockRenderer

    root = Path.cwd()
    renderer = MockRenderer() if args.mock else FluxRenderer(root, root / "configs/serving.json")
    budget = RenderBudget.create(
        Path("smoke-private/render-budget.sqlite"), allocation_id=args.allocation,
        plan_sha256=digest(Path("ops/amd-api-live-plan.json").read_bytes()),
    )
    app = create_app(root, api_key=Path("smoke-private/api-key").read_text(),
                     renderer=BoundedRenderer(renderer, budget, args.deadline),
                     jobs_dir=root / "smoke-private/jobs", trial_image_cap=2,
                     hourly_cost_dollars=1.99, idle_unload_seconds=1800)
    uvicorn.run(app, host="127.0.0.1", port=args.port, access_log=False, log_level="warning")


def run(args):
    import httpx
    from PIL import Image

    os.umask(0o077)
    private = Path("smoke-private")
    private.mkdir(mode=0o700, exist_ok=True)
    # Single-use even if a prior process died before the server was ready.
    with (private / "started").open("x") as marker:
        marker.write(str(time.time()))
    outputs = Path("api-results")
    outputs.mkdir(mode=0o700, exist_ok=False)
    report = {"status": "starting", "mock": args.mock, "allocation_id": args.allocation,
              "images": [], "prompts": PROMPTS}
    if not args.mock:
        import torch
        if not torch.version.hip or not torch.cuda.is_available() or torch.cuda.device_count() != 1:
            raise RuntimeError("Exactly one visible AMD ROCm GPU is required")
        if not torch.cuda.is_bf16_supported():
            raise RuntimeError("BF16 support required")
        report["environment"] = {"torch": torch.__version__, "hip": torch.version.hip,
                                 "gpu": torch.cuda.get_device_name(0), "gpu_count": 1}
    config = json.loads(Path("configs/serving.json").read_text())
    report["model_id"] = config["model_id"]
    report["model_revision"] = config["model_revision"]
    report["adapter_sha256"] = config["adapter_sha256"]
    key = secrets.token_urlsafe(32)
    (private / "api-key").write_text(key)
    server_args = [sys.executable, __file__, "serve", "--allocation", args.allocation,
                   "--deadline", str(args.deadline), "--port", str(args.port)]
    if args.mock:
        server_args.append("--mock")
    started = time.time()
    with (private / "server.log").open("w") as log:
        server = subprocess.Popen(server_args, stdout=log, stderr=log)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{args.port}", timeout=10,
                          headers={"Authorization": "Bearer " + key}) as client:
            while time.time() < min(args.deadline, started + 60):
                if server.poll() is not None:
                    raise RuntimeError("API server stopped")
                try:
                    if client.get("/healthz").status_code == 200:
                        break
                except httpx.TransportError:
                    pass
                time.sleep(1)
            else:
                raise TimeoutError("API did not become healthy")
            assert client.get("/v1/me", headers={"Authorization": "Bearer invalid"}).status_code == 401
            response = client.post("/v1/generations", json={"prompts": PROMPTS, "seed": 7})
            assert response.status_code == 202, response.status_code
            job_id = response.json()["id"]
            report["job_id"] = job_id
            while time.time() < args.deadline:
                response = client.get(f"/v1/generations/{job_id}")
                response.raise_for_status()
                job = response.json()
                if job["status"] in ("succeeded", "failed"):
                    break
                time.sleep(3)
            else:
                raise TimeoutError("Generation deadline")
            if job["status"] != "succeeded":
                # Job error contains no credentials; preserve actionable inference diagnostics.
                report["job_error"] = job.get("error")
                raise RuntimeError("API generation failed")
            assert len(job["results"]) == 2
            # Test the admission cap, which must reject before any additional render.
            assert client.post("/v1/generations", json={"prompt": "blocked third image"}).status_code == 429
            for index, item in enumerate(job["results"]):
                evidence = {"prompt": item["prompt"], "seed": item["seed"], "metrics": item["metrics"]}
                pixels = []
                for extension in ("png", "webp"):
                    response = client.get(item[f"{extension}_url"])
                    response.raise_for_status()
                    data = response.content
                    assert len(data) <= 4 * 1024 * 1024
                    image = Image.open(io.BytesIO(data))
                    image.load()
                    assert image.size == (512, 512) and image.mode == "RGBA"
                    assert image.getchannel("A").getextrema()[0] < 255
                    pixels.append(image.tobytes())
                    name = f"emoji-{index}.{extension}"
                    (outputs / name).write_bytes(data)
                    evidence[extension] = {"path": name, "sha256": digest(data), "bytes": len(data)}
                # Ignore RGB under fully transparent pixels when comparing lossless formats.
                a = Image.open(outputs / f"emoji-{index}.png").convert("RGBA")
                b = Image.open(outputs / f"emoji-{index}.webp").convert("RGBA")
                background = Image.new("RGBA", a.size, "white")
                assert Image.alpha_composite(background, a).tobytes() == Image.alpha_composite(background, b).tobytes()
                report["images"].append(evidence)
            report.update(status="completed", elapsed_seconds=round(time.time() - started, 3),
                          authentication_checked=True, third_image_rejected=True)
    except BaseException as error:
        report.update(status="failed", error=type(error).__name__)
        raise
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)
        ledger = private / "render-budget.sqlite"
        if ledger.exists():
            report["render_budget"] = RenderBudget(
                ledger, allocation_id=args.allocation,
                plan_sha256=digest(Path("ops/amd-api-live-plan.json").read_bytes()),
            ).snapshot()
        (outputs / "report.json").write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "serve"])
    parser.add_argument("--allocation", required=True)
    parser.add_argument("--deadline", type=float, required=True)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--mock", action="store_true")
    arguments = parser.parse_args()
    (serve if arguments.command == "serve" else run)(arguments)
