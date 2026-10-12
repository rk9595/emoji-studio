"""Checksum-locked, resumable AMD comparison and offline blinded review builder."""

import argparse
import hashlib
import json
import random
import shutil
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def plan(root=ROOT):
    config_path = root / "configs/amd-comparison.json"
    config = json.loads(config_path.read_text())
    benchmark_path = root / config["benchmark"]
    benchmark = json.loads(benchmark_path.read_text())
    ids = [row["id"] for row in config["conditions"]]
    if len(set(ids)) != len(ids) or config["incumbent"] not in ids:
        raise ValueError("Duplicate conditions or missing incumbent")
    for row in config["conditions"]:
        if row["path"] and sha256(root / row["path"]) != row["sha256"]:
            raise ValueError(f"Adapter checksum mismatch: {row['id']}")
    pairs = []
    for prompt in benchmark["prompts"]:
        for seed in config["seeds"]:
            pairs.append({
                "pair_id": f"{prompt['id']}-seed-{seed}",
                "prompt": prompt["prompt"], "category": prompt["category"],
                "criteria": prompt["criteria"], "seed": seed,
            })
    if len(pairs) * len(ids) != config["expected_images"]:
        raise ValueError("Image count differs from recipe")
    lock = {"config_sha256": sha256(config_path), "benchmark_sha256": sha256(benchmark_path)}
    return config, pairs, lock


def verify(output, config, pairs, lock, require_complete=True):
    report = json.loads((output / "report.json").read_text())
    if any(report.get(key) != value for key, value in lock.items()):
        raise ValueError("Report inputs differ from locked recipe")
    expected = {(c["id"], p["pair_id"]): (c, p)
                for c in config["conditions"] for p in pairs}
    seen = set()
    for row in report["images"]:
        key = row["condition"], row["pair_id"]
        if key in seen or key not in expected:
            raise ValueError("Duplicate or unknown image")
        condition, pair = expected[key]
        if row["adapter_sha256"] != condition["sha256"] or any(
            row.get(k) != pair[k] for k in ("prompt", "seed", "category", "criteria")
        ):
            raise ValueError("Image metadata differs from recipe")
        path = output / row["image"]
        if not path.resolve().is_relative_to(output.resolve()) or sha256(path) != row["sha256"]:
            raise ValueError("Unsafe, missing, or corrupt image")
        seen.add(key)
    if require_complete and (report["status"] != "completed" or seen != set(expected)):
        raise ValueError("Comparison is incomplete")
    return report


def review(output, root=ROOT):
    config, pairs, lock = plan(root)
    report = verify(output, config, pairs, lock)
    rows = {(r["condition"], r["pair_id"]): r for r in report["images"]}
    assets = output / "review-assets"
    assets.mkdir(exist_ok=True)
    comparisons, mapping = [], []
    rng = random.Random(lock["config_sha256"])
    for pair in pairs:
        for candidate in config["conditions"]:
            if candidate["id"] == config["incumbent"]:
                continue
            sides = [config["incumbent"], candidate["id"]]
            rng.shuffle(sides)
            cid = hashlib.sha256(f"{pair['pair_id']}:{candidate['id']}".encode()).hexdigest()[:20]
            public = {"id": cid, **pair}
            private = {"id": cid, "pair_id": pair["pair_id"]}
            for side, condition in zip(("left", "right"), sides, strict=True):
                row = rows[condition, pair["pair_id"]]
                name = hashlib.sha256(f"{cid}:{side}".encode()).hexdigest()[:24] + ".png"
                shutil.copyfile(output / row["image"], assets / name)
                public[f"{side}_image"] = f"review-assets/{name}"
                private[f"{side}_condition"] = condition
                private[f"{side}_sha256"] = row["sha256"]
            comparisons.append(public)
            mapping.append(private)
    rng.shuffle(comparisons)
    review_id = hashlib.sha256(json.dumps(comparisons, sort_keys=True).encode()).hexdigest()
    payload = {"schema_version": 1, "review_id": review_id, "comparisons": comparisons}
    template = (root / "scripts/checkpoint_review.html").read_text()
    (output / "checkpoint-review.html").write_text(
        template.replace("__REVIEW_DATA__", json.dumps(payload).replace("<", "\\u003c"))
    )
    save(output / "blind-map.json", {"review_id": review_id, "comparisons": mapping})
    return {"verified_images": len(rows), "comparisons": len(comparisons), "review_id": review_id}


