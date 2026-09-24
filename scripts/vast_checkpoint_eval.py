"""Single-use, bounded Vast lifecycle for checkpoint-selection evaluation."""

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import vast_train as smoke_vast  # noqa: E402
from vast_smoke import IMAGE, credit, destroy, owned_instance, request  # noqa: E402

from emoji_studio.common import read_json, write_json  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-checkpoint-selection"
EXPERIMENT = "lora_checkpoint_selection_v1"
MAX_AUTHORIZED_DOLLARS = 1.0
MAX_AUTHORIZED_SECONDS = 3600
MIN_AUTHORIZED_SECONDS = 1800
MAX_AUTHORIZED_HOURLY = 0.70


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def locked_hashes():
    return {
        "project_sha256": sha256(ROOT / "pyproject.toml"),
        "lockfile_sha256": sha256(ROOT / "uv.lock"),
        "config_sha256": sha256(ROOT / "configs/checkpoint-selection.json"),
        "benchmark_sha256": sha256(ROOT / "benchmarks/checkpoint-selection.json"),
        "evaluator_sha256": sha256(ROOT / "scripts/evaluate_checkpoints.py"),
        "environment_sha256": sha256(ROOT / "scripts/remote_environment.py"),
        "remote_shell_sha256": sha256(ROOT / "scripts/remote_checkpoint_eval.sh"),
        "remote_launcher_sha256": sha256(ROOT / "scripts/remote_checkpoint_launch.py"),
    }


def load_authorization(path, clock=time.time):
    path = path.resolve()
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise ValueError(
            "Checkpoint authorization must be inside artifacts/vast-checkpoint-selection"
        )
    authorization = read_json(path)
    required = {
        "authorization_id",
        "authorized",
        "experiment",
        *locked_hashes().keys(),
        "max_total_dollars",
        "max_hourly_dollars",
        "max_elapsed_seconds",
        "expires_epoch",
    }
    if set(authorization) != required:
        raise ValueError("Checkpoint authorization has unexpected or missing fields")
    expected = {"authorized": True, "experiment": EXPERIMENT, **locked_hashes()}
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError("Checkpoint authorization does not match the locked experiment")
    identifier = authorization["authorization_id"]
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isalnum():
        raise ValueError("Authorization ID must be non-empty ASCII letters and digits")
    for name, ceiling in [
        ("max_total_dollars", MAX_AUTHORIZED_DOLLARS),
        ("max_hourly_dollars", MAX_AUTHORIZED_HOURLY),
        ("max_elapsed_seconds", MAX_AUTHORIZED_SECONDS),
    ]:
        value = authorization[name]
        if not smoke_vast.finite_number(value) or value <= 0 or value > ceiling:
            raise ValueError(f"Authorization {name} is outside the hard safety bounds")
    if authorization["max_elapsed_seconds"] < MIN_AUTHORIZED_SECONDS:
        raise ValueError("Authorization is too short for setup, evaluation, and safe teardown")
    if not smoke_vast.finite_number(authorization["expires_epoch"]):
        raise ValueError("Authorization expiry is invalid")
    if clock() >= authorization["expires_epoch"]:
        raise ValueError("Checkpoint authorization has expired")
    for allocation in ARTIFACT_ROOT.glob("*/allocation.json"):
        if read_json(allocation).get("authorization_id") == identifier:
            raise ValueError("Checkpoint authorization was already used")
    return authorization


def verify_locked_inputs():
    config = read_json(ROOT / "configs/checkpoint-selection.json")
    for checkpoint in config["checkpoints"]:
        path = ROOT / checkpoint["path"]
        if not path.is_file() or sha256(path) != checkpoint["sha256"]:
            raise ValueError(f"Checkpoint {checkpoint['step']} differs from its lock")
    return {**locked_hashes(), "adapter_sha256": [row["sha256"] for row in config["checkpoints"]]}


