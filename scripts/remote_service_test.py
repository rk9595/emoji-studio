"""Exercise the real Emoji Studio service on one CUDA GPU and preserve evidence."""

import argparse
import hashlib
import io
import json
import os
import secrets
import signal
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from emoji_studio.client import EmojiStudioClient
from emoji_studio.common import write_json

ROOT = Path("/workspace/emoji-studio")
OUTPUT = ROOT / "runs/service-gpu-test"
BASE_URL = "http://127.0.0.1:8000"


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def request(path, key=None):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    with urllib.request.urlopen(
        urllib.request.Request(BASE_URL + path, headers=headers), timeout=30
    ) as response:
        body = response.read()
        return response.status, response.headers.get("content-type", ""), body


def wait_health(timeout=120):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            status, _, body = request("/healthz")
            if status == 200:
                return json.loads(body)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            pass
        time.sleep(1)
    raise TimeoutError("Service did not become healthy")


def gpu_monitor(stop, samples):
    command = [
        "nvidia-smi",
        "--query-gpu=timestamp,name,memory.used,memory.total,utilization.gpu",
        "--format=csv,noheader,nounits",
    ]
    while not stop.wait(1):
        try:
            row = subprocess.run(command, capture_output=True, text=True, timeout=10, check=True)
            parts = [part.strip() for part in row.stdout.strip().split(",")]
            if len(parts) == 5:
                samples.append(
                    {
                        "timestamp": parts[0],
                        "gpu_name": parts[1],
                        "memory_used_mib": float(parts[2]),
                        "memory_total_mib": float(parts[3]),
                        "utilization_percent": float(parts[4]),
                    }
                )
        except (OSError, ValueError, subprocess.SubprocessError):
            pass


def image_evidence(client, job, name):
    result = job["results"][0]
    png = client.download(result["png_url"])
    webp = client.download(result["webp_url"])
    (OUTPUT / f"{name}.png").write_bytes(png)
    (OUTPUT / f"{name}.webp").write_bytes(webp)
    image = Image.open(io.BytesIO(png))
    alpha = image.getchannel("A")
    return {
        "job_id": job["id"],
        "png_sha256": hashlib.sha256(png).hexdigest(),
        "webp_sha256": hashlib.sha256(webp).hexdigest(),
        "png_bytes": len(png),
        "webp_bytes": len(webp),
        "mode": image.mode,
        "size": list(image.size),
        "alpha_extrema": list(alpha.getextrema()),
        "metrics": result["metrics"],
    }


