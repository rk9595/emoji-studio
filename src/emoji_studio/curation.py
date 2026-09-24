"""Explicit review gates before source references can become training data."""

import hashlib
from collections import Counter

from PIL import Image

from .common import digest, now, read_json, write_json


def create_curation(root, output):
    references = read_json(root / "data/references.json")
    if output.exists():
        raise ValueError("Curation already exists; refusing to overwrite review decisions")
    document = {
        "schema_version": 1,
        "created_at": now(),
        "reference_manifest_hash": digest(references),
        "rows": [
            {
                "asset_id": row["id"],
                "sha256": row["sha256"],
                "concept": row["concept"],
                "decision": "pending",
                "caption": row["caption"],
                "caption_reviewed": False,
                "reviewer": "",
                "split": "unassigned",
                "allow_low_resolution": False,
            }
            for row in references
        ],
    }
    write_json(output, document)
    return {"path": str(output), "pending": len(references), "training_ready": False}


def training_preflight(root, curation_path, config_path):
    references = read_json(root / "data/references.json")
    config = read_json(config_path)
    document = read_json(curation_path)
    if document.get("schema_version") != 1:
        raise ValueError("Unsupported curation schema")
    if document.get("reference_manifest_hash") != digest(references):
        raise ValueError("Curation belongs to a different reference manifest")
    source = {row["id"]: row for row in references}
    seen, families, image_splits = set(), {}, {}
    issues, accepted = [], []
    for row in document["rows"]:
        asset_id = row["asset_id"]
        if asset_id not in source or asset_id in seen:
            raise ValueError("Unknown or duplicate asset in curation")
        seen.add(asset_id)
        original = source[asset_id]
        if row["sha256"] != original["sha256"]:
            raise ValueError("Curation checksum differs from source manifest")
        decision = row.get("decision")
        if decision == "exclude":
            continue
        errors = []
        if decision != "keep":
            errors.append("review_pending")
        if row.get("caption_reviewed") is not True:
            errors.append("caption_not_reviewed")
        if not isinstance(row.get("caption"), str) or not row["caption"].strip():
            errors.append("caption_missing")
        if not isinstance(row.get("reviewer"), str) or not row["reviewer"].strip():
            errors.append("reviewer_missing")
        split = row.get("split")
        if split not in {"train", "validation", "test"}:
            errors.append("split_unassigned")
        if original.get("license") not in config["allowed_source_licenses"]:
            errors.append("license_not_allowed")
        path = (root / original["path"]).resolve()
        if not path.is_relative_to(root.resolve()):
            raise ValueError("Source path escapes the project")
        if (
            not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest() != original["sha256"]
        ):
            errors.append("source_checksum_failed")
        else:
            with Image.open(path) as image:
                image.load()
                if (
                    min(image.size) < config["resolution"]
                    and row.get("allow_low_resolution") is not True
                ):
                    errors.append("low_resolution_not_acknowledged")
        if decision == "keep" and split in {"train", "validation", "test"}:
            family = original["concept_family"]
            if family in families and families[family] != split:
                errors.append("concept_family_leakage")
            families[family] = split
            sha = original["sha256"]
            if sha in image_splits and image_splits[sha] != split:
                errors.append("duplicate_image_leakage")
            image_splits[sha] = split
        if errors:
            issues.append({"asset_id": asset_id, "concept": original["concept"], "reasons": errors})
        else:
            accepted.append({**original, "caption": row["caption"].strip(), "split": split})
    if seen != set(source):
        issues.append({"reasons": ["reference_decisions_missing"]})
    audit = read_json(root / "data/asset-audit.json")
    notice = (root / audit["license_path"]).resolve()
    if (
        not notice.is_relative_to(root.resolve())
        or not notice.is_file()
        or not notice.read_text().strip()
    ):
        issues.append({"reasons": ["source_license_notice_missing"]})
    counts = Counter(row["split"] for row in accepted)
    for split, minimum in config["minimum_split_counts"].items():
        if counts[split] < minimum:
            issues.append(
                {"reasons": [f"insufficient_{split}"], "required": minimum, "found": counts[split]}
            )
    return {
        "checked_at": now(),
        "data_ready": not issues,
        "training_authorized": False,
        "curation_hash": digest(document),
        "reference_manifest_hash": digest(references),
        "accepted_counts": dict(counts),
        "blocking_issues": issues,
        "note": "Data readiness is not permission to rent GPUs or launch training. Low-resolution acceptance does not add image detail.",
    }
