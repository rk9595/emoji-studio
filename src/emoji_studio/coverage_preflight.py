"""Read-only, stdlib-only coverage proposal; never a trainer or spending authority."""

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict, deque
from pathlib import Path

POLICY = "concept-tone-round-robin-sha256-v1"
HASH = re.compile(r"[0-9a-f]{64}\Z")
MAX_MANIFEST_BYTES = 32 * 1024 * 1024


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                       allow_nan=False) + "\n").encode()


def sha256(value):
    return hashlib.sha256(value).hexdigest()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Integer outside prototype bounds")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def checked_rows(raw, expected_hash):
    if not isinstance(expected_hash, str) or not HASH.fullmatch(expected_hash):
        raise ValueError("Expected manifest SHA-256 required")
    if len(raw) > MAX_MANIFEST_BYTES or sha256(raw) != expected_hash:
        raise ValueError("Manifest size or checksum differs")
    manifest = json.loads(raw, object_pairs_hook=unique_keys)
    if not isinstance(manifest, dict):
        raise ValueError("Manifest must be an object")
    rows = manifest.get("rows")
    if not isinstance(rows, list) or not 1 <= len(rows) <= 100_000:
        raise ValueError("Expected a bounded nonempty rows list")
    ids = set()
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Invalid manifest row")
        for field in ("asset_id", "concept", "tone", "family_id", "caption", "caption_status"):
            value = row.get(field)
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise ValueError("Missing or invalid row metadata")
        for field in ("sha256", "source_sha256", "pixel_sha256"):
            if not isinstance(row.get(field), str) or not HASH.fullmatch(row[field]):
                raise ValueError("Missing asset/source/pixel hash")
        if type(row.get("included")) is not bool or row.get("split") not in ("train", "validation"):
            raise ValueError("Invalid inclusion flag or split")
        if row["asset_id"] in ids:
            raise ValueError("Duplicate asset ID")
        ids.add(row["asset_id"])
    return rows


def _ordered_draws(rows, seed, count):
    """Hash-sort each pass independently, then interleave nonempty buckets.

    The versioned hash input avoids interpreter PRNG differences and row-order
    dependence. No probabilities, oversampling or dropped tails are implicit.
    """
    buckets = defaultdict(list)
    for row in rows:
        buckets[(row["concept"], row["tone"])].append(row["asset_id"])
    draws = []
    pass_index = 0
    while len(draws) < count:
        def rank(kind, value):
            return sha256(canonical([POLICY, seed, pass_index, kind, value]))

        keys = sorted(buckets, key=lambda key: (rank("bucket", key), key))
        active = deque(deque(sorted(buckets[key], key=lambda asset: (rank("asset", asset), asset)))
                       for key in keys)
        while active and len(draws) < count:
            bucket = active.popleft()
            draws.append(bucket.popleft())
            if bucket:
                active.append(bucket)
        pass_index += 1
    return draws


