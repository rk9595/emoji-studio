import re

from .common import digest, now, read_json, write_json

BRIEF_VERSION = "emoji-language-v2-task-first"
STYLE = "Mobile emoji, rounded 3D yellow forms, clear silhouette, centered, plain white background, no text."
MODES = {
    "emoji": "Simple details.",
    "sticker": "Single sticker composition.",
}


def validate_benchmark(data):
    if data.get("split") != "development":
        raise ValueError("This runner currently accepts development benchmarks only")
    seen = set()
    for row in data["prompts"]:
        if not re.fullmatch(r"dev-[a-z]+-\d{2}", row["id"]) or row["id"] in seen:
            raise ValueError(f"Invalid or duplicate prompt id: {row['id']}")
        seen.add(row["id"])
        if row["mode"] not in MODES or not row["prompt"].strip():
            raise ValueError("Invalid mode or empty prompt")
        if not row.get("criteria") or not all(
            isinstance(c, str) and c.strip() for c in row["criteria"]
        ):
            raise ValueError("Every prompt needs concrete semantic criteria")
    if not seen:
        raise ValueError("Benchmark has no prompts")
    return data


def render_prompt(row, condition):
    if condition == "raw":
        return row["prompt"]
    if condition == "brief":
        return row["prompt"] + " " + STYLE + " " + MODES[row["mode"]]
    raise ValueError(f"Unknown prompt condition: {condition}")


def create_plan(
    root, output, model, conditions, seeds, limit=None, resolution=512, benchmark_path=None
):
    benchmark = validate_benchmark(
        read_json(benchmark_path or root / "benchmarks/development.json")
    )
    models = read_json(root / "configs/models.json")
    if model not in models:
        raise ValueError(f"Unknown model: {model}")
    if resolution < 256 or resolution > 2048 or resolution % 64:
        raise ValueError("Resolution must be a multiple of 64 between 256 and 2048")
    if not seeds or len(set(seeds)) != len(seeds) or any(s < 0 or s >= 2**32 for s in seeds):
        raise ValueError("Use unique integer seeds in [0, 2^32)")
    if not conditions or len(set(conditions)) != len(conditions):
        raise ValueError("Use one or more unique prompt conditions")
    if limit is not None and limit < 1:
        raise ValueError("Limit must be positive")
    jobs = []
    for row in benchmark["prompts"][:limit]:
        for condition in conditions:
            text = render_prompt(row, condition)
            for seed in seeds:
                job = {
                    "prompt_id": row["id"],
                    "category": row["category"],
                    "mode": row["mode"],
                    "source_prompt": row["prompt"],
                    "criteria": row["criteria"],
                    "prompt": text,
                    "condition": condition,
                    "seed": seed,
                    "resolution": resolution,
                    "model": models[model],
                    "brief_version": BRIEF_VERSION,
                }
                job["id"] = digest(job)[:20]
                jobs.append(job)
    plan = {
        "schema_version": 1,
        "created_at": now(),
        "model_key": model,
        "model": models[model],
        "benchmark_hash": digest(benchmark),
        "brief_version": BRIEF_VERSION,
        "jobs": jobs,
        "job_count": len(jobs),
        "status": "planned_not_generated",
        "comparison_note": "Same sample count; also report elapsed time/cost. Equal seeds do not imply equal images across models.",
    }
    plan["experiment_hash"] = digest({k: v for k, v in plan.items() if k != "created_at"})
    if output.exists():
        existing = read_json(output)
        if existing.get("experiment_hash") != plan["experiment_hash"]:
            raise ValueError(
                "A different experiment already exists here; choose another output path"
            )
        return existing
    write_json(output, plan)
    return plan
