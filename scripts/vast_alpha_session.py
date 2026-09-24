"""Launch or stop a bounded private manual-test session on one Vast GPU."""

import argparse
import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from vast_service_load_test import service_offer_allowed  # noqa: E402
from vast_smoke import IMAGE, credit, destroy, owned_instance, request  # noqa: E402

from emoji_studio.alpha import AccessPolicy  # noqa: E402
from emoji_studio.common import read_json, write_json  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-alpha-session"
CURRENT = ARTIFACT_ROOT / "current.json"
BUDGET = ARTIFACT_ROOT / "budget.json"
MAX_HOURLY_DOLLARS = 0.70
MAX_TOTAL_DOLLARS = 3.0
MAX_ELAPSED_SECONDS = 4 * 60 * 60
LOCAL_PORT = 8000


def build_archive(target):
    users = ROOT / "configs/alpha-users.json"
    AccessPolicy.from_file(users)
    names = [
        "pyproject.toml",
        "uv.lock",
        "src",
        "configs/serving.json",
        "configs/alpha-users.json",
        "runs/lora-quality-pilot/adapters/step-25.safetensors",
        "scripts/remote_environment.py",
        "scripts/remote_alpha_start.sh",
    ]
    with tarfile.open(target, "w:gz") as archive:
        for name in names:
            archive.add(
                ROOT / name,
                arcname=name,
                filter=lambda item: None if "__pycache__" in item.name else item,
            )


def compatible_offers():
    query = {
        "type": "ondemand",
        "allocated_storage": 100,
        "verified": {"eq": True},
        "rentable": {"eq": True},
        "rented": {"eq": False},
        "num_gpus": {"eq": 1},
        "gpu_ram": {"gte": 40000},
        "cpu_ram": {"gte": 64000},
        "compute_cap": {"gte": 800},
        "disk_space": {"gte": 100},
        "direct_port_count": {"gte": 1},
        "cuda_max_good": {"gte": 12.8},
        "dph_total": {"lte": MAX_HOURLY_DOLLARS},
        "inet_down_cost": {"lte": 0.007},
        "inet_up_cost": {"lte": 0.007},
        "reliability": {"gte": 0.98},
        "inet_down": {"gte": 500},
        "limit": 20,
        "order": [["dlperf", "desc"], ["inet_down", "desc"]],
    }
    offers = request("POST", "/v0/bundles/", query)["offers"]
    return [row for row in offers if service_offer_allowed(row, MAX_HOURLY_DOLLARS)]


def ssh_command(state, identity):
    row = owned_instance(state)
    return [
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
        f"UserKnownHostsFile={identity.parent / 'known_hosts'}",
        "-o",
        "ServerAliveInterval=15",
        "-o",
        "ServerAliveCountMax=3",
        "-p",
        str(row["ssh_port"]),
        "root@" + row["ssh_host"],
    ]


def wait_for_ssh(state, identity):
    deadline = min(state["deadline_epoch"] - 600, time.time() + 600)
    while time.time() < deadline:
        row = owned_instance(state)
        print("Instance state:", row.get("actual_status"), row.get("status_msg"), flush=True)
        if row.get("actual_status") == "running" and row.get("ssh_host"):
            command = ssh_command(state, identity)
            if subprocess.run([*command, "true"], capture_output=True, timeout=30).returncode == 0:
                return command
        time.sleep(15)
    raise TimeoutError("Instance was not SSH-ready within ten minutes")


def upload(ssh, identity, archive):
    row_host = ssh[-1]
    row_port = ssh[-2]
    sftp = [
        "sftp",
        "-b",
        "-",
        "-i",
        str(identity),
        "-o",
        "BatchMode=yes",
        "-o",
        "IdentitiesOnly=yes",
        "-o",
        "StrictHostKeyChecking=accept-new",
        "-o",
        f"UserKnownHostsFile={identity.parent / 'known_hosts'}",
        "-P",
        row_port,
        row_host,
    ]
    remote_archive = "/root/emoji-alpha.tar.gz"
    local_hash = hashlib.sha256(archive.read_bytes()).hexdigest()
    subprocess.run([*ssh, f"touch {remote_archive}"], check=True, timeout=30)
    for attempt in range(1, 7):
        try:
            result = subprocess.run(
                sftp,
                input=f"reput {archive} emoji-alpha.tar.gz\nbye\n".encode(),
                capture_output=True,
                timeout=300,
            )
            with (identity.parent / "upload.log").open("ab") as log:
                log.write(result.stdout)
                log.write(result.stderr)
            if result.returncode:
                raise subprocess.CalledProcessError(
                    result.returncode, sftp, result.stdout, result.stderr
                )
            remote_hash = subprocess.run(
                [*ssh, f"sha256sum {remote_archive}"],
                capture_output=True,
                text=True,
                check=True,
                timeout=30,
            ).stdout.split()[0]
            if remote_hash == local_hash:
                return
            subprocess.run([*ssh, f"rm -f {remote_archive}; touch {remote_archive}"], check=True)
        except (OSError, subprocess.SubprocessError) as error:
            print("Upload retry:", attempt, type(error).__name__, flush=True)
            if attempt < 6:
                time.sleep(10)
    raise RuntimeError("Project upload failed after six checksum-verified attempts")


