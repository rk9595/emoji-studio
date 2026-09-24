"""Start the bounded smoke workload independently of the SSH transport."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path("/workspace/emoji-studio")


def worker(seconds, experiment):
    with (ROOT / "smoke.log").open("ab", buffering=0) as log:
        result = subprocess.run(
            [
                "timeout",
                "--signal=TERM",
                "--kill-after=30s",
                f"{seconds}s",
                "bash",
                "scripts/remote_smoke.sh",
                experiment,
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
        )
    temporary = ROOT / "smoke.exit.tmp"
    temporary.write_text(str(result.returncode))
    temporary.replace(ROOT / "smoke.exit")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("seconds", type=int)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--experiment", choices=["smoke", "sanity"], default="smoke")
    args = parser.parse_args()
    if args.worker:
        worker(args.seconds, args.experiment)
    else:
        pidfile = ROOT / "smoke.pid"
        if pidfile.exists():
            raise SystemExit("Launch already recorded; refusing a duplicate workload")
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                str(args.seconds),
                "--worker",
                "--experiment",
                args.experiment,
            ],
            cwd=ROOT,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        pidfile.write_text(str(process.pid))
        print(json.dumps({"pid": process.pid, "detached": True}))
