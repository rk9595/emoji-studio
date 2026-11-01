"""Read-only independent absence check for the stopped corrective allocation."""

import json
import os
import time
from pathlib import Path

from amd_training_live import ProviderError, api, command


def main():
    if os.environ.get("GH_REPO") != "rk9595/emoji-studio-ops":
        raise ValueError("Private receipt repository required")
    release = "amd-coverage-20261031b"
    state = json.loads(command(["gh", "release", "download", release,
                                "-p", "training-state.json", "-O", "-"]))
    if (state.get("droplet_id") != 614682073 or state.get("run_id") != "41273277371"
            or state.get("source") != "0a960b92de7457a231ed348153b13b898d114db4"
            or state.get("campaign") != release):
        raise ValueError("Unexpected allocation receipt")
    report = {"allocation_id": 614682073, "original_run_id": "41273277371",
              "reconciliation_run_id": os.environ["GITHUB_RUN_ID"],
              "source": os.environ["GITHUB_SHA"], "independent": True,
              "read_only": True, "checked_epoch": time.time(), "cleanup_confirmed": False}
    try:
        row = api("GET", "/droplets/614682073")["droplet"]
        report["observed"] = {key: row.get(key) for key in ("id", "name", "tags", "created_at", "size_slug", "status")}
    except ProviderError as error:
        if error.code != 404:
            raise
        report.update(cleanup_confirmed=True, exact_resource_http_status=404)
    path = Path("independent-cleanup-reconciliation.json")
    path.write_text(json.dumps(report, indent=2) + "\n")
    command(["gh", "release", "upload", release, str(path)])
    print(json.dumps(report))
    if not report["cleanup_confirmed"]:
        raise RuntimeError("Exact resource still exists; inspect ownership before cleanup")


if __name__ == "__main__":
    main()
