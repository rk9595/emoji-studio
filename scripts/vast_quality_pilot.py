"""One separately authorized, bounded Vast lifecycle for the 100-step quality pilot."""

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
from emoji_studio.training_data import verify_export  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-quality-pilot"
EXPERIMENT = "lora_100_step_quality_pilot_v1"
EXPORT_HASH = "0eaf81532ebbc8d382d5f709df179f00652914a097001a61ffaa629fe1739581"
TRAINER_HASH = "de02782d47ce4535eb9efad49bd90de1ddf9bebcd4313d344d3b1bbb5d536c53"
TRAINER_REVISION = "d035dcd7cc7c88e0a154609b62887d50bba9fdc2"
CONFIG_HASH = "4da69ff011745d37ec9dccbe48927eb1ef9d71dba7a2525cd060505fab6dcc18"
EVALUATION_HASH = "d469cfc1f2ba996a30afd7c1c70d4d89b71e7b55eabbd8118070954073887864"
MAX_AUTHORIZED_DOLLARS = 2.0
MAX_AUTHORIZED_SECONDS = 3600
MIN_AUTHORIZED_SECONDS = 1800
MAX_AUTHORIZED_HOURLY = 0.70


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_authorization(path, clock=time.time):
    path = path.resolve()
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise ValueError("Quality-pilot authorization must be inside artifacts/vast-quality-pilot")
    authorization = read_json(path)
    required = {
        "authorization_id",
        "authorized",
        "experiment",
        "export_hash",
        "trainer_sha256",
        "config_sha256",
        "evaluation_sha256",
        "max_total_dollars",
        "max_hourly_dollars",
        "max_elapsed_seconds",
        "expires_epoch",
    }
    if set(authorization) != required:
        raise ValueError("Quality-pilot authorization has unexpected or missing fields")
    expected = {
        "authorized": True,
        "experiment": EXPERIMENT,
        "export_hash": EXPORT_HASH,
        "trainer_sha256": TRAINER_HASH,
        "config_sha256": CONFIG_HASH,
        "evaluation_sha256": EVALUATION_HASH,
    }
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError("Quality-pilot authorization does not match the locked experiment")
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
        raise ValueError("Quality-pilot authorization has expired")
    for allocation in ARTIFACT_ROOT.glob("*/allocation.json"):
        if read_json(allocation).get("authorization_id") == identifier:
            raise ValueError("Quality-pilot authorization was already used")
    return authorization


def verify_locked_inputs():
    manifest = verify_export(ROOT / "data/training/pilot-v1")
    if manifest["export_hash"] != EXPORT_HASH:
        raise ValueError("Local training export differs from the locked pilot input")
    checks = {
        ROOT / "configs/lora-quality-pilot.json": CONFIG_HASH,
        ROOT / "benchmarks/lora-quality-eval.json": EVALUATION_HASH,
        ROOT
        / "artifacts/trainers"
        / TRAINER_REVISION
        / "train_dreambooth_lora_flux2_klein.py": TRAINER_HASH,
    }
    for path, expected in checks.items():
        if sha256(path) != expected:
            raise ValueError(f"Locked input hash differs: {path.relative_to(ROOT)}")


def build_archive(target):
    verify_locked_inputs()
    names = [
        "pyproject.toml",
        "uv.lock",
        "src",
        "configs",
        "benchmarks",
        "tests",
        "data/curation.json",
        "data/training/pilot-v1",
        f"artifacts/trainers/{TRAINER_REVISION}",
        "scripts",
    ]
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
        raise tarfile.TarError("Unsafe path in quality-pilot result archive")
    return members


def extracted_hash(archive, name):
    source = archive.extractfile(name)
    if source is None:
        raise tarfile.TarError(f"Archive member is not a file: {name}")
    return hashlib.file_digest(source, "sha256").hexdigest()


def validate_final_archive(path):
    required = {
        "runs/lora-quality-pilot-report.json",
        "runs/lora-quality-pilot/pytorch_lora_weights.safetensors",
        "runs/lora-quality-pilot/evaluation/report.json",
        "quality-pilot.log",
        "quality-bootstrap.log",
        "quality.exit",
    }
    required.update(
        f"runs/lora-quality-pilot/adapters/step-{step}.safetensors" for step in [25, 50, 75, 100]
    )
    with tarfile.open(path) as archive:
        members = safe_members(archive)
        names = {member.name for member in members}
        if not required.issubset(names):
            raise tarfile.TarError("Final quality-pilot archive is incomplete")
        report = json.load(archive.extractfile("runs/lora-quality-pilot-report.json"))
        evaluation = json.load(
            archive.extractfile("runs/lora-quality-pilot/evaluation/report.json")
        )
        exit_code = archive.extractfile("quality.exit").read().decode().strip()
        adapter_name = "runs/lora-quality-pilot/pytorch_lora_weights.safetensors"
        adapter_hash = extracted_hash(archive, adapter_name)
        if report.get("status") != "completed" or evaluation.get("status") != "completed":
            raise tarfile.TarError("Quality pilot or evaluation did not complete")
        if exit_code != "0":
            raise tarfile.TarError("Remote quality-pilot process did not exit successfully")
        if adapter_hash != report.get("final_adapter", {}).get("sha256"):
            raise tarfile.TarError("Final adapter checksum differs from the remote report")
        if adapter_hash != evaluation.get("adapter_sha256"):
            raise tarfile.TarError("Evaluation used a different adapter")
        if report.get("step_100_matches_final_tensors") is not True:
            raise tarfile.TarError("Step-100 and final adapter equivalence was not verified")
        checkpoint_rows = report.get("checkpoint_adapters", [])
        if [row.get("step") for row in checkpoint_rows] != [25, 50, 75, 100]:
            raise tarfile.TarError("Periodic adapter list is incomplete")
        for row in checkpoint_rows:
            name = row.get("path")
            if name not in names or extracted_hash(archive, name) != row.get("sha256"):
                raise tarfile.TarError("Periodic adapter checksum differs")
        images = evaluation.get("images", [])
        if len(images) != 24:
            raise tarfile.TarError("Matched evaluation must contain exactly 24 images")
        pairs = {}
        for row in images:
            name = "runs/lora-quality-pilot/" + row.get("image", "")
            if name not in names or extracted_hash(archive, name) != row.get("image_sha256"):
                raise tarfile.TarError("Evaluation image checksum differs")
            pairs.setdefault(row.get("pair_id"), set()).add(row.get("condition"))
        if len(pairs) != 12 or any(
            conditions != {"base", "adapted"} for conditions in pairs.values()
        ):
            raise tarfile.TarError("Evaluation images are not twelve matched pairs")
    return report