def wait_for_remote_health(ssh, timeout=900):
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = subprocess.run(
            [*ssh, "curl -fsS http://127.0.0.1:8000/healthz"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            health = json.loads(result.stdout)
            if health.get("status") == "ok":
                return health
        log = subprocess.run(
            [
                *ssh,
                "tail -c 1200 /workspace/emoji-studio/alpha-bootstrap.log "
                "/workspace/emoji-studio/alpha-service.log 2>/dev/null || true",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if log.stdout:
            print(log.stdout[-1200:], flush=True)
        time.sleep(20)
    raise TimeoutError("Alpha service did not become healthy within fifteen minutes")


def start_guard(state_path, folder):
    command = [
        sys.executable,
        str(ROOT / "scripts/vast_train.py"),
        "guard",
        "--state",
        str(state_path),
    ]
    if shutil.which("caffeinate"):
        command = ["caffeinate", "-i", *command]
    with (folder / "guard.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    return process.pid


def start_tunnel(ssh, folder):
    command = [
        *ssh[:-1],
        "-o",
        "ExitOnForwardFailure=yes",
        "-N",
        "-L",
        f"127.0.0.1:{LOCAL_PORT}:127.0.0.1:8000",
        ssh[-1],
    ]
    with (folder / "tunnel.log").open("w") as log:
        process = subprocess.Popen(command, stdout=log, stderr=log, start_new_session=True)
    time.sleep(2)
    if process.poll() is not None:
        raise RuntimeError("SSH tunnel failed to start")
    return process.pid


def wait_for_local_health(timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{LOCAL_PORT}/healthz", timeout=10
            ) as response:
                return json.load(response)
        except (OSError, urllib.error.URLError, json.JSONDecodeError):
            time.sleep(2)
    raise TimeoutError("Local SSH tunnel did not become healthy within one minute")


def session_budget(current_balance):
    if BUDGET.is_file():
        budget = read_json(BUDGET)
    else:
        previous = sorted(ARTIFACT_ROOT.glob("emoji-alpha-*/preflight.json"))
        if previous:
            first = min(
                (read_json(path) for path in previous), key=lambda row: row["created_epoch"]
            )
            started = first["created_epoch"]
            credit_start = first["credit_before"]
        else:
            started = time.time()
            credit_start = current_balance
        budget = {
            "credit_start": credit_start,
            "started_epoch": started,
            "deadline_epoch": started + MAX_ELAPSED_SECONDS,
            "max_total_dollars": MAX_TOTAL_DOLLARS,
        }
        write_json(BUDGET, budget)
    if time.time() >= budget["deadline_epoch"] - 600:
        raise ValueError("Less than ten minutes remain in the shared alpha-session window")
    if budget["credit_start"] - current_balance >= budget["max_total_dollars"]:
        raise ValueError("The shared $3 alpha-session budget is exhausted")
    return budget


def start():
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if CURRENT.exists():
        raise ValueError("An alpha session record already exists; stop or reconcile it first")
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", LOCAL_PORT))
        except OSError as error:
            raise ValueError(f"Local port {LOCAL_PORT} is already in use") from error
    balance = credit()
    if balance < MAX_TOTAL_DOLLARS:
        raise ValueError("Prepaid credit is below the $3 session cap")
    budget = session_budget(balance)
    if request("GET", "/v1/instances/").get("total_instances", 0):
        raise ValueError("An existing instance is active; refusing another allocation")
    offers = compatible_offers()
    if not offers:
        raise ValueError("No compatible one-GPU offer is currently available")

    offer = offers[0]
    label = "emoji-alpha-" + uuid.uuid4().hex[:10]
    folder = ARTIFACT_ROOT / label
    folder.mkdir()
    identity = folder / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity)],
        check=True,
        timeout=30,
    )
    archive = folder / "project.tar.gz"
    build_archive(archive)
    started = time.time()
    state = {
        "label": label,
        "experiment": "private_alpha_manual_session_v1",
        "offer_id": offer["id"],
        "credit_before": budget["credit_start"],
        "max_total_dollars": budget["max_total_dollars"],
        "deadline_epoch": budget["deadline_epoch"],
        "created_epoch": started,
        "image": IMAGE,
        "offer": {
            key: offer.get(key)
            for key in ["gpu_name", "gpu_ram", "dph_total", "inet_down_cost", "inet_up_cost"]
        },
    }
    write_json(folder / "preflight.json", state)
    allocated = False
    try:
        created = request(
            "PUT",
            f"/v0/asks/{offer['id']}/",
            {
                "image": IMAGE,
                "disk": 100,
                "label": label,
                "runtype": "ssh",
                "target_state": "running",
                "cancel_unavail": True,
                "onstart": "chown root:root /root/.ssh /root/.ssh/authorized_keys\n"
                "chmod 700 /root/.ssh\nchmod 600 /root/.ssh/authorized_keys\n",
            },
        )
        state["instance_id"] = created["new_contract"]
        allocated = True
        state_path = folder / "allocation.json"
        write_json(state_path, state)
        guard_pid = start_guard(state_path, folder)
        request(
            "POST",
            f"/v0/instances/{state['instance_id']}/ssh/",
            {"ssh_key": identity.with_suffix(".pub").read_text().strip()},
        )
        ssh = wait_for_ssh(state, identity)
        upload(ssh, identity, archive)
        subprocess.run(
            [
                *ssh,
                "rm -rf /workspace/emoji-studio && mkdir -p /workspace/emoji-studio && "
                "tar -xzf /root/emoji-alpha.tar.gz -C /workspace/emoji-studio && "
                f"cd /workspace/emoji-studio && bash scripts/remote_alpha_start.sh {offer['dph_total']}",
            ],
            check=True,
            timeout=120,
        )
        health = wait_for_remote_health(ssh)
        tunnel_pid = start_tunnel(ssh, folder)
        health = wait_for_local_health()
        session = {
            "status": "ready",
            "url": f"http://127.0.0.1:{LOCAL_PORT}",
            "instance_id": state["instance_id"],
            "label": label,
            "started_at": datetime.now(UTC).isoformat(),
            "expires_epoch": state["deadline_epoch"],
            "expires_at": datetime.fromtimestamp(state["deadline_epoch"], UTC).isoformat(),
            "max_total_dollars": MAX_TOTAL_DOLLARS,
            "hourly_cost_dollars": offer["dph_total"],
            "gpu_name": offer["gpu_name"],
            "guard_pid": guard_pid,
            "tunnel_pid": tunnel_pid,
            "health": health,
        }
        write_json(folder / "session.json", session)
        write_json(CURRENT, {"folder": folder.name})
        print(json.dumps(session, indent=2))
    except Exception:
        if allocated:
            try:
                result = destroy(state)
                write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
            except Exception as cleanup_error:
                print(
                    f"MANUAL CLEANUP REQUIRED for instance {state['instance_id']}: "
                    f"{type(cleanup_error).__name__}",
                    file=sys.stderr,
                )
        raise


def session_paths():
    current = read_json(CURRENT)
    folder = ARTIFACT_ROOT / current["folder"]
    return folder, read_json(folder / "allocation.json"), read_json(folder / "session.json")


def stop():
    folder, state, session = session_paths()
    try:
        result = destroy(state)
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        result = {"already_absent": True}
    for key in ["tunnel_pid", "guard_pid"]:
        pid = session.get(key)
        if isinstance(pid, int):
            try:
                os.kill(pid, 15)
            except ProcessLookupError:
                pass
    write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
    CURRENT.unlink(missing_ok=True)
    print(json.dumps({"status": "stopped", "instance_id": state["instance_id"]}, indent=2))


def status():
    folder, state, session = session_paths()
    try:
        instance = owned_instance(state)
        active = True
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
        instance = None
        active = False
    print(
        json.dumps(
            {
                **session,
                "active": active,
                "instance_status": instance.get("actual_status") if instance else None,
                "credit_now": credit(),
                "artifact_folder": str(folder),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["start", "status", "stop"])
    args = parser.parse_args()
    try:
        {"start": start, "status": status, "stop": stop}[args.command]()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Error: {type(error).__name__}: {error}\n")