def preflight(raw, *, expected_hash, seed, draws, batch_size=1, accumulation=4,
              full_coverage=True, required_buckets=(), required_caption_status=None):
    """Return a proposal and receipt, or blockers with no executable schedule.

    full_coverage=False is an explicit partial diagnostic, never an approved
    subset. A subset must arrive as a separately reviewed, frozen manifest.
    """
    integer(seed, 0, 2**32 - 1)
    integer(draws, 1, 1_000_000)
    integer(batch_size, 1, 1024)
    integer(accumulation, 1, 1024)
    if type(full_coverage) is not bool:
        raise ValueError("Coverage claim must be boolean")
    if required_caption_status is not None and (
        not isinstance(required_caption_status, str) or not required_caption_status.strip()
    ):
        raise ValueError("Invalid required caption status")
    if not isinstance(required_buckets, (list, tuple)) or any(
        not isinstance(bucket, (list, tuple)) or len(bucket) != 2
        or any(not isinstance(value, str) or not value.strip() for value in bucket)
        for bucket in required_buckets
    ):
        raise ValueError("Required buckets must be concept/tone pairs")
    required = sorted(set(tuple(bucket) for bucket in required_buckets))
    rows = checked_rows(raw, expected_hash)
    included = [row for row in rows if row["included"]]
    train = sorted([row for row in included if row["split"] == "train"],
                   key=lambda row: row["asset_id"])
    blockers = []
    leaks = {}
    for field in ("family_id", "sha256", "source_sha256", "pixel_sha256"):
        splits = defaultdict(set)
        for row in included:
            splits[row[field]].add(row["split"])
        leaks[field] = sum(len(values) > 1 for values in splits.values())
    if any(leaks.values()):
        blockers.append("train_validation_leakage")
    if not train:
        blockers.append("empty_training_pool")
    buckets = {(row["concept"], row["tone"]) for row in train}
    missing = [list(bucket) for bucket in required if bucket not in buckets]
    if missing:
        blockers.append("missing_required_buckets")
    if required_caption_status is not None and any(
        row["caption_status"] != required_caption_status for row in train
    ):
        blockers.append("required_caption_status_not_met")
    unit = batch_size * accumulation
    if draws % unit:
        blockers.append("draw_budget_not_whole_optimizer_steps")
    if full_coverage and draws < len(train):
        blockers.append("draw_budget_below_full_coverage")
    result = {
        "schema_version": 1, "status": "blocked" if blockers else "prototype_passed",
        "training_authorized": False, "policy": POLICY, "manifest_sha256": expected_hash,
        "seed": seed, "full_coverage_claim": full_coverage, "eligible_assets": len(train),
        "validation_assets": sum(row["split"] == "validation" for row in included),
        "excluded_assets": len(rows) - len(included), "draw_budget": draws,
        "arithmetic": {"batch_size": batch_size, "gradient_accumulation": accumulation,
                       "world_size": 1, "draws_per_optimizer_step": unit,
                       "complete_optimizer_steps": draws // unit, "leftover_draws": draws % unit,
                       "minimum_full_coverage_steps": (len(train) + unit - 1) // unit,
                       "minimum_aligned_full_coverage_draws": ((len(train) + unit - 1) // unit) * unit},
        "required_buckets": [list(bucket) for bucket in required],
        "missing_required_buckets": missing, "leakage_counts": leaks,
        "required_caption_status": required_caption_status,
        "caption_status_counts": dict(sorted(Counter(row["caption_status"] for row in train).items())),
        "blockers": blockers, "schedule": None, "coverage": None,
        "limitations": ["Metadata checks only; asset bytes and caption truth not verified",
                        "No provenance/license approval or perceptual near-duplicate review",
                        "No annotation, evaluation-freeze, trainer-integration or spend approval"],
    }
    if blockers:
        return result
    sequence = _ordered_draws(train, seed, draws)
    counts = Counter(sequence)
    missed = [list(bucket) for bucket in required
              if not any(counts[row["asset_id"]] for row in train
                         if (row["concept"], row["tone"]) == bucket)]
    if missed:
        result.update(status="blocked", blockers=["required_buckets_not_drawn"])
        result["undrawn_required_buckets"] = missed
        return result
    schedule = {"policy": POLICY, "manifest_sha256": expected_hash, "seed": seed,
                "draws": sequence}
    bucket_totals = Counter()
    for row in train:
        bucket_totals[(row["concept"], row["tone"])] += counts[row["asset_id"]]
    result["schedule"] = schedule
    result["schedule_sha256"] = sha256(canonical(schedule))
    result["coverage"] = {
        "unique_assets": len(counts), "full_passes": draws // len(train),
        "minimum_repeats": min(counts[row["asset_id"]] for row in train),
        "maximum_repeats": max(counts.values()),
        "omitted_assets": [row["asset_id"] for row in train if not counts[row["asset_id"]]],
        "asset_draws": {row["asset_id"]: counts[row["asset_id"]] for row in train},
        "bucket_draws": [{"concept": key[0], "tone": key[1], "draws": value}
                         for key, value in sorted(bucket_totals.items())],
    }
    return result


def verify_schedule(schedule, raw, **options):
    """Reject drift, non-training IDs, repeats or reordering against a fresh proposal.

    Callers supply the original pinned manifest and explicit preflight options;
    never infer authority or the requested budget from an untrusted schedule.
    """
    proposal = preflight(raw, **options)
    if proposal["status"] != "prototype_passed" or canonical(schedule) != canonical(proposal["schedule"]):
        raise ValueError("Schedule differs from the explicit coverage proposal")
    return proposal["schedule_sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--draws", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--accumulation", type=int, default=4)
    parser.add_argument("--partial-diagnostic", action="store_true")
    parser.add_argument("--require-bucket", nargs=2, action="append", default=[],
                        metavar=("CONCEPT", "TONE"))
    parser.add_argument("--required-caption-status")
    args = parser.parse_args()
    try:
        with args.manifest.open("rb") as stream:
            raw = stream.read(MAX_MANIFEST_BYTES + 1)
        report = preflight(raw, expected_hash=args.manifest_sha256, seed=args.seed,
                           draws=args.draws, batch_size=args.batch_size,
                           accumulation=args.accumulation, full_coverage=not args.partial_diagnostic,
                           required_buckets=args.require_bucket,
                           required_caption_status=args.required_caption_status)
    except (ValueError, TypeError, OSError, AttributeError):
        print(json.dumps({"status": "invalid", "training_authorized": False}))
        raise SystemExit(2) from None
    print(canonical(report).decode(), end="")
    raise SystemExit(0 if report["status"] == "prototype_passed" else 1)


if __name__ == "__main__":
    main()
