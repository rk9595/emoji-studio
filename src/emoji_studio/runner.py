import fcntl
import hashlib
import importlib.metadata
import platform
import re
import time
import uuid

from PIL import Image

from .common import digest, now, read_json, write_json


def validate_token_lengths(plan, tokenizers):
    counts = {}
    for job in plan["jobs"]:
        counts[job["id"]] = []
        for tokenizer in tokenizers:
            count = len(tokenizer(job["prompt"], truncation=False)["input_ids"])
            limit = tokenizer.model_max_length
            if count > limit:
                raise ValueError(
                    f"Prompt {job['prompt_id']} has {count} tokens; limit is {limit}. Refusing truncation."
                )
            counts[job["id"]].append(count)
    return counts


def validate_plan(plan):
    expected = digest({k: v for k, v in plan.items() if k not in {"created_at", "experiment_hash"}})
    if plan.get("experiment_hash") != expected:
        raise ValueError("Plan integrity check failed; create a new plan instead of editing one")
    if not plan.get("jobs") or plan.get("job_count") != len(plan["jobs"]):
        raise ValueError("Plan job count is invalid")
    seen = set()
    for job in plan["jobs"]:
        job_id = job["id"]
        if not re.fullmatch(r"[0-9a-f]{20}", job_id) or job_id in seen:
            raise ValueError("Invalid or duplicate job ID")
        if job_id != digest({k: v for k, v in job.items() if k != "id"})[:20]:
            raise ValueError("Job content differs from its ID")
        if job["model"] != plan["model"]:
            raise ValueError("A run must use one model configuration")
        seen.add(job_id)
    return plan


def completed_job(run_dir, job):
    receipt_path = run_dir / "records" / f"{job['id']}.json"
    image_path = run_dir / "images" / f"{job['id']}.png"
    if not receipt_path.exists() or not image_path.exists():
        return False
    try:
        receipt = read_json(receipt_path)
        if receipt.get("status") != "completed" or receipt.get("job") != job:
            return False
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != receipt["image_sha256"]:
            return False
        with Image.open(image_path) as image:
            image.verify()
        return True
    except (ValueError, KeyError, OSError):
        return False


def execute_jobs(plan, run_dir, render, deadline, clock=time.monotonic):
    """Commit each image and receipt separately so interrupted runs can resume safely."""
    validate_plan(plan)
    (run_dir / "images").mkdir(parents=True, exist_ok=True)
    completed = skipped = failed = 0
    stopped = False
    for job in plan["jobs"]:
        if completed_job(run_dir, job):
            skipped += 1
            continue
        if clock() >= deadline:
            stopped = True
            break
        started = clock()
        receipt = {"job": job, "started_at": now()}
        try:
            image, metrics = render(job, deadline)
            image_path = run_dir / "images" / f"{job['id']}.png"
            temporary = image_path.with_suffix(".tmp")
            image.save(temporary, format="PNG")
            temporary.replace(image_path)
            receipt.update(
                {
                    "status": "completed",
                    "image": f"images/{job['id']}.png",
                    "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest(),
                    "width": image.width,
                    "height": image.height,
                    "metrics": metrics,
                    "alpha_processed": False,
                }
            )
            completed += 1
        except TimeoutError as error:
            receipt.update({"status": "interrupted", "error": str(error)})
            stopped = True
        except Exception as error:
            receipt.update({"status": "failed", "error": f"{type(error).__name__}: {error}"})
            failed += 1
        receipt["elapsed_seconds"] = round(clock() - started, 4)
        receipt["finished_at"] = now()
        write_json(run_dir / "records" / f"{job['id']}.json", receipt)
        print(f"{job['id']}: {receipt['status']}", flush=True)
        if stopped or failed:
            # Stop on the first failure; never keep charging for repeated OOM/errors.
            break
    summary = {
        "completed_this_session": completed,
        "previously_completed": skipped,
        "failed_this_session": failed,
        "stopped_at_deadline": stopped,
        "total_jobs": len(plan["jobs"]),
        "updated_at": now(),
    }
    summary["remaining"] = len(plan["jobs"]) - sum(completed_job(run_dir, j) for j in plan["jobs"])
    summary["status"] = "completed" if summary["remaining"] == 0 else "incomplete"
    write_json(run_dir / "summary.json", summary)
    return summary


