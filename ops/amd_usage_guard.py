"""Local read-only usage watcher; request cloud cleanup before limits are reached.

This process does not allocate or access AMD credentials. It writes one bound stop
request to the private campaign release. Cloud expiry is independent of the Mac.
"""

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

from codex_supervisor import AppServer, cloud_state

ROOT = Path(__file__).resolve().parents[1]


def near_limit(response, threshold=85):
    buckets = response.get("rateLimitsByLimitId") or {"default": response.get("rateLimits")}
    percentages = []
    for bucket in buckets.values():
        if not bucket:
            continue
        if bucket.get("rateLimitReachedType"):
            return True
        for name in ("primary", "secondary"):
            window = bucket.get(name)
            if window:
                value = window.get("usedPercent")
                if not isinstance(value, (int, float)) or not 0 <= value <= 100:
                    raise ValueError("Invalid quota signal")
                percentages.append(value)
    if not percentages:
        raise ValueError("No usable quota signal")
    return max(percentages) >= threshold


def read_limits(config):
    server = AppServer(config["socket_path"])
    try:
        return server.call("account/rateLimits/read")
    finally:
        server.close()


def request_stop(config, queue, release, reason):
    request = {"campaign": release, "run_id": queue["cloud_run_id"],
               "reason": reason, "requested_epoch": time.time()}
    directory = ROOT / "var/amd-api-live" / release
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "stop-request.json"
    path.write_text(json.dumps(request, indent=2) + "\n")
    # No overwrite; both remote controllers verify the run/campaign identity.
    result = subprocess.run([config["gh"], "release", "upload", release, str(path),
                             "-R", "rk9595/emoji-studio-ops"],
                            capture_output=True, timeout=30)
    if result.returncode:
        # An uncertain acknowledgment may mean the exact request already exists.
        remote = subprocess.run([config["gh"], "release", "download", release,
                                 "-R", "rk9595/emoji-studio-ops", "-p", path.name, "-O", "-"],
                                check=True, capture_output=True, text=True, timeout=30)
        saved = json.loads(remote.stdout)
        if saved.get("campaign") != release or saved.get("run_id") != queue["cloud_run_id"]:
            raise ValueError("Remote stop request identity differs")
    return request


def campaign_binding(queue, release):
    workflows = {"AMD two-image API smoke": ("active_api_attempt", 2400),
                 "AMD coverage training": ("active_training_attempt", 4200)}
    key, duration = workflows.get(queue.get("cloud_run_workflow"), (None, None))
    if (queue.get("cloud_repository") != "rk9595/emoji-studio-ops" or key is None
            or queue.get(key, {}).get("release") != release):
        raise ValueError("Usage watcher must bind the active bounded run")
    return duration


def main(release):
    os.umask(0o077)
    config = json.loads((ROOT / "var/automation/supervisor.json").read_text())
    queue = json.loads((ROOT / "ops/work-queue.json").read_text())
    deadline = time.monotonic() + campaign_binding(queue, release)
    failures = 0
    stopped = False
    receipt = {"run_id": queue["cloud_run_id"], "campaign": release, "threshold_percent": 85}
    receipt_path = ROOT / "var/amd-api-live" / f"usage-guard-{queue['cloud_run_id']}.json"
    while time.monotonic() < deadline:
        try:
            finished = cloud_state(config, queue)["status"] in ("completed", "failed", "expired")
            if finished:
                receipt.update(status="cloud_run_finished", checked_epoch=time.time())
                receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
                return
        except Exception:
            pass  # Still check usage; the remote independent deadline remains active.
        if not stopped:
            try:
                near = near_limit(read_limits(config))
                failures = 0
            except Exception:
                failures += 1
                near = failures >= 2
            if near:
                reason = "usage_signal_unavailable" if failures else "usage_at_or_above_85_percent"
                try:
                    receipt["stop_request"] = request_stop(config, queue, release, reason)
                    stopped = True
                except Exception:
                    receipt["stop_delivery_pending"] = True
        receipt.update(status="cleanup_requested" if stopped else "watching", checked_epoch=time.time())
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        time.sleep(30)
    receipt.update(status="watcher_deadline_reached", checked_epoch=time.time())
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("release")
    main(parser.parse_args().release)
