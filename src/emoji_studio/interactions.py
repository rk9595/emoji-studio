"""Data readiness checks for reviewed interaction examples, independent of GPU access."""

import hashlib
from collections import Counter, defaultdict

from PIL import Image

from .common import digest, read_json

REVIEW_CHECKS = ("gesture_correct", "anatomy_correct", "readable_32px", "caption_correct")
CONTROL_GESTURES = ("raised_hand", "folded_hands", "handshake", "clapping")


def interaction_preflight(root, manifest_path):
    root = root.resolve()
    document = read_json(manifest_path)
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported interaction manifest schema")
    benchmark_path = root / "benchmarks/high-five-v1.json"
    benchmark = read_json(benchmark_path)
    benchmark_sha = hashlib.sha256(benchmark_path.read_bytes()).hexdigest()
    if document.get("benchmark_sha256") != benchmark_sha:
        raise ValueError("Interaction manifest is bound to a different frozen benchmark")
    evaluation_prompts = {" ".join(p["prompt"].lower().split()) for p in benchmark["prompts"]}
    evaluation_hashes = set()
    # Baseline images must never become interaction training targets.
    report_path = root / "runs/high-five-baseline-v1/report.json"
    if report_path.exists():
        evaluation_hashes = {r["image_sha256"] for r in read_json(report_path)["images"]}
    issues, accepted = [], []
    seen_ids, seen_hashes = set(), set()
    group_splits = defaultdict(set)
    groups = defaultdict(set)
    tone_counts = Counter()
    for row in document["rows"]:
        if row.get("decision") != "keep":
            continue
        reasons = []
        identifier = row.get("id", "")
        if not identifier or identifier in seen_ids:
            reasons.append("missing_or_duplicate_id")
        seen_ids.add(identifier)
        split, gesture = row.get("split"), row.get("gesture")
        if split not in ("train", "validation"):
            reasons.append("invalid_split")
        if gesture not in ("high_five", *CONTROL_GESTURES, "style_replay"):
            reasons.append("invalid_gesture")
        lineage = row.get("lineage_group")
        pose = row.get("pose_group")
        if not lineage or not pose:
            reasons.append("missing_pose_or_lineage_group")
        else:
            for key in (f"lineage:{lineage}", f"pose:{pose}"):
                group_splits[key].add(split)
        path = (root / row.get("path", "")).resolve()
        checksum = row.get("sha256")
        if not path.is_relative_to(root) or not path.is_file():
            reasons.append("missing_or_unsafe_image_path")
        else:
            if hashlib.sha256(path.read_bytes()).hexdigest() != checksum:
                reasons.append("image_checksum_failed")
            try:
                with Image.open(path) as image:
                    image.load()
                    if min(image.size) < 512 and row.get("allow_low_resolution") is not True:
                        reasons.append("low_resolution_not_acknowledged")
            except (OSError, ValueError):
                reasons.append("invalid_image")
        if not checksum or checksum in seen_hashes:
            reasons.append("missing_or_duplicate_image_hash")
        seen_hashes.add(checksum)
        if checksum in evaluation_hashes:
            reasons.append("evaluation_image_leakage")
        caption = row.get("caption", "").strip()
        if not caption:
            reasons.append("missing_caption")
        source = row.get("source", {})
        if not all(source.get(k) for k in ("kind", "origin", "creator", "terms", "terms_evidence")):
            reasons.append("incomplete_source_provenance")
        if any(source.get(k) is not True for k in ("training_permitted", "redistribution_permitted")):
            reasons.append("unverified_source_permissions")
        if source.get("kind") not in ("licensed_artwork", "commissioned", "synthetic"):
            reasons.append("invalid_source_kind")
        if source.get("kind") == "synthetic" and not all(
            source.get(k) for k in ("generator", "model_version", "generated_at", "prompt")
        ):
            reasons.append("incomplete_synthetic_provenance")
        for text in (caption, source.get("prompt", "")):
            normalized = " ".join(text.lower().split())
            if any(prompt in normalized for prompt in evaluation_prompts):
                reasons.append("evaluation_prompt_leakage")
        review = row.get("review", {})
        if not review.get("reviewer") or review.get("image_sha256") != checksum:
            reasons.append("missing_or_stale_review")
        if any(review.get(k) is not True for k in REVIEW_CHECKS):
            reasons.append("visual_review_incomplete_or_failed")
        if gesture == "high_five":
            if review.get("palm_contact") is not True or review.get("wrists_separated") is not True:
                reasons.append("interaction_geometry_unverified")
            tones = row.get("tone_pair", [])
            if len(tones) != 2 or any(t not in ("yellow", "light", "medium", "dark") for t in tones):
                reasons.append("invalid_tone_pair")
        if reasons:
            issues.append({"id": identifier, "reasons": sorted(set(reasons))})
        else:
            accepted.append(row)
            if gesture == "high_five":
                groups[split].add(pose)
                for tone in set(row["tone_pair"]):
                    tone_counts[split, tone] += 1
    for group, splits in group_splits.items():
        if len(splits) > 1:
            issues.append({"id": group, "reasons": ["pose_or_lineage_split_leakage"]})
    counts = Counter((r["split"], r["gesture"]) for r in accepted)
    for split, minimum, pose_minimum in (("train", 24, 8), ("validation", 8, 4)):
        if counts[split, "high_five"] < minimum:
            issues.append({"id": split, "reasons": [f"need_{minimum}_reviewed_high_fives"]})
        if len(groups[split]) < pose_minimum:
            issues.append({"id": split, "reasons": [f"need_{pose_minimum}_distinct_poses"]})
        for tone in ("light", "medium", "dark"):
            minimum_tones = 4 if split == "train" else 1
            if tone_counts[split, tone] < minimum_tones:
                issues.append({"id": f"{split}:{tone}", "reasons": ["insufficient_tone_coverage"]})
    for gesture in CONTROL_GESTURES:
        if counts["train", gesture] < 1:
            issues.append({"id": gesture, "reasons": ["missing_reviewed_training_control"]})
    return {
        "schema_version": 1, "manifest_hash": digest(document),
        "benchmark_sha256": benchmark_sha, "data_ready": not issues,
        "training_authorized": False,
        "accepted_counts": {f"{s}/{g}": n for (s, g), n in sorted(counts.items())},
        "candidate_count": len(document["rows"]), "blocking_issues": issues,
        "note": "Checks validate recorded review and lineage, not visual truth. Human review remains necessary.",
    }