def generate(plan_path, max_seconds=900, cpu_offload=False):
    if max_seconds <= 0:
        raise ValueError("max-seconds must be positive")
    plan = validate_plan(read_json(plan_path))
    run_dir = plan_path.parent
    lock = (run_dir / ".runner.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lock.close()
        raise ValueError("Another runner is already using this experiment") from None
    with lock:
        if all(completed_job(run_dir, job) for job in plan["jobs"]):
            return {"status": "completed", "remaining": 0, "model_loaded": False}
        try:
            import diffusers
            import torch
        except ImportError as error:
            raise ValueError(
                "GPU dependencies are missing. On a CUDA machine run: uv sync --extra gpu --frozen"
            ) from error
        if not torch.cuda.is_available():
            raise ValueError("This baseline runner requires CUDA; no weights were downloaded")
        config = plan["model"]
        if config["pipeline"] not in {"Flux2KleinPipeline", "StableDiffusionXLPipeline"}:
            raise ValueError("Unsupported pipeline")
        if not re.fullmatch(r"[0-9a-f]{40}", config["revision"]):
            raise ValueError("Model revision must be a pinned commit SHA")
        if config["dtype"] == "bfloat16" and not torch.cuda.is_bf16_supported():
            raise ValueError("Selected baseline requires a GPU with BF16 support")
        prompt_tokens = {}
        if config["pipeline"] == "StableDiffusionXLPipeline":
            from transformers import AutoTokenizer

            tokenizers = [
                AutoTokenizer.from_pretrained(
                    config["model_id"], subfolder=folder, revision=config["revision"]
                )
                for folder in ["tokenizer", "tokenizer_2"]
            ]
            prompt_tokens = validate_token_lengths(plan, tokenizers)
            write_json(run_dir / "prompt-preflight.json", prompt_tokens)
        started = time.monotonic()
        deadline = started + max_seconds
        env = {
            "started_at": now(),
            "python": platform.python_version(),
            "platform": platform.platform(),
            "gpu": torch.cuda.get_device_name(0),
            "gpu_memory_bytes": torch.cuda.get_device_properties(0).total_memory,
            "cuda": torch.version.cuda,
            "cpu_offload": cpu_offload,
            "packages": {
                name: importlib.metadata.version(name)
                for name in ["torch", "diffusers", "transformers", "accelerate", "pillow"]
            },
            "experiment_hash": plan["experiment_hash"],
        }
        session_path = run_dir / "sessions" / f"{uuid.uuid4().hex}.json"
        write_json(session_path, env)
        write_json(run_dir / "environment.json", env)
        pipeline_type = getattr(diffusers, config["pipeline"])
        pipeline = pipeline_type.from_pretrained(
            config["model_id"],
            revision=config["revision"],
            torch_dtype=getattr(torch, config["dtype"]),
            use_safetensors=True,
        )
        if cpu_offload:
            pipeline.enable_model_cpu_offload()
        else:
            pipeline.to("cuda")
        env["model_load_seconds"] = round(time.monotonic() - started, 4)
        env["scheduler"] = dict(pipeline.scheduler.config)
        write_json(session_path, env)
        write_json(run_dir / "environment.json", env)

        def check_deadline(pipe, step, timestep, callback_kwargs):
            if time.monotonic() >= deadline:
                raise TimeoutError("Run time limit reached during sampling")
            return callback_kwargs

        def render(job, end):
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.synchronize()
            sample_start = time.monotonic()
            kwargs = {
                "prompt": job["prompt"],
                "width": job["resolution"],
                "height": job["resolution"],
                "num_inference_steps": config["steps"],
                "guidance_scale": config["guidance_scale"],
                "generator": torch.Generator(device="cuda").manual_seed(job["seed"]),
                "callback_on_step_end": check_deadline,
            }
            with torch.inference_mode():
                image = pipeline(**kwargs).images[0]
            torch.cuda.synchronize()
            return image, {
                "generation_seconds": round(time.monotonic() - sample_start, 4),
                "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_reserved_bytes": torch.cuda.max_memory_reserved(),
                "batch_size": 1,
                "prompt_token_counts": prompt_tokens.get(job["id"]),
            }

        result = execute_jobs(plan, run_dir, render, deadline)
        result["session_seconds"] = round(time.monotonic() - started, 4)
        write_json(run_dir / "summary.json", result)
        return result