def sync_results(ssh, folder, final=False):
    temporary = folder / ("final-results.download" if final else "results.download")
    command = (
        "cd /workspace/emoji-studio && tar --ignore-failed-read -cz "
        "runs/lora-quality-pilot-report.json "
        "runs/lora-quality-pilot/pytorch_lora_weights.safetensors "
        "runs/lora-quality-pilot/adapters "
        "runs/lora-quality-pilot/evaluation "
        "quality-pilot.log quality-bootstrap.log quality.exit"
    )
    if not final:
        command = command.replace(
            "runs/lora-quality-pilot/evaluation ",
            "runs/lora-quality-pilot/checkpoint-*/pytorch_lora_weights.safetensors "
            "runs/lora-quality-pilot/evaluation ",
        )
    try:
        with temporary.open("wb") as output:
            subprocess.run(
                [*ssh, command],
                stdout=output,
                stderr=subprocess.PIPE,
                check=True,
                timeout=300,
            )
        if final:
            report = validate_final_archive(temporary)
            temporary.replace(folder / "final-results.tar.gz")
            print("Durable quality-pilot adapter:", report["final_adapter"]["sha256"], flush=True)
        else:
            with tarfile.open(temporary) as archive:
                safe_members(archive)
            temporary.replace(folder / "results.tar.gz")
            print("Durable partial quality-pilot snapshot", flush=True)
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError, ValueError, KeyError) as error:
        print("Quality-pilot snapshot retry needed:", type(error).__name__, flush=True)
        return False


def print_remote_progress(ssh):
    try:
        result = subprocess.run(
            [
                *ssh,
                "tail -c 2500 /workspace/emoji-studio/quality-bootstrap.log; "
                "tail -c 3500 /workspace/emoji-studio/quality-pilot.log 2>/dev/null || true",
            ],
            capture_output=True,
            timeout=30,
        )
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    except (OSError, subprocess.SubprocessError) as error:
        print("Quality-pilot progress poll skipped:", type(error).__name__, flush=True)


def run(authorization_path, offer_id=None):
    authorization = load_authorization(authorization_path)
    verify_locked_inputs()
    balance = credit()
    if balance < authorization["max_total_dollars"]:
        raise ValueError("Prepaid credit is below the authorized experiment cap")
    existing = request("GET", "/v1/instances/")
    if existing.get("total_instances", 0):
        raise ValueError("Existing instances detected; reconcile them before the quality pilot")
    identity, key_is_registered = smoke_vast.find_identity(request("GET", "/v0/users/current/"))
    hourly = authorization["max_hourly_dollars"]
    label = "emoji-quality-" + uuid.uuid4().hex[:10]
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
            print("Marketplace offer rejected; trying the next compatible offer", flush=True)
    if created is None or state is None:
        raise ValueError("All compatible marketplace offers were unavailable at allocation time")
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
            raise TimeoutError("Instance was not SSH-ready within the bounded startup window")
        with archive.open("rb") as payload:
            subprocess.run(
                [*ssh, "mkdir -p /workspace/emoji-studio && tar -xz -C /workspace/emoji-studio"],
                stdin=payload,
                check=True,
                timeout=180,
            )
        seconds = int(state["deadline_epoch"] - time.time() - 180)
        if seconds < 1020:
            raise TimeoutError("Insufficient authorized time remains to start the remote pilot")
        command = (
            "cd /workspace/emoji-studio && "
            f"python3 scripts/remote_quality_launch.py {min(seconds, 3600)}"
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
                        "test ! -f /workspace/emoji-studio/quality.exit || "
                        "cat /workspace/emoji-studio/quality.exit",
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
                print("Quality-pilot transport retry:", type(error).__name__, flush=True)
            time.sleep(60)
        print("Remote quality-pilot exit:", status, flush=True)
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
                print("Quality-pilot cleanup retry:", type(error).__name__, flush=True)
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
            "Destroyed quality-pilot instance",
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
        smoke_vast.guard(args.state)
    elif args.command == "check-authorization":
        if args.authorization is None:
            parser.error("check-authorization requires --authorization")
        print(json.dumps(load_authorization(args.authorization), indent=2))
    else:
        if args.authorization is None:
            parser.error("run requires --authorization")
        sys.exit(run(args.authorization, args.offer))
