import json
from pathlib import Path

from .benchmark import validate_benchmark
from .common import digest, read_json
from .runner import completed_job, validate_plan


def build_report(root):
    references = (
        read_json(root / "data/references.json") if (root / "data/references.json").exists() else []
    )
    audit = (
        read_json(root / "data/asset-audit.json")
        if (root / "data/asset-audit.json").exists()
        else {}
    )
    benchmark = validate_benchmark(read_json(root / "benchmarks/development.json"))
    curation_path = root / "data/curation.json"
    curation = read_json(curation_path) if curation_path.exists() else None
    if curation and curation.get("reference_manifest_hash") != digest(references):
        curation = None
    runs = []
    for path in sorted((root / "runs").glob("*/plan.json")):
        plan = validate_plan(read_json(path))
        rows = []
        for job in plan["jobs"]:
            record_path = path.parent / "records" / f"{job['id']}.json"
            row = {"id": job["id"], "job": job, "status": "planned"}
            if record_path.exists():
                row.update(read_json(record_path))
                if row["status"] == "completed":
                    if completed_job(path.parent, job):
                        row["image"] = (
                            (path.parent / "images" / f"{job['id']}.png")
                            .relative_to(root)
                            .as_posix()
                        )
                    else:
                        row["status"] = "invalid_artifact"
                        row.pop("image", None)
            rows.append(row)
        runs.append(
            {
                "name": path.parent.name,
                "model": plan["model_key"],
                "experiment_hash": plan["experiment_hash"],
                "review": read_json(path.parent / "review.json")
                if (path.parent / "review.json").exists()
                else None,
                "rows": rows,
            }
        )
    runs.sort(
        key=lambda run: (
            bool(run["review"] and run["review"].get("valid_for_quality_comparison") is False),
            run["name"],
        )
    )
    payload = json.dumps(
        {
            "references": references,
            "audit": audit,
            "benchmark": benchmark,
            "runs": runs,
            "curation": curation,
        },
        ensure_ascii=True,
    ).replace("<", "\\u003c")
    template = (Path(__file__).parent / "workbench.html").read_text()
    output = root / "index.html"
    output.write_text(template.replace("__WORKBENCH_DATA__", payload))
    return {
        "path": str(output),
        "references": len(references),
        "prompts": len(benchmark["prompts"]),
        "runs": len(runs),
        "completed_images": sum(r["status"] == "completed" for run in runs for r in run["rows"]),
    }
