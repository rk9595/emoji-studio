"""One approved Vast smoke-test lifecycle; credentials never leave the local client."""

import argparse
import json
import math
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from emoji_studio.common import read_json, write_json  # noqa: E402
from emoji_studio.runner import completed_job, validate_plan  # noqa: E402

API = "https://console.vast.ai/api"
IMAGE = "pytorch/pytorch@sha256:b85566342b86d13a67712e9315d40cdc2dad7f8d86df1aff3831f80835edbcca"
KEY_FILE = Path.home() / ".config/vastai/vast_api_key"


def request(method, path, body=None):
    key = KEY_FILE.read_text().strip()
    req = urllib.request.Request(
        API + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as response:
        data = json.load(response)
    if isinstance(data, dict) and data.get("success") is False:
        message = str(data.get("msg", data.get("error", "unknown error"))).replace(
            key, "[redacted]"
        )
        raise RuntimeError(f"Vast request rejected: {message}")
    return data


def credit():
    user = request("GET", "/v0/users/current/")
    if "credit" not in user:
        raise ValueError("Prepaid credit unavailable; refusing to infer it from balance")
    return float(user["credit"])


def owned_instance(state):
    row = request("GET", f"/v0/instances/{state['instance_id']}/")["instances"]
    if row.get("label") != state["label"]:
        raise ValueError("Instance label differs; refusing to change an unrelated resource")
    return row


def destroy(state):
    try:
        owned_instance(state)
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return {"already_absent": True}
        raise
    return request("DELETE", f"/v0/instances/{state['instance_id']}")


def guard(path):
    state = read_json(path)
    done = path.parent / "cleanup.json"
    while not done.exists():
        try:
            expired = time.time() >= state["deadline_epoch"]
            spent = state["credit_before"] - credit()
            if expired or spent >= 4.0:
                result = destroy(state)
                write_json(
                    path.parent / "guard-result.json",
                    {
                        "reason": "deadline" if expired else "credit_guard",
                        "result": result,
                        "time": time.time(),
                    },
                )
                return
        except Exception as error:
            print(f"Guard retry: {type(error).__name__}", flush=True)
        time.sleep(20)


def print_remote_progress(ssh):
    try:
        result = subprocess.run(
            [*ssh, "tail -c 2000 /workspace/emoji-studio/smoke.log"],
            capture_output=True,
            timeout=30,
        )
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    except (subprocess.TimeoutExpired, OSError) as error:
        print("Progress poll skipped:", type(error).__name__, flush=True)


def sync_results(ssh, folder):
    temporary = folder / "results.download"
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                [*ssh, "tar -cz -C /workspace/emoji-studio runs smoke.log"],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=90,
            )
        with tarfile.open(temporary) as archive:
            count = sum(member.name.endswith(".png") for member in archive.getmembers())
        temporary.replace(folder / "results.tar.gz")
        print("Durable local snapshot:", count, "images", flush=True)
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print("Snapshot retry needed:", type(error).__name__, flush=True)
        return False


def offer_allowed(offer):
    try:
        numeric = [
            "num_gpus",
            "gpu_ram",
            "cpu_ram",
            "compute_cap",
            "dph_total",
            "inet_down_cost",
            "inet_up_cost",
        ]
        if not all(math.isfinite(float(offer[key])) for key in numeric):
            return False
        return (
            offer["gpu_name"] != "RTX 4090"
            and offer["num_gpus"] == 1
            and offer["gpu_ram"] >= 45000
            and offer["cpu_ram"] >= 64000
            and offer["compute_cap"] >= 800
            and 0 <= offer["dph_total"] <= 0.70
            and 0 <= offer["inet_down_cost"] <= 0.007
            and 0 <= offer["inet_up_cost"] <= 0.007
        )
    except (KeyError, TypeError, ValueError):
        return False


def add_run_artifacts(tar, root, name):
    folder = root / "runs" / name
    plan = validate_plan(read_json(folder / "plan.json"))
    tar.add(folder / "plan.json", arcname=f"runs/{name}/plan.json")
    for job in plan["jobs"]:
        if completed_job(folder, job):
            for part, extension in [("images", ".png"), ("records", ".json")]:
                relative = f"runs/{name}/{part}/{job['id']}{extension}"
                tar.add(root / relative, arcname=relative)
    for session in sorted((folder / "sessions").glob("*.json")):
        tar.add(session, arcname=session.relative_to(root).as_posix())


