"""Run the candidate trial under an independent remote process timeout."""

import argparse
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def snapshot(stream, root=ROOT):
    relative = "runs/high-five-teacher-pilot-v1"
    output = root / relative
    report_path = output / "report.json"
    # Capture the report first. Its referenced PNGs were atomically published before it.
    payload = report_path.read_bytes() if report_path.exists() else None
    report = json.loads(payload) if payload else {"images": []}
    with tarfile.open(fileobj=stream, mode="w|gz") as archive:
        archive.add(output / "plan.json", arcname=f"{relative}/plan.json")
        for row in report["images"]:
            path = (output / row["image"]).resolve()
            if not path.is_relative_to(output.resolve()) or not path.is_file():
                raise ValueError("Unsafe image path in report")
            archive.add(path, arcname=f"{relative}/{row['image']}")
        if payload:
            info = tarfile.TarInfo(f"{relative}/report.json")
            info.size = len(payload)
            archive.addfile(info, io.BytesIO(payload))
        log = root / "teacher.log"
        if log.exists():
            archive.add(log, arcname="teacher.log")


def worker(seconds):
    code = 1
    try:
        os.environ.update(HF_HOME="/workspace/huggingface", UV_CACHE_DIR="/workspace/uv-cache",
                          HF_HUB_DISABLE_TELEMETRY="1", HF_HUB_DOWNLOAD_TIMEOUT="120",
                          PYTHONUNBUFFERED="1")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "--target", "/workspace/uv-cli",
            "uv==0.10.9",
        ], cwd=ROOT, check=True)
        os.environ["PATH"] = "/workspace/uv-cli/bin" + os.pathsep + os.environ["PATH"]
        subprocess.run([sys.executable, "scripts/remote_environment.py"], cwd=ROOT, check=True)
        code = subprocess.run([
            str(ROOT / ".venv/bin/python"), "scripts/sample_interaction_teacher.py", "run",
            "--max-seconds", str(min(3000, seconds)),
        ], cwd=ROOT).returncode
    finally:
        (ROOT / "teacher.exit").write_text(str(code))
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seconds", type=int)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--snapshot", action="store_true")
    args = parser.parse_args()
    if args.snapshot:
        snapshot(sys.stdout.buffer)
        return 0
    if args.seconds is None or not 900 <= args.seconds <= 3300:
        parser.error("seconds must be 900..3300")
    if args.worker:
        return worker(args.seconds)
    # Exclusive marker prevents a repeated SSH request from starting duplicate work.
    with (ROOT / "teacher.launch.json").open("x") as marker:
        with (ROOT / "teacher.log").open("ab", buffering=0) as log:
            process = subprocess.Popen([
                "timeout", "--signal=TERM", "--kill-after=30s", str(args.seconds),
                sys.executable, str(Path(__file__).resolve()),
                "--seconds", str(args.seconds), "--worker",
            ], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                start_new_session=True)
        json.dump({"pid": process.pid, "max_seconds": args.seconds}, marker)
    print(json.dumps({"pid": process.pid, "detached": True}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
