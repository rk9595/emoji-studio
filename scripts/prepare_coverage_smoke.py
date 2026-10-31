"""Freeze eight existing training assets for a separate two-step AMD diagnostic."""

import json
import shutil
import tempfile
from pathlib import Path

from emoji_studio.common import digest
from emoji_studio.coverage_preflight import canonical, sha256, verify_schedule
from emoji_studio.coverage_training import options, prepare
from emoji_studio.training_data import verify_export

ROOT = Path(__file__).resolve().parents[1]


def immutable_file(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError(f"Existing diagnostic input differs: {path.name}")
    else:
        path.write_bytes(data)


def main():
    recipe = json.loads((ROOT / "configs/lora-coverage-v1.json").read_bytes())
    source = ROOT / recipe["dataset"]
    raw = (source / "manifest.json").read_bytes()
    schedule = json.loads((ROOT / "artifacts/trainers/coverage-v1/schedule.json").read_bytes())
    verify_schedule(schedule, raw, **options(recipe))
    original = verify_export(source)
    ids = schedule["draws"][:8]
    if len(set(ids)) != 8:
        raise ValueError("Diagnostic must contain eight distinct training images")
    rows = {row["asset_id"]: row for row in original["rows"] if row["included"] and row["split"] == "train"}
    destination = ROOT / "data/training/coverage-smoke-v1"
    with tempfile.TemporaryDirectory(dir=destination.parent, prefix=".coverage-smoke-") as temp:
        staging = Path(temp) / "dataset"
        (staging / "train").mkdir(parents=True)
        metadata = []
        for asset in ids:
            row = rows[asset]
            shutil.copyfile(source / row["path"], staging / row["path"])
            metadata.append({"file_name": Path(row["path"]).name, "asset_id": asset,
                             "text": row["caption"]})
        (staging / "train/metadata.jsonl").write_bytes(b"".join(canonical(row) for row in metadata))
        shutil.copyfile(source / "LICENSE.source.txt", staging / "LICENSE.source.txt")
        manifest = {"schema_version": 1, "diagnostic_only": True,
                    "parent_manifest_sha256": sha256(raw), "rows": [rows[asset] for asset in ids],
                    "counts": {"train": 8, "validation": 0},
                    "files": {p.relative_to(staging).as_posix(): sha256(p.read_bytes())
                              for p in sorted(staging.rglob("*")) if p.is_file()}}
        manifest["export_hash"] = digest(manifest)
        (staging / "manifest.json").write_bytes(canonical(manifest))
        if destination.exists():
            if verify_export(destination) != manifest:
                raise ValueError("Existing smoke export differs")
        else:
            staging.rename(destination)
    benchmark_path = ROOT / "benchmarks/coverage-smoke.json"
    benchmark = canonical({"split": "diagnostic", "prompts": [],
                           "purpose": "Finite-loss/checkpoint reload only; no quality evaluation"})
    immutable_file(benchmark_path, benchmark)
    smoke = {**recipe, "experiment": "fluent_coverage_smoke_v1", "max_steps": 2,
             "dataset": "data/training/coverage-smoke-v1", "output": "runs/fluent-coverage-smoke-v1",
             "manifest_sha256": sha256((destination / "manifest.json").read_bytes()),
             "purpose": "Eight-image/two-step finite-loss diagnostic, not a quality candidate",
             "checkpoints_to_evaluate": [], "evaluation": {"benchmark": "benchmarks/coverage-smoke.json",
              "sha256": sha256(benchmark), "maximum_new_images": 1,
              "reload_prompt": "A compact blue backpack, 3D emoji illustration, centered on a white background",
              "seed": 0, "steps": 4, "guidance_scale": 4, "resolution": 512}}
    path = ROOT / "configs/lora-coverage-smoke-v1.json"
    immutable_file(path, canonical(smoke))
    report = prepare(ROOT, path, ROOT / "artifacts/trainers/coverage-smoke-v1")
    (ROOT / "reports/coverage-smoke-preparation.json").write_bytes(canonical(report))
    print(json.dumps({"status": report["status"], "draws": report["draws"],
                      "optimizer_steps": 2, "quality_evaluation": False}))


if __name__ == "__main__":
    main()
