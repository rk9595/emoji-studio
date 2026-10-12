"""Create the exact private input bundle without including credentials or other runs."""

import hashlib
import json
import sys
import tarfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from amd_compare import plan  # noqa: E402


def prepare():
    recipe, pairs, lock = plan(ROOT)
    files = ["configs/amd-comparison.json", recipe["benchmark"],
             "scripts/amd_compare.py", "scripts/checkpoint_review.html",
             "docker/rocm-requirements.txt", "ops/remote_compare.sh"]
    files += [c["path"] for c in recipe["conditions"] if c["path"]]
    output = ROOT / "artifacts/amd-comparison-v1"
    output.mkdir(parents=True, exist_ok=True)
    target = output / "inputs.tar.gz"
    with tarfile.open(target, "w:gz") as archive:
        for filename in files:
            archive.add(ROOT / filename, arcname=filename)
    with target.open("rb") as stream:
        checksum = hashlib.file_digest(stream, "sha256").hexdigest()
    campaign = {"experiment": recipe["experiment"], "input_sha256": checksum,
                "input_bytes": target.stat().st_size, "max_allocations": 2,
                "max_hourly_dollars": 1.99, "worker_deadline_seconds": 3300,
                "independent_expiry_minutes": 65, "spending_reserve_dollars": 3,
                "expires_epoch": int(time.time() + 3 * 86400),
                "expected_images": len(pairs) * len(recipe["conditions"]), **lock}
    (output / "campaign.json").write_text(json.dumps(campaign, indent=2) + "\n")
    (output / "state.json").write_text(json.dumps({"status": "queued", "allocation_attempted": False}, indent=2) + "\n")
    print(json.dumps({"bundle": str(target), **campaign}, indent=2))


if __name__ == "__main__":
    prepare()