def build_archive(target):
    verify_locked_inputs()
    config = read_json(ROOT / "configs/checkpoint-selection.json")
    names = [
        "pyproject.toml",
        "uv.lock",
        "src",
        "data/curation.json",
        "configs/checkpoint-selection.json",
        "benchmarks/checkpoint-selection.json",
        "scripts/remote_environment.py",
        "scripts/evaluate_checkpoints.py",
        "scripts/remote_checkpoint_eval.sh",
        "scripts/remote_checkpoint_launch.py",
    ] + [row["path"] for row in config["checkpoints"]]
    partial = ROOT / "runs/checkpoint-selection"
    if partial.is_dir():
        names.append("runs/checkpoint-selection")
    with tarfile.open(target, "w:gz") as archive:
        for name in names:
            archive.add(
                ROOT / name,
                arcname=name,
                filter=lambda item: None if "__pycache__" in item.name else item,
            )


def safe_members(archive):
    members = archive.getmembers()
    if any(member.name.startswith("/") or ".." in Path(member.name).parts for member in members):
        raise tarfile.TarError("Unsafe path in checkpoint result archive")
    return members


def extracted_hash(archive, name):
    source = archive.extractfile(name)
    if source is None:
        raise tarfile.TarError(f"Archive member is not a file: {name}")
    return hashlib.file_digest(source, "sha256").hexdigest()


def validate_final_archive(path):
    with tarfile.open(path) as archive:
        names = {member.name for member in safe_members(archive)}
        required = {
            "runs/checkpoint-selection/report.json",
            "checkpoint-eval.log",
            "checkpoint-bootstrap.log",
            "checkpoint.exit",
        }
        if not required.issubset(names):
            raise tarfile.TarError("Final checkpoint result archive is incomplete")
        if archive.extractfile("checkpoint.exit").read().decode().strip() != "0":
            raise tarfile.TarError("Remote checkpoint evaluation did not exit successfully")
        report = json.load(archive.extractfile("runs/checkpoint-selection/report.json"))
        config = read_json(ROOT / "configs/checkpoint-selection.json")
        if report.get("status") != "completed":
            raise tarfile.TarError("Checkpoint report is not complete")
        if report.get("config_sha256") != sha256(ROOT / "configs/checkpoint-selection.json"):
            raise tarfile.TarError("Checkpoint report used another configuration")
        if report.get("benchmark_sha256") != sha256(ROOT / "benchmarks/checkpoint-selection.json"):
            raise tarfile.TarError("Checkpoint report used another benchmark")
        images = report.get("images", [])
        if len(images) != config["expected_images"]:
            raise tarfile.TarError("Checkpoint report has the wrong image count")
        identities = {(row.get("pair_id"), row.get("checkpoint_step")) for row in images}
        if len(identities) != config["expected_images"]:
            raise tarfile.TarError("Checkpoint report has duplicate or missing matched images")
        for row in images:
            member = "runs/checkpoint-selection/" + row["image"]
            if member not in names or extracted_hash(archive, member) != row["image_sha256"]:
                raise tarfile.TarError(f"Checkpoint image checksum differs: {member}")
    return report


def sync_results(ssh, folder, final=False):
    temporary = folder / "results.download"
    command = (
        "cd /workspace/emoji-studio && "
        "files='runs/checkpoint-selection checkpoint-eval.log checkpoint-bootstrap.log'; "
        'if test -f checkpoint.exit; then files="$files checkpoint.exit"; fi; '
        "tar -cz $files"
    )
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                [*ssh, command],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=120,
            )
        if final:
            validate_final_archive(temporary)
        else:
            with tarfile.open(temporary) as archive:
                safe_members(archive)
        temporary.replace(folder / "results.tar.gz")
        print("Durable checkpoint snapshot saved", flush=True)
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError, KeyError) as error:
        print("Checkpoint snapshot retry needed:", type(error).__name__, flush=True)
        return False


def print_remote_progress(ssh):
    try:
        result = subprocess.run(
            [
                *ssh,
                "tail -c 3000 /workspace/emoji-studio/checkpoint-bootstrap.log 2>/dev/null || true",
            ],
            capture_output=True,
            timeout=30,
        )
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    except (OSError, subprocess.SubprocessError) as error:
        print("Checkpoint progress poll skipped:", type(error).__name__, flush=True)


