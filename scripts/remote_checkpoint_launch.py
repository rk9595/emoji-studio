"""Start the bounded checkpoint evaluation independently of the SSH transport."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspace/emoji-studio")


def worker(seconds):
    with (ROOT / "checkpoint-bootstrap.log").open("ab", buffering=0) as log:
        result = subprocess.run(
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=30s",
                f"{seconds}s",
                "bash",
                "scripts/remote_checkpoint_eval.sh",
                str(max(900, seconds - 60)),
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
    temporary = ROOT / "checkpoint.exit.tmp"
    temporary.write_text(str(result.returncode))
    temporary.replace(ROOT / "checkpoint.exit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("seconds", type=int)
    parser.add_argument("--worker", action="store_true")
    args = parser.parse_args()
    if not 1020 <= args.seconds <= 3600:
        parser.error("seconds must be between 1020 and 3600")
    if args.worker:
        worker(args.seconds)
    else:
        pidfile = ROOT / "checkpoint.pid"
        if pidfile.exists():
            raise SystemExit("Launch already recorded; refusing a duplicate workload")
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), str(args.seconds), "--worker"],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pidfile.write_text(str(process.pid))
        print(json.dumps({"pid": process.pid, "detached": True}))
