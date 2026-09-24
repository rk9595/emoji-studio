"""Build a blinded, static pairwise checkpoint review from verified evaluation outputs."""

import argparse
import hashlib
import json
import shutil
from itertools import combinations
from pathlib import Path

from emoji_studio.common import digest, read_json, write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "runs/checkpoint-selection"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output=OUTPUT):
    report = read_json(output / "report.json")
    if report.get("status") != "completed":
        raise ValueError("Checkpoint evaluation must be complete before building blinded review")
    config = read_json(ROOT / "configs/checkpoint-selection.json")
    if len(report.get("images", [])) != config["expected_images"]:
        raise ValueError("Checkpoint evaluation image count is incomplete")
    assets = output / "review-assets"
    assets.mkdir(parents=True, exist_ok=True)
    by_pair = {}
    for row in report["images"]:
        path = output / row["image"]
        if not path.is_file() or sha256(path) != row["image_sha256"]:
            raise ValueError(f"Invalid evaluation image: {row['image']}")
        by_pair.setdefault(row["pair_id"], []).append(row)

    comparisons = []
    secret = []
    for pair_id, rows in sorted(by_pair.items()):
        if {row["checkpoint_step"] for row in rows} != {25, 50, 75, 100}:
            raise ValueError(f"Pair {pair_id} does not contain all four checkpoints")
        rows = sorted(rows, key=lambda row: row["checkpoint_step"])
        for first, second in combinations(rows, 2):
            comparison_id = digest(
                {
                    "pair_id": pair_id,
                    "steps": [first["checkpoint_step"], second["checkpoint_step"]],
                    "schema": 1,
                }
            )[:20]
            left, right = (first, second)
            if int(comparison_id, 16) % 2:
                left, right = right, left
            public_images = []
            for side, row in [("left", left), ("right", right)]:
                filename = (
                    digest(
                        {
                            "comparison_id": comparison_id,
                            "side": side,
                            "sha256": row["image_sha256"],
                        }
                    )[:24]
                    + ".png"
                )
                destination = assets / filename
                if destination.exists() and sha256(destination) != row["image_sha256"]:
                    raise ValueError("Existing blinded review asset has unexpected content")
                if not destination.exists():
                    shutil.copyfile(output / row["image"], destination)
                public_images.append(f"review-assets/{filename}")
            comparisons.append(
                {
                    "id": comparison_id,
                    "pair_id": pair_id,
                    "prompt": left["prompt"],
                    "category": left["category"],
                    "criteria": left["criteria"],
                    "seed": left["seed"],
                    "left_image": public_images[0],
                    "right_image": public_images[1],
                }
            )
            secret.append(
                {
                    "id": comparison_id,
                    "pair_id": pair_id,
                    "left_step": left["checkpoint_step"],
                    "right_step": right["checkpoint_step"],
                    "left_sha256": left["image_sha256"],
                    "right_sha256": right["image_sha256"],
                }
            )
    expected_comparisons = len(by_pair) * 6
    if len(comparisons) != expected_comparisons:
        raise ValueError("Blinded review comparison count is incorrect")
    review_id = digest(comparisons)
    write_json(
        output / "blind-map.json",
        {
            "schema_version": 1,
            "review_id": review_id,
            "comparisons": secret,
            "review_html_sha256": None,
        },
    )
    payload = json.dumps(
        {"schema_version": 1, "review_id": review_id, "comparisons": comparisons}
    ).replace("<", "\\u003c")
    template = (Path(__file__).parent / "checkpoint_review.html").read_text()
    html = template.replace("__REVIEW_DATA__", payload)
    destination = output / "checkpoint-review.html"
    destination.write_text(html)
    mapping = read_json(output / "blind-map.json")
    mapping["review_html_sha256"] = sha256(destination)
    write_json(output / "blind-map.json", mapping)
    return {"path": str(destination), "pairs": len(by_pair), "comparisons": len(comparisons)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    print(json.dumps(build(args.output.resolve()), indent=2))
