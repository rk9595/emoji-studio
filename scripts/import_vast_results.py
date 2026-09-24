"""Validate remote artifacts before merging them into the local development runs."""

import argparse
import hashlib
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from emoji_studio.common import read_json  # noqa: E402
from emoji_studio.runner import completed_job, validate_plan  # noqa: E402


def import_results(archive):
    staging = archive.parent / (
        "extracted-" + hashlib.sha256(archive.read_bytes()).hexdigest()[:12]
    )
    if staging.exists():
        raise ValueError("Extraction already exists; inspect it instead of overwriting")
    with tarfile.open(archive) as tar:
        members = tar.getmembers()
        total = 0
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not (member.isdir() or member.isfile()):
                raise ValueError("Unsafe archive member")
            if not path.parts or path.parts[0] not in {"runs", "smoke.log"}:
                raise ValueError("Unexpected archive contents")
            total += member.size
        if total > 100 * 1024**2:
            raise ValueError("Unexpectedly large smoke-test archive")
        tar.extractall(staging, filter="data")
    verified = []
    for name in [
        "klein-smoke",
        "sdxl-smoke",
        "klein-smoke-v2",
        "sdxl-smoke-v2",
        "klein-sanity-1024",
        "sdxl-sanity-1024",
    ]:
        source = staging / "runs" / name
        destination = ROOT / "runs" / name
        if not (source / "plan.json").exists():
            continue
        remote_plan = validate_plan(read_json(source / "plan.json"))
        local_plan = validate_plan(read_json(destination / "plan.json"))
        if remote_plan != local_plan:
            raise ValueError(f"Remote plan differs from local plan: {name}")
        for job in local_plan["jobs"]:
            if completed_job(source, job):
                verified.append((source, destination, job))
            elif (source / "records" / f"{job['id']}.json").exists():
                record = read_json(source / "records" / f"{job['id']}.json")
                if record.get("status") == "completed":
                    raise ValueError("Remote image failed checksum verification")
    for source, destination, job in verified:
        for part, suffix in [("images", ".png"), ("records", ".json")]:
            (destination / part).mkdir(exist_ok=True)
            shutil.copy2(
                source / part / (job["id"] + suffix), destination / part / (job["id"] + suffix)
            )
        for file in ["environment.json", "summary.json", "prompt-preflight.json"]:
            if (source / file).exists():
                shutil.copy2(source / file, destination / file)
        if (source / "sessions").exists():
            shutil.copytree(source / "sessions", destination / "sessions", dirs_exist_ok=True)
    print(
        f"Imported {len(verified)} checksum-verified generated images; raw logs retained in {staging}"
    )
    return len(verified)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    import_results(args.archive.resolve())
