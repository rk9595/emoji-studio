"""Start the bounded service test independently of the SSH transport."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspace/emoji-studio")


def worker(seconds, hourly_cost):
    with (ROOT / "service-bootstrap.log").open("ab", buffering=0) as log:
        result = subprocess.run(
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=30s",
                f"{seconds}s",
                "bash",
                "scripts/remote_service_test.sh",
                str(max(900, seconds - 60)),
                str(hourly_cost),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
    temporary = ROOT / "service.exit.tmp"
    temporary.write_text(str(result.returncode))
    temporary.replace(ROOT / "service.exit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("seconds", type=int)
    parser.add_argument("hourly_cost", type=float)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not 1020 <= args.seconds <= 2700:
        parser.error("seconds must be between 1020 and 2700")
    if not 0 < args.hourly_cost <= 0.70:
        parser.error("hourly cost is outside the authorized range")
    if args.worker:
        worker(args.seconds, args.hourly_cost)
    else:
        pidfile = ROOT / "service.pid"
        if pidfile.exists():
            raise SystemExit("Launch already recorded; refusing a duplicate workload")
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(args.seconds),
                str(args.hourly_cost),
                "--worker",
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pidfile.write_text(str(process.pid))
        print(json.dumps({"pid": process.pid, "detached": True}))