def evaluate(output, max_seconds=2400, root=ROOT):
    import torch
    from diffusers import Flux2KleinPipeline

    config, pairs, lock = plan(root)
    if not torch.version.hip or not torch.cuda.is_available():
        raise RuntimeError("ROCm GPU required")
    output.mkdir(parents=True, exist_ok=True)
    path = output / "report.json"
    report = {**lock, "status": "running", "images": [], "model": config["model_id"],
              "environment": {"torch": torch.__version__, "hip": torch.version.hip,
                              "gpu": torch.cuda.get_device_name(0)}}
    if path.exists():
        prior = verify(output, config, pairs, lock, require_complete=False)
        if prior["environment"] != report["environment"]:
            raise ValueError("Refusing to mix different runtimes in a matched comparison")
        report["images"] = prior["images"]
    save(path, report)
    start = time.monotonic()

    def deadline(pipe, step, timestep, kwargs):
        if time.monotonic() - start >= max_seconds:
            raise TimeoutError("Comparison time limit reached")
        return kwargs

    try:
        pipe = Flux2KleinPipeline.from_pretrained(
            config["model_id"], revision=config["model_revision"],
            torch_dtype=torch.bfloat16, use_safetensors=True,
        ).to("cuda")
        pipe.set_progress_bar_config(disable=True)
        for condition in config["conditions"]:
            if condition["path"]:
                adapter = root / condition["path"]
                pipe.load_lora_weights(adapter.parent, weight_name=adapter.name,
                                       adapter_name=condition["id"])
        existing = {(r["condition"], r["pair_id"]) for r in report["images"]}
        for condition in config["conditions"]:
            if condition["path"]:
                pipe.enable_lora()
                pipe.set_adapters(condition["id"])
            else:
                pipe.disable_lora()
            for pair in pairs:
                if (condition["id"], pair["pair_id"]) in existing:
                    continue
                deadline(None, None, None, {})
                torch.cuda.reset_peak_memory_stats()
                torch.cuda.synchronize()
                began = time.monotonic()
                with torch.no_grad():
                    image = pipe(
                        prompt=pair["prompt"], width=config["resolution"],
                        height=config["resolution"], num_inference_steps=config["steps"],
                        guidance_scale=config["guidance_scale"],
                        generator=torch.Generator(device="cuda").manual_seed(pair["seed"]),
                        callback_on_step_end=deadline,
                    ).images[0]
                torch.cuda.synchronize()
                destination = output / condition["id"] / f"{pair['pair_id']}.png"
                destination.parent.mkdir(exist_ok=True)
                temporary = destination.with_suffix(".tmp")
                image.save(temporary, format="PNG")
                temporary.replace(destination)
                report["images"].append({
                    **pair, "condition": condition["id"], "adapter_sha256": condition["sha256"],
                    "image": destination.relative_to(output).as_posix(), "sha256": sha256(destination),
                    "seconds": round(time.monotonic() - began, 4),
                    "peak_allocated_bytes": torch.cuda.max_memory_allocated(),
                })
                save(path, report)
                print(f"saved {len(report['images'])}/{config['expected_images']}", flush=True)
        report["status"] = "completed"
    except BaseException as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["wall_seconds"] = round(time.monotonic() - start, 4)
        save(path, report)
    return review(output, root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["plan", "run", "review"])
    parser.add_argument("--output", type=Path, default=ROOT / "runs/amd-comparison-v1")
    parser.add_argument("--max-seconds", type=int, default=2400)
    args = parser.parse_args()
    if args.command == "plan":
        recipe, pairs, lock = plan()
        result = {**lock, "pairs": len(pairs), "conditions": len(recipe["conditions"]),
                  "images": recipe["expected_images"]}
    elif args.command == "review":
        result = review(args.output)
    else:
        result = evaluate(args.output, args.max_seconds)
    print(json.dumps(result, indent=2))