def guard(path):
    state = read_json(path)
    done = path.parent / "cleanup.json"
    while not done.exists():
        try:
            expired = time.time() >= state["deadline_epoch"]
            spent = state["credit_before"] - credit()
            if expired or spent >= state["max_total_dollars"]:
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
            print("Checkpoint guard retry:", type(error).__name__, flush=True)
        time.sleep(20)


def run(authorization_path, offer_id=None):
    authorization = load_authorization(authorization_path)
    verify_locked_inputs()
    balance = credit()
    if balance < authorization["max_total_dollars"]:
        raise ValueError("Prepaid credit is below the authorized experiment cap")
    existing = request("GET", "/v1/instances/")
    if existing.get("total_instances", 0):
        raise ValueError("Existing instances detected; reconcile them before checkpoint evaluation")
    identity, key_is_registered = smoke_vast.find_identity(request("GET", "/v0/users/current/"))
    hourly = authorization["max_hourly_dollars"]
    label = "emoji-checkpoints-" + uuid.uuid4().hex[:10]
    folder = ARTIFACT_ROOT / label
    folder.mkdir(parents=True)
    archive = folder / "project.tar.gz"
    build_archive(archive)
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
        "dph_total": {"lte": hourly},
        "inet_down_cost": {"lte": 0.007},
        "inet_up_cost": {"lte": 0.007},
        "reliability": {"gte": 0.98},
        "inet_down": {"gte": 500},
        "limit": 20,
        "order": [["dlperf", "desc"], ["inet_down", "desc"]],
    }
    if offer_id:
        query["id"] = {"eq": offer_id}
    offers = request("POST", "/v0/bundles/", query)["offers"]
    offers = [offer for offer in offers if smoke_vast.offer_allowed(offer, hourly)]
    if not offers:
        raise ValueError("No compatible one-GPU offer is available within authorization")
    start = time.time()
    state = None
    created = None
    for offer in offers:
        state = {
            "label": label,
            "authorization_id": authorization["authorization_id"],
            "experiment": EXPERIMENT,
            "offer_id": offer["id"],
            "credit_before": balance,
            "max_total_dollars": authorization["max_total_dollars"],
            "deadline_epoch": start + authorization["max_elapsed_seconds"],
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
            break
        except urllib.error.HTTPError as error:
            if error.code not in {400, 404} or offer_id is not None:
                raise
            print("Marketplace offer rejected; trying next compatible offer", flush=True)
        except (OSError, TimeoutError):
            # Allocation APIs can time out after committing. Recover only the one exact label.
            listing = request("GET", "/v1/instances/")
            rows = listing.get("instances", [])
            if isinstance(rows, dict):
                rows = [rows]
            matches = [row for row in rows if row.get("label") == label]
            if len(matches) != 1:
                raise
            created = {"new_contract": matches[0]["id"]}
            print("Recovered committed allocation after provider timeout", flush=True)
            break
    if created is None or state is None:
        raise ValueError("All compatible marketplace offers were unavailable")
    state["instance_id"] = created["new_contract"]
    allocation_path = folder / "allocation.json"
    write_json(allocation_path, state)
    print(json.dumps(state), flush=True)
    ssh = None
    status = 1
    try:
        guard_cmd = [
            sys.executable,
            str(Path(__file__).resolve()),
            "guard",
            "--state",
            str(allocation_path),
        ]
        if shutil.which("caffeinate"):
            guard_cmd = ["caffeinate", "-i", *guard_cmd]
        with (folder / "guard.log").open("w") as log:
            subprocess.Popen(guard_cmd, stdout=log, stderr=log, start_new_session=True)
        if not key_is_registered:
            request(
                "POST",
                f"/v0/instances/{state['instance_id']}/ssh/",
                {"ssh_key": identity.with_suffix(".pub").read_text().strip()},
            )
        startup_deadline = min(start + 900, state["deadline_epoch"] - 1200)
        while time.time() < startup_deadline:
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
                if subprocess.run([*ssh, "true"], capture_output=True, timeout=30).returncode == 0:
                    write_json(
                        folder / "connection.json",
                        {"ssh_host": row["ssh_host"], "ssh_port": row["ssh_port"]},
                    )
                    break
            time.sleep(20)
        else:
            raise TimeoutError("Instance was not SSH-ready within bounded startup window")
        with archive.open("rb") as payload:
            subprocess.run(
                [*ssh, "mkdir -p /workspace/emoji-studio && tar -xz -C /workspace/emoji-studio"],
                stdin=payload,
                check=True,
                timeout=600,
            )
        seconds = int(state["deadline_epoch"] - time.time() - 180)
        if seconds < 1020:
            raise TimeoutError("Insufficient authorized time remains to start evaluation")
        command = (
            "cd /workspace/emoji-studio && "
            f"python3 scripts/remote_checkpoint_launch.py {min(seconds, 3600)}"
        )
        with (folder / "ssh.log").open("w") as log:
            subprocess.run([*ssh, command], stdout=log, stderr=log, check=True, timeout=45)
        while time.time() < state["deadline_epoch"] - 120:
            try:
                row = owned_instance(state)
                if row.get("ssh_host") and row.get("ssh_port"):
                    ssh[-2:] = [str(row["ssh_port"]), "root@" + row["ssh_host"]]
                result = subprocess.run(
                    [
                        *ssh,
                        "test ! -f /workspace/emoji-studio/checkpoint.exit || "
                        "cat /workspace/emoji-studio/checkpoint.exit",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                code = result.stdout.decode("utf-8", errors="replace").strip()
                if result.returncode == 0 and code.lstrip("-").isdigit():
                    if int(code) == 0:
                        if sync_results(ssh, folder, final=True):
                            status = 0
                            break
                    elif sync_results(ssh, folder):
                        status = int(code)
                        break
                else:
                    print_remote_progress(ssh)
                    sync_results(ssh, folder)
            except (OSError, subprocess.SubprocessError) as error:
                print("Checkpoint transport retry:", type(error).__name__, flush=True)
            time.sleep(45)
        print("Remote checkpoint evaluation exit:", status, flush=True)
    finally:
        if ssh:
            if not sync_results(ssh, folder, final=True):
                sync_results(ssh, folder)
        cleaned = False
        for _ in range(5):
            try:
                result = destroy(state)
                write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
                cleaned = True
                break
            except Exception as error:
                print("Checkpoint cleanup retry:", type(error).__name__, flush=True)
                time.sleep(5)
        if not cleaned:
            raise RuntimeError(
                f"MANUAL CLEANUP REQUIRED: instance {state['instance_id']}; guard remains active"
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
            "Destroyed checkpoint instance",
            state["instance_id"],
            "observed credit change",
            balance - after,
            flush=True,
        )
    return status


def resume(state_path):
    """Resume transport for an owned allocation recovered after an ambiguous API timeout."""
    state_path = state_path.resolve()
    if not state_path.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise ValueError("Resume state must be inside checkpoint artifacts")
    state = read_json(state_path)
    if state.get("experiment") != EXPERIMENT or time.time() >= state["deadline_epoch"]:
        raise ValueError("Resume state is for another or expired experiment")
    row = owned_instance(state)
    if row.get("label") != state["label"]:
        raise ValueError("Refusing to resume an unrelated instance")
    identity, key_is_registered = smoke_vast.find_identity(request("GET", "/v0/users/current/"))
    folder = state_path.parent
    archive = folder / "project.tar.gz"
    if not archive.is_file():
        raise ValueError("Recovered allocation has no prepared project archive")
    if not key_is_registered:
        request(
            "POST",
            f"/v0/instances/{state['instance_id']}/ssh/",
            {"ssh_key": identity.with_suffix(".pub").read_text().strip()},
        )
    ssh = None
    status = 1
    try:
        startup_deadline = min(time.time() + 600, state["deadline_epoch"] - 1200)
        while time.time() < startup_deadline:
            row = owned_instance(state)
            print("Recovered instance state:", row.get("actual_status"), flush=True)
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
                if subprocess.run([*ssh, "true"], capture_output=True, timeout=30).returncode == 0:
                    write_json(
                        folder / "connection.json",
                        {"ssh_host": row["ssh_host"], "ssh_port": row["ssh_port"]},
                    )
                    break
            time.sleep(20)
        else:
            raise TimeoutError("Recovered instance was not SSH-ready")
        with archive.open("rb") as payload:
            subprocess.run(
                [*ssh, "mkdir -p /workspace/emoji-studio && tar -xz -C /workspace/emoji-studio"],
                stdin=payload,
                check=True,
                timeout=600,
            )
        seconds = int(state["deadline_epoch"] - time.time() - 180)
        if seconds < 1020:
            raise TimeoutError("Insufficient authorized time remains after allocation recovery")
        command = (
            "cd /workspace/emoji-studio && "
            f"python3 scripts/remote_checkpoint_launch.py {min(seconds, 3600)}"
        )
        with (folder / "ssh.log").open("w") as log:
            subprocess.run([*ssh, command], stdout=log, stderr=log, check=True, timeout=45)
        while time.time() < state["deadline_epoch"] - 120:
            try:
                row = owned_instance(state)
                if row.get("ssh_host") and row.get("ssh_port"):
                    ssh[-2:] = [str(row["ssh_port"]), "root@" + row["ssh_host"]]
                result = subprocess.run(
                    [
                        *ssh,
                        "test ! -f /workspace/emoji-studio/checkpoint.exit || "
                        "cat /workspace/emoji-studio/checkpoint.exit",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                code = result.stdout.decode("utf-8", errors="replace").strip()
                if result.returncode == 0 and code.lstrip("-").isdigit():
                    if int(code) == 0:
                        if sync_results(ssh, folder, final=True):
                            status = 0
                            break
                    elif sync_results(ssh, folder):
                        status = int(code)
                        break
                else:
                    print_remote_progress(ssh)
                    sync_results(ssh, folder)
            except (OSError, subprocess.SubprocessError) as error:
                print("Recovered checkpoint transport retry:", type(error).__name__, flush=True)
            time.sleep(45)
        print("Recovered checkpoint evaluation exit:", status, flush=True)
    finally:
        if ssh:
            if not sync_results(ssh, folder, final=True):
                sync_results(ssh, folder)
        cleaned = False
        for _ in range(5):
            try:
                result = destroy(state)
                write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
                cleaned = True
                break
            except Exception as error:
                print("Recovered checkpoint cleanup retry:", type(error).__name__, flush=True)
                time.sleep(5)
        if not cleaned:
            raise RuntimeError(
                f"MANUAL CLEANUP REQUIRED: instance {state['instance_id']}; guard remains active"
            )
        time.sleep(5)
        after = credit()
        write_json(
            folder / "cost.json",
            {
                "credit_before": state["credit_before"],
                "credit_after": after,
                "observed_credit_change": state["credit_before"] - after,
                "elapsed_seconds": time.time() - state["created_epoch"],
                "billing_may_lag": True,
                "recovered_after_allocation_timeout": True,
            },
        )
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "resume", "guard", "check-authorization"])
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--offer", type=int)
    parser.add_argument("--state", type=Path)
    args = parser.parse_args()
    if args.command == "guard":
        if args.state is None:
            parser.error("guard requires --state")
        guard(args.state)
    elif args.command == "check-authorization":
        if args.authorization is None:
            parser.error("check-authorization requires --authorization")
        print(json.dumps(load_authorization(args.authorization), indent=2))
    elif args.command == "resume":
        if args.state is None:
            parser.error("resume requires --state")
        sys.exit(resume(args.state))
    else:
        if args.authorization is None:
            parser.error("run requires --authorization")
        sys.exit(run(args.authorization, args.offer))
