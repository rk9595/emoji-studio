"""One separately authorized, bounded Vast LoRA training-smoke lifecycle."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tarfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from vast_smoke import IMAGE, credit, destroy, owned_instance, request  # noqa: E402

from emoji_studio.common import read_json, write_json  # noqa: E402
from emoji_studio.training_data import verify_export  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-training"
EXPERIMENT = "lora_two_step_save_reload_smoke"
EXPORT_HASH = "0eaf81532ebbc8d382d5f709df179f00652914a097001a61ffaa629fe1739581"
TRAINER_HASH = "de02782d47ce4535eb9efad49bd90de1ddf9bebcd4313d344d3b1bbb5d536c53"
TRAINER_REVISION = "d035dcd7cc7c88e0a154609b62887d50bba9fdc2"
MAX_AUTHORIZED_DOLLARS = 5.0
MAX_AUTHORIZED_SECONDS = 7200
MAX_AUTHORIZED_HOURLY = 0.70


def finite_number(value):
    return type(value) in {int, float} and math.isfinite(value)


def load_authorization(path, clock=time.time):
    path = path.resolve()
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise ValueError("Training authorization must be inside artifacts/vast-training")
    authorization = read_json(path)
    required = {
        "authorization_id",
        "authorized",
        "experiment",
        "export_hash",
        "trainer_sha256",
        "max_total_dollars",
        "max_hourly_dollars",
        "max_elapsed_seconds",
        "expires_epoch",
    }
    if set(authorization) != required:
        raise ValueError("Training authorization has unexpected or missing fields")
    if authorization["authorized"] is not True:
        raise ValueError("Training is not authorized")
    if authorization["experiment"] != EXPERIMENT:
        raise ValueError("Authorization is for a different experiment")
    if authorization["export_hash"] != EXPORT_HASH:
        raise ValueError("Authorization is for a different training export")
    if authorization["trainer_sha256"] != TRAINER_HASH:
        raise ValueError("Authorization is for a different trainer")
    identifier = authorization["authorization_id"]
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isalnum():
        raise ValueError("Authorization ID must be non-empty ASCII letters and digits")
    bounds = [
        ("max_total_dollars", MAX_AUTHORIZED_DOLLARS),
        ("max_hourly_dollars", MAX_AUTHORIZED_HOURLY),
        ("max_elapsed_seconds", MAX_AUTHORIZED_SECONDS),
    ]
    for name, ceiling in bounds:
        value = authorization[name]
        if not finite_number(value) or value <= 0 or value > ceiling:
            raise ValueError(f"Authorization {name} is outside the hard safety bounds")
    if not finite_number(authorization["expires_epoch"]):
        raise ValueError("Authorization expiry is invalid")
    if clock() >= authorization["expires_epoch"]:
        raise ValueError("Training authorization has expired")
    for allocation in ARTIFACT_ROOT.glob("*/allocation.json"):
        if read_json(allocation).get("authorization_id") == identifier:
            raise ValueError("Training authorization was already used to allocate an instance")
    return authorization


def offer_allowed(offer, hourly_limit):
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
            and 0 <= offer["dph_total"] <= hourly_limit
            and 0 <= offer["inet_down_cost"] <= 0.007
            and 0 <= offer["inet_up_cost"] <= 0.007
        )
    except (KeyError, TypeError, ValueError):
        return False


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
            print(f"Guard retry: {type(error).__name__}", flush=True)
        time.sleep(20)


def build_archive(target):
    manifest = verify_export(ROOT / "data/training/pilot-v1")
    if manifest["export_hash"] != EXPORT_HASH:
        raise ValueError("Local export differs from the authorized export")
    with tarfile.open(target, "w:gz") as archive:
        for name in [
            "pyproject.toml",
            "uv.lock",
            "src",
            "configs",
            "benchmarks",
            "tests",
            "data/curation.json",
            "data/training/pilot-v1",
            f"artifacts/trainers/{TRAINER_REVISION}",
            "scripts/remote_environment.py",
            "scripts/remote_train.py",
            "scripts/remote_train.sh",
            "scripts/remote_training_launch.py",
            "scripts/verify_lora_adapter.py",
            "scripts/vast_smoke.py",
            "scripts/vast_train.py",
        ]:
            archive.add(
                ROOT / name,
                arcname=name,
                filter=lambda item: None if "__pycache__" in item.name else item,
            )


def sync_results(ssh, folder):
    temporary = folder / "results.download"
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                [
                    *ssh,
                    "tar --ignore-failed-read -cz -C /workspace/emoji-studio "
                    "runs training.log training-bootstrap.log training.exit",
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=180,
            )
        with tarfile.open(temporary) as archive:
            members = archive.getmembers()
            if any(
                member.name.startswith("/") or ".." in Path(member.name).parts for member in members
            ):
                raise tarfile.TarError("Unsafe path in result archive")
            count = sum(member.name.endswith(".safetensors") for member in members)
        temporary.replace(folder / "results.tar.gz")
        print("Durable training snapshot:", count, "adapter/checkpoint files", flush=True)
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError) as error:
        print("Training snapshot retry needed:", type(error).__name__, flush=True)
        return False


def validate_final_archive(path):
    required = {
        "runs/training-smoke-report.json",
        "runs/lora-pilot-smoke/pytorch_lora_weights.safetensors",
        "runs/lora-pilot-smoke/adapter-inference.json",
        "runs/lora-pilot-smoke/adapter-inference.png",
        "training.log",
        "training-bootstrap.log",
        "training.exit",
    }
    with tarfile.open(path) as archive:
        members = archive.getmembers()
        names = {member.name for member in members}
        if any(
            member.name.startswith("/") or ".." in Path(member.name).parts for member in members
        ):
            raise tarfile.TarError("Unsafe path in final result archive")
        if not required.issubset(names):
            raise tarfile.TarError("Final result archive is incomplete")
        report = json.load(archive.extractfile("runs/training-smoke-report.json"))
        inference = json.load(archive.extractfile("runs/lora-pilot-smoke/adapter-inference.json"))
        exit_code = archive.extractfile("training.exit").read().decode().strip()
        adapter = archive.extractfile("runs/lora-pilot-smoke/pytorch_lora_weights.safetensors")
        adapter_hash = hashlib.file_digest(adapter, "sha256").hexdigest()
        image = archive.extractfile("runs/lora-pilot-smoke/adapter-inference.png")
        image_hash = hashlib.file_digest(image, "sha256").hexdigest()
    if report.get("status") != "completed" or exit_code != "0":
        raise tarfile.TarError("Remote training smoke did not complete successfully")
    if adapter_hash != report.get("final_adapter", {}).get("sha256"):
        raise tarfile.TarError("Final adapter checksum differs from its report")
    if adapter_hash != inference.get("adapter_sha256"):
        raise tarfile.TarError("Inference used a different adapter")
    if image_hash != inference.get("image_sha256"):
        raise tarfile.TarError("Inference image checksum differs from its receipt")
    return report


def sync_final_results(ssh, folder):
    temporary = folder / "final-results.download"
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                [
                    *ssh,
                    "tar -cz -C /workspace/emoji-studio "
                    "runs/training-smoke-report.json "
                    "runs/lora-pilot-smoke/pytorch_lora_weights.safetensors "
                    "runs/lora-pilot-smoke/adapter-inference.json "
                    "runs/lora-pilot-smoke/adapter-inference.png "
                    "training.log training-bootstrap.log training.exit",
                ],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=300,
            )
        report = validate_final_archive(temporary)
        temporary.replace(folder / "final-results.tar.gz")
        print(
            "Durable final adapter:",
            report["final_adapter"]["sha256"],
            "inference:",
            report["adapter_inference"]["image_sha256"],
            flush=True,
        )
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError, ValueError, KeyError) as error:
        print("Final training snapshot retry needed:", type(error).__name__, flush=True)
        return False


def print_remote_progress(ssh):
    try:
        result = subprocess.run(
            [
                *ssh,
                "tail -c 3000 /workspace/emoji-studio/training-bootstrap.log; "
                "tail -c 3000 /workspace/emoji-studio/training.log 2>/dev/null || true",
            ],
            capture_output=True,
            timeout=30,
        )
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    except (OSError, subprocess.SubprocessError) as error:
        print("Training progress poll skipped:", type(error).__name__, flush=True)


def find_identity(account):
    identity = Path.home() / ".ssh/id_ed25519"
    registered = False
    for name in ["id_ed25519", "id_rsa"]:
        candidate = Path.home() / ".ssh" / name
        public = candidate.with_suffix(".pub")
        if public.exists() and public.read_text().split()[1] in account.get("ssh_key", ""):
            identity = candidate
            registered = True
            break
    if not identity.exists() or not identity.with_suffix(".pub").exists():
        raise ValueError("No usable local SSH identity found")
    return identity, registered


def run(authorization_path, offer_id=None):
    authorization = load_authorization(authorization_path)
    balance = credit()
    if balance < authorization["max_total_dollars"]:
        raise ValueError("Prepaid credit is below the authorized experiment cap")
    existing = request("GET", "/v1/instances/")
    if existing.get("total_instances", 0):
        raise ValueError("Existing instances detected; reconcile them before training")
    identity, key_is_registered = find_identity(request("GET", "/v0/users/current/"))
    hourly = authorization["max_hourly_dollars"]
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
    offers = [offer for offer in offers if offer_allowed(offer, hourly)]
    if not offers:
        raise ValueError("No compatible one-GPU offer is available within authorization")
    offer = offers[0]
    label = "emoji-training-" + uuid.uuid4().hex[:10]
    folder = ARTIFACT_ROOT / label
    folder.mkdir(parents=True)
    archive = folder / "project.tar.gz"
    build_archive(archive)
    start = time.time()
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
            raise TimeoutError("Instance was not SSH-ready within the bounded startup window")
        with archive.open("rb") as payload:
            subprocess.run(
                [*ssh, "mkdir -p /workspace/emoji-studio && tar -xz -C /workspace/emoji-studio"],
                stdin=payload,
                check=True,
                timeout=180,
            )
        seconds = max(120, int(state["deadline_epoch"] - time.time() - 300))
        command = (
            f"cd /workspace/emoji-studio && python3 scripts/remote_training_launch.py {seconds}"
        )
        with (folder / "ssh.log").open("w") as log:
            subprocess.run([*ssh, command], stdout=log, stderr=log, check=True, timeout=45)
        while time.time() < state["deadline_epoch"] - 180:
            try:
                row = owned_instance(state)
                if row.get("ssh_host") and row.get("ssh_port"):
                    ssh[-2:] = [str(row["ssh_port"]), "root@" + row["ssh_host"]]
                result = subprocess.run(
                    [
                        *ssh,
                        "test ! -f /workspace/emoji-studio/training.exit || "
                        "cat /workspace/emoji-studio/training.exit",
                    ],
                    capture_output=True,
                    timeout=30,
                )
                code = result.stdout.decode("utf-8", errors="replace").strip()
                if result.returncode == 0 and code.lstrip("-").isdigit():
                    if int(code) == 0:
                        if sync_final_results(ssh, folder):
                            status = 0
                            break
                    elif sync_results(ssh, folder):
                        status = int(code)
                        break
                else:
                    print_remote_progress(ssh)
                    sync_results(ssh, folder)
            except (OSError, subprocess.SubprocessError) as error:
                print("Training transport retry:", type(error).__name__, flush=True)
            time.sleep(60)
        print("Remote training-smoke exit:", status, flush=True)
    finally:
        if ssh:
            if not sync_final_results(ssh, folder):
                sync_results(ssh, folder)
        cleaned = False
        for _ in range(5):
            try:
                result = destroy(state)
                write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
                cleaned = True
                break
            except Exception as error:
                print("Training cleanup retry:", type(error).__name__, flush=True)
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
            "Destroyed training instance",
            state["instance_id"],
            "observed credit change",
            balance - after,
            flush=True,
        )
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "guard", "check-authorization"])
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
    else:
        if args.authorization is None:
            parser.error("run requires --authorization")
        sys.exit(run(args.authorization, args.offer))