def unauthorized_status():
    payload = json.dumps({"prompt": "must be rejected"}).encode()
    req = urllib.request.Request(
        BASE_URL + "/v1/generations",
        data=payload,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as error:
        return error.code
    return 200


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--hourly-cost", required=True, type=float)
    parser.add_argument("--requests", default=16, type=int)
    parser.add_argument("--concurrency", default=4, type=int)
    parser.add_argument("--idle-seconds", default=10, type=int)
    parser.add_argument("--timeout", default=1200, type=int)
    args = parser.parse_args()
    if not 0 < args.hourly_cost <= 0.70:
        parser.error("hourly cost is outside the authorized range")
    if args.requests != 16 or args.concurrency != 4:
        parser.error("the locked test requires 16 requests at concurrency 4")
    if OUTPUT.exists():
        raise SystemExit("Service GPU test output already exists")
    OUTPUT.mkdir(parents=True)

    api_key = secrets.token_urlsafe(32)
    environment = os.environ.copy()
    environment.update(
        {
            "EMOJI_STUDIO_API_KEY": api_key,
            "EMOJI_STUDIO_ROOT": str(ROOT),
            "EMOJI_STUDIO_RENDERER": "flux",
            "EMOJI_STUDIO_HOURLY_COST_DOLLARS": str(args.hourly_cost),
            "EMOJI_STUDIO_IDLE_UNLOAD_SECONDS": str(args.idle_seconds),
            "PORT": "8000",
        }
    )
    samples = []
    stop_monitor = threading.Event()
    monitor = threading.Thread(target=gpu_monitor, args=(stop_monitor, samples), daemon=True)
    monitor.start()
    started = time.time()
    server = None
    report = {
        "status": "failed",
        "requests": args.requests,
        "concurrency": args.concurrency,
        "hourly_cost_dollars": args.hourly_cost,
        "adapter_sha256": sha256(ROOT / "runs/lora-quality-pilot/adapters/step-25.safetensors"),
        "serving_config_sha256": sha256(ROOT / "configs/serving.json"),
    }
    try:
        service_log = (OUTPUT / "service.log").open("wb", buffering=0)
        server = subprocess.Popen(
            ["uv", "run", "emoji-studio-api"],
            cwd=ROOT,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=service_log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        report["initial_health"] = wait_health()
        report["unauthorized_status"] = unauthorized_status()
        client = EmojiStudioClient(BASE_URL, api_key, timeout=60)

        smoke = []
        for index in range(2):
            cold_started = time.monotonic()
            job = client.generate("a smiling orange rocket", seed=424242)
            complete = client.wait(job["id"], poll_seconds=0.25, timeout=args.timeout)
            evidence = image_evidence(client, complete, f"smoke-{index + 1}")
            evidence["end_to_end_seconds"] = round(time.monotonic() - cold_started, 4)
            smoke.append(evidence)
        report["smoke"] = smoke
        report["deterministic_png_match"] = smoke[0]["png_sha256"] == smoke[1]["png_sha256"]
        report["deterministic_webp_match"] = smoke[0]["webp_sha256"] == smoke[1]["webp_sha256"]

        load_env = environment.copy()
        result = subprocess.run(
            [
                "uv",
                "run",
                "python",
                "scripts/load_test_service.py",
                "--url",
                BASE_URL,
                "--requests",
                str(args.requests),
                "--concurrency",
                str(args.concurrency),
                "--timeout",
                str(args.timeout),
            ],
            cwd=ROOT,
            env=load_env,
            capture_output=True,
            text=True,
            timeout=args.timeout + 120,
        )
        (OUTPUT / "load-test.stdout").write_text(result.stdout)
        (OUTPUT / "load-test.stderr").write_text(result.stderr)
        report["load_test_exit"] = result.returncode
        report["load_test"] = json.loads(result.stdout)

        _, _, metrics = request("/metrics", api_key)
        (OUTPUT / "metrics.prom").write_bytes(metrics)
        report["post_load_health"] = json.loads(request("/healthz")[2])

        idle_deadline = time.monotonic() + args.idle_seconds + 60
        idle_health = report["post_load_health"]
        while time.monotonic() < idle_deadline:
            idle_health = json.loads(request("/healthz")[2])
            if not idle_health["model_loaded"]:
                break
            time.sleep(1)
        report["idle_health"] = idle_health
        metrics_text = metrics.decode()
        report["checks"] = {
            "authentication": report["unauthorized_status"] == 401,
            "determinism": report["deterministic_png_match"] and report["deterministic_webp_match"],
            "transparent_exports": all(
                row["mode"] == "RGBA" and row["alpha_extrema"] == [0, 255] for row in smoke
            ),
            "load_test": result.returncode == 0
            and report["load_test"]["completed"] == args.requests
            and report["load_test"]["failed"] == 0,
            "metrics": 'emoji_studio_images_generated_total{status="ok"} 18' in metrics_text,
            "idle_unload": not idle_health["model_loaded"],
        }
        report["status"] = "completed" if all(report["checks"].values()) else "failed_checks"
    except Exception as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        if server is not None and server.poll() is None:
            os.killpg(server.pid, signal.SIGINT)
            try:
                server.wait(timeout=60)
            except subprocess.TimeoutExpired:
                os.killpg(server.pid, signal.SIGKILL)
                server.wait(timeout=30)
        stop_monitor.set()
        monitor.join(timeout=15)
        report["wall_seconds"] = round(time.time() - started, 4)
        report["gpu_samples"] = len(samples)
        report["peak_sampled_gpu_memory_mib"] = max(
            (row["memory_used_mib"] for row in samples), default=None
        )
        report["peak_sampled_gpu_utilization_percent"] = max(
            (row["utilization_percent"] for row in samples), default=None
        )
        write_json(OUTPUT / "gpu-samples.json", samples)
        write_json(OUTPUT / "report.json", report)
    print(json.dumps(report, indent=2))
    raise SystemExit(0 if report["status"] == "completed" else 1)


if __name__ == "__main__":
    main()