def run(offer_id, experiment="smoke"):
    suffix = {"smoke": "smoke-v2", "sanity": "sanity-1024"}[experiment]
    balance = credit()
    if balance < 5:
        raise ValueError(f"At least $5 prepaid credit required; found ${balance:.2f}")
    existing = request("GET", "/v1/instances/")
    if existing.get("total_instances", 0):
        raise ValueError("Existing instances detected; reconcile them before a new budgeted run")
    account = request("GET", "/v0/users/current/")
    identity = Path.home() / ".ssh/id_ed25519"
    key_is_registered = False
    for name in ["id_ed25519", "id_rsa"]:
        candidate = Path.home() / ".ssh" / name
        public = candidate.with_suffix(".pub")
        if public.exists() and public.read_text().split()[1] in account.get("ssh_key", ""):
            identity = candidate
            key_is_registered = True
            break
    print("Using local SSH identity:", identity.name, "registered:", key_is_registered, flush=True)
    query = {
        "type": "ondemand",
        "allocated_storage": 100,
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"eq": 1},
        "gpu_ram": {"gte": 45000},
        "cpu_ram": {"gte": 64000},
        "compute_cap": {"gte": 800},
        "disk_space": {"gte": 100},
        "direct_port_count": {"gte": 1},
        "cuda_max_good": {"gte": 12.8},
        "dph_total": {"lte": 0.70},
        "inet_down_cost": {"lte": 0.007},
        "inet_up_cost": {"lte": 0.007},
        "reliability": {"gte": 0.98},
        "inet_down": {"gte": 500},
        "limit": 20,
        "order": [["dlperf", "desc"], ["inet_down", "desc"]],
    }
    if offer_id:
        query["id"] = {"eq": offer_id}
    offers = request(
        "POST",
        "/v0/bundles/",
        query,
    )["offers"]
    if not offers:
        raise ValueError("No compatible offer available within approved bounds")
    offers = [offer for offer in offers if offer_allowed(offer)]
    if not offers:
        raise ValueError("No returned offer passed the independent hardware and price checks")
    offer = offers[0]
    offer_id = offer["id"]
    if not offer_allowed(offer):
        raise ValueError("Offer exceeds approved cost or hardware bounds")
    label = "emoji-smoke-" + uuid.uuid4().hex[:10]
    folder = ROOT / "artifacts/vast" / label
    folder.mkdir(parents=True)
    archive = folder / "project.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for name in [
            "pyproject.toml",
            "uv.lock",
            "src",
            "configs",
            "benchmarks",
            "tests",
            "scripts/remote_smoke.sh",
            "scripts/remote_launch.py",
            "scripts/remote_environment.py",
        ]:
            tar.add(
                ROOT / name,
                arcname=name,
                filter=lambda item: None if "__pycache__" in item.name else item,
            )
        for model in ["klein", "sdxl"]:
            add_run_artifacts(tar, ROOT, f"{model}-{suffix}")
    start = time.time()
    budget_path = ROOT / "artifacts/vast/budget.json"
    if not budget_path.exists():
        write_json(budget_path, {"credit_start": balance, "deadline_epoch": start + 7200})
    budget = read_json(budget_path)
    if budget.get("resume_remaining_runtime"):
        used = sum(
            read_json(p)["elapsed_seconds"] for p in (ROOT / "artifacts/vast").glob("*/cost.json")
        )
        budget["deadline_epoch"] = start + min(1800, max(0, 7200 - used))
        budget["resume_remaining_runtime"] = False
        write_json(budget_path, budget)
    if start >= budget["deadline_epoch"] - 600 or budget["credit_start"] - balance >= 4:
        raise ValueError("Shared experiment budget exhausted; no new instance will be allocated")
    state = {
        "label": label,
        "experiment": experiment,
        "offer_id": offer_id,
        "credit_before": budget["credit_start"],
        "deadline_epoch": budget["deadline_epoch"],
        "created_epoch": start,
        "image": IMAGE,
        "offer": {
            key: offer.get(key)
            for key in [
                "gpu_name",
                "gpu_ram",
                "cpu_ram",
                "dph_total",
                "inet_down_cost",
                "inet_up_cost",
                "driver_version",
                "inet_down",
                "dlperf",
                "cpu_cores_effective",
            ]
        },
    }
    write_json(folder / "preflight.json", state)
    # Do not retry creation: a lost response could otherwise allocate a second billable instance.
    created = request(
        "PUT",
        f"/v0/asks/{offer_id}/",
        {
            "image": IMAGE,
            "disk": 100,
            "label": label,
            "runtype": "ssh",
            "target_state": "running",
            "cancel_unavail": True,
            "onstart": "chown root:root /root/.ssh /root/.ssh/authorized_keys\nchmod 700 /root/.ssh\nchmod 600 /root/.ssh/authorized_keys\n",
        },
    )
    state["instance_id"] = created["new_contract"]
    path = folder / "allocation.json"
    write_json(path, state)
    print(json.dumps(state), flush=True)
    ssh = None
    status = 1
    try:
        guard_cmd = [sys.executable, str(Path(__file__).resolve()), "guard", "--state", str(path)]
        if shutil.which("caffeinate"):
            guard_cmd = ["caffeinate", "-i", *guard_cmd]
        with (folder / "guard.log").open("w") as log:
            subprocess.Popen(guard_cmd, stdout=log, stderr=log, start_new_session=True)
        if not key_is_registered:
            request(
                "POST",
                f"/v0/instances/{state['instance_id']}/ssh/",
                {
                    "ssh_key": identity.with_suffix(".pub").read_text().strip(),
                },
            )
        while time.time() < min(start + 1200, state["deadline_epoch"] - 300):
            row = owned_instance(state)
            print("Instance state:", row.get("actual_status"), row.get("status_msg"), flush=True)
            if (
                row.get("actual_status") == "running"
                and row.get("ssh_host")
                and row.get("ssh_port")
            ):
                ssh = [
                    "ssh",
                    "-i",
                    str(identity),
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "IdentitiesOnly=yes",
                    "-o",
                    "ConnectTimeout=20",
                    "-o",
                    "StrictHostKeyChecking=accept-new",
                    "-o",
                    f"UserKnownHostsFile={folder / 'known_hosts'}",
                    "-o",
                    "ServerAliveInterval=15",
                    "-o",
                    "ServerAliveCountMax=3",
                    "-p",
                    str(row["ssh_port"]),
                    "root@" + row["ssh_host"],
                ]
                probe = subprocess.run([*ssh, "true"], capture_output=True, timeout=30)
                if probe.returncode == 0:
                    write_json(
                        folder / "connection.json",
                        {"ssh_host": row["ssh_host"], "ssh_port": row["ssh_port"]},
                    )
                    break
            time.sleep(20)
        else:
            raise TimeoutError("Instance was not SSH-ready within 20 minutes")
        with archive.open("rb") as payload:
            subprocess.run(
                [*ssh, "mkdir -p /workspace/emoji-studio && tar -xz -C /workspace/emoji-studio"],
                stdin=payload,
                check=True,
                timeout=120,
            )
        seconds = max(1, int(state["deadline_epoch"] - time.time() - 300))
        command = f"cd /workspace/emoji-studio && python3 scripts/remote_launch.py {seconds} --experiment {experiment}"
        with (folder / "ssh.log").open("w") as log:
            subprocess.run([*ssh, command], stdout=log, stderr=log, check=True, timeout=45)
        while time.time() < state["deadline_epoch"] - 180:
            try:
                row = owned_instance(state)
                if row.get("ssh_host") and row.get("ssh_port"):
                    ssh[-2:] = [str(row["ssh_port"]), "root@" + row["ssh_host"]]
                print_remote_progress(ssh)
                saved = sync_results(ssh, folder)
                result = subprocess.run(
                    [
                        *ssh,
                        "test ! -f /workspace/emoji-studio/smoke.exit || cat /workspace/emoji-studio/smoke.exit",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                code = result.stdout.decode("utf-8", errors="replace").strip()
                if result.returncode == 0 and code.lstrip("-").isdigit() and saved:
                    status = int(code)
                    break
            except (subprocess.SubprocessError, OSError) as error:
                print("Transport retry:", type(error).__name__, flush=True)
            time.sleep(30)
        print("Remote exit:", status, flush=True)
    finally:
        if ssh:
            sync_results(ssh, folder)
        cleaned = False
        for attempt in range(5):
            try:
                result = destroy(state)
                write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
                cleaned = True
                break
            except Exception as error:
                print("Cleanup retry:", type(error).__name__, flush=True)
                time.sleep(5)
        if not cleaned:
            raise RuntimeError(
                f"MANUAL CLEANUP REQUIRED: instance {state['instance_id']}; guard still active"
            )
        time.sleep(5)
        after = credit()
        write_json(
            folder / "cost.json",
            {
                "credit_before": balance,
                "credit_after": after,
                "observed_credit_change": balance - after,
                "elapsed_seconds": time.time() - start,
                "billing_may_lag": True,
            },
        )
        print(
            "Destroyed instance",
            state["instance_id"],
            "observed credit change",
            balance - after,
            flush=True,
        )
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "guard"])
    parser.add_argument("--offer", type=int)
    parser.add_argument("--state", type=Path)
    parser.add_argument("--experiment", choices=["smoke", "sanity"], default="smoke")
    args = parser.parse_args()
    if args.command == "guard":
        guard(args.state)
    else:
        sys.exit(run(args.offer, args.experiment))
