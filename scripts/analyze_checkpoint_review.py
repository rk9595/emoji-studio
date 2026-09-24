"""Decode a completed blinded review and recommend a checkpoint by its locked rule."""

import argparse
import json
from collections import defaultdict
from pathlib import Path

from emoji_studio.common import read_json, write_json

ROOT = Path(__file__).resolve().parents[1]


def analyze(review_path, output_dir=ROOT / "runs/checkpoint-selection"):
    review = read_json(review_path)
    mapping = read_json(output_dir / "blind-map.json")
    if review.get("review_id") != mapping.get("review_id"):
        raise ValueError("Review export belongs to a different blinded comparison")
    decisions = review.get("reviews", {})
    expected = {row["id"] for row in mapping["comparisons"]}
    if set(decisions) != expected:
        missing = len(expected - set(decisions))
        extra = len(set(decisions) - expected)
        raise ValueError(f"Review is incomplete or mismatched: {missing} missing, {extra} extra")
    stats = defaultdict(lambda: {"wins": 0, "losses": 0, "ties": 0, "both_bad": 0, "severe": 0})
    allowed = {"left", "right", "tie", "both_bad"}
    for comparison in mapping["comparisons"]:
        decision = decisions[comparison["id"]]
        preference = decision.get("preference")
        if preference not in allowed:
            raise ValueError(f"Invalid preference for {comparison['id']}")
        left = comparison["left_step"]
        right = comparison["right_step"]
        if preference == "left":
            stats[left]["wins"] += 1
            stats[right]["losses"] += 1
        elif preference == "right":
            stats[right]["wins"] += 1
            stats[left]["losses"] += 1
        elif preference == "tie":
            stats[left]["ties"] += 1
            stats[right]["ties"] += 1
        else:
            stats[left]["both_bad"] += 1
            stats[right]["both_bad"] += 1
        stats[left]["severe"] += int(bool(decision.get("left_severe")))
        stats[right]["severe"] += int(bool(decision.get("right_severe")))
    rows = []
    for step in [25, 50, 75, 100]:
        row = {"step": step, **stats[step]}
        row["preference_score"] = row["wins"] + 0.5 * row["ties"]
        rows.append(row)
    eligible = [row for row in rows if row["severe"] < 2]
    if not eligible:
        recommendation = None
        reason = "Every checkpoint has repeated severe geometry regressions."
    else:
        best_score = max(row["preference_score"] for row in eligible)
        recommendation = min(
            row["step"] for row in eligible if row["preference_score"] == best_score
        )
        reason = (
            "Highest pairwise preference score among checkpoints without repeated severe "
            "geometry regressions; earliest step wins an exact tie."
        )
    result = {
        "schema_version": 1,
        "review_id": review["review_id"],
        "review_export": str(Path(review_path).resolve()),
        "comparisons": len(expected),
        "scores": rows,
        "recommended_step": recommendation,
        "rule": reason,
    }
    write_json(output_dir / "selection.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "runs/checkpoint-selection")
    args = parser.parse_args()
    print(json.dumps(analyze(args.review, args.output.resolve()), indent=2))
