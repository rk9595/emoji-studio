"""Read-only audit of retained training exposure for observed semantic failures."""

import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def audit(root=ROOT):
    manifest_path = root / "data/training/collection-v2/manifest.json"
    schedule_path = root / "data/training/collection-v2/sampling.json"
    manifest = json.loads(manifest_path.read_text())
    schedule = json.loads(schedule_path.read_text())
    rows = manifest["rows"]
    train = {r["asset_id"]: r for r in rows if r["split"] == "train" and r["included"]}
    draws = Counter(schedule["draws"])
    if set(draws) - set(train):
        raise ValueError("Schedule includes a non-training asset")
    groups = []
    for group in sorted({r["group"] for r in train.values()}):
        assets = [r for r in train.values() if r["group"] == group]
        total = sum(draws[r["asset_id"]] for r in assets)
        groups.append({"group": group, "training_images": len(assets), "draws": total,
                       "distinct_drawn": sum(draws[r["asset_id"]] > 0 for r in assets),
                       "mean_draws_per_training_image": round(total / len(assets), 4)})
    concepts = []
    for concept in ("Crossed fingers", "Folded hands", "High five", "Pinky promise", "Bicycle"):
        matched = [r for r in rows if r["concept"].casefold() == concept.casefold() and r["included"]]
        concepts.append({
            "concept": concept, "train_images": sum(r["split"] == "train" for r in matched),
            "validation_images": sum(r["split"] == "validation" for r in matched),
            "training_draws": sum(draws[r["asset_id"]] for r in matched),
            "captions": sorted({r["caption"] for r in matched}),
        })
    return {
        "status": "completed_metadata_audit", "dataset": "collection-v2",
        "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "sampling_sha256": hashlib.sha256(schedule_path.read_bytes()).hexdigest(),
        "training_images": len(train), "training_draws": sum(draws.values()),
        "distinct_images_drawn": len(draws), "groups": groups, "concepts": concepts,
        "caption_review_status": dict(Counter(r["caption_status"] for r in rows)),
        "limitations": "Metadata and sampling audit only; not a visual annotation or quality score.",
    }


if __name__ == "__main__":
    report = audit()
    destination = ROOT / "reports/collection-coverage-audit.json"
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
