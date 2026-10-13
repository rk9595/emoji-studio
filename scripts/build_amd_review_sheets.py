"""Make verified, label-blinded contact sheets for an explicitly AI-authored review.

Keep sheets/map.json hidden until observations.json has been saved. These are
diagnostic montages, not generated or modified benchmark outputs.
"""

import argparse
import json
import random
from collections import Counter
from pathlib import Path

from amd_compare import ROOT, plan, save, sha256, verify
from PIL import Image, ImageDraw


def build(output):
    config, pairs, lock = plan()
    report = verify(output, config, pairs, lock)
    rows = {(row["pair_id"], row["condition"]): row for row in report["images"]}
    destination = output / "sheets"
    destination.mkdir(exist_ok=True)
    rng = random.Random("ai-sheets-v1:" + lock["config_sha256"])
    mapping = {}
    for pair in pairs:
        conditions = [row["id"] for row in config["conditions"]]
        rng.shuffle(conditions)
        sheet = Image.new("RGB", (1152, 940), "#e8e8e8")
        draw = ImageDraw.Draw(sheet)
        draw.text((12, 8), pair["pair_id"] + " | AI diagnostic; identities hidden", fill="black")
        mapping[pair["pair_id"]] = {}
        for index, condition in enumerate(conditions):
            label = chr(65 + index)
            row = rows[pair["pair_id"], condition]
            x, y = (index % 3) * 384, 36 + (index // 3) * 452
            with Image.open(output / row["image"]) as source:
                source = source.convert("RGB")
                sheet.paste(source.resize((384, 384), Image.Resampling.LANCZOS), (x, y))
                sheet.paste(source.resize((32, 32), Image.Resampling.LANCZOS), (x + 324, y + 396))
            draw.text((x + 12, y + 396), label + " | 32px thumbnail at right", fill="black")
            mapping[pair["pair_id"]][label] = {
                "condition": condition, "image_sha256": row["sha256"],
            }
        sheet.save(destination / (pair["pair_id"] + ".png"))
    save(destination / "map.json", {
        **lock, "source_report_sha256": sha256(output / "report.json"), "pairs": mapping,
    })
    return {"sheets": len(mapping), "directory": str(destination)}


def summarize(output, observations_path):
    config, pairs, lock = plan()
    report = verify(output, config, pairs, lock)
    mapping = json.loads((output / "sheets/map.json").read_text())
    observations = json.loads(observations_path.read_text())
    if mapping["source_report_sha256"] != sha256(output / "report.json"):
        raise ValueError("Contact sheet source report differs")
    if any(mapping.get(key) != value for key, value in lock.items()):
        raise ValueError("Contact sheet recipe differs")
    expected_pairs = {pair["pair_id"] for pair in pairs}
    if (set(mapping["pairs"]) != expected_pairs
            or set(observations["observations"]) != expected_pairs
            or observations["label_order"] != "ABCDEF"):
        raise ValueError("Incomplete or mismatched observations")
    conditions = {row["id"] for row in config["conditions"]}
    counts = {condition: Counter() for condition in conditions}
    rows = {(row["pair_id"], row["condition"]): row for row in report["images"]}
    for pair in pairs:
        pair_id = pair["pair_id"]
        labels = mapping["pairs"][pair_id]
        scores = observations["observations"][pair_id]["scores"]
        if (set(labels) != set("ABCDEF")
                or {item["condition"] for item in labels.values()} != conditions
                or len(scores) != 6
                or any(type(score) is not int or score not in (0, 1, 2) for score in scores)):
            raise ValueError("Invalid labels or scores")
        for label, score in zip("ABCDEF", scores, strict=True):
            item = labels[label]
            if item["image_sha256"] != rows[pair_id, item["condition"]]["sha256"]:
                raise ValueError("Contact sheet image mapping differs")
            counts[item["condition"]][score] += 1
    return {
        "reviewer": observations["reviewer"], "method": observations["method"],
        "scoring": observations["scoring"], **lock,
        "source_report_sha256": mapping["source_report_sha256"],
        "observations_sha256": sha256(observations_path),
        "map_sha256": sha256(output / "sheets/map.json"),
        "verified_images": len(report["images"]),
        "conditions": {condition: {
            "major_failure": counts[condition][0], "partial_or_uncertain": counts[condition][1],
            "major_details_met": counts[condition][2],
        } for condition in sorted(conditions)},
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "runs/amd-comparison-v1")
    parser.add_argument("--observations", type=Path)
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    result = (summarize(args.output.resolve(), args.observations)
              if args.observations else build(args.output.resolve()))
    if args.summary_output:
        save(args.summary_output, result)
    print(json.dumps(result, indent=2))
