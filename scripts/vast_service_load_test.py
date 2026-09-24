"""Single-use, bounded Vast lifecycle for the real Emoji Studio service load test."""

import argparse
import hashlib
import json
import math
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

import vast_train as vast_helpers  # noqa: E402
from vast_smoke import IMAGE, credit, destroy, owned_instance, request  # noqa: E402

from emoji_studio.common import read_json, write_json  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-service-load-test"
EXPERIMENT = "single_gpu_service_load_test_v1"
MAX_AUTHORIZED_DOLLARS = 1.0
MAX_AUTHORIZED_SECONDS = 2700
MIN_AUTHORIZED_SECONDS = 1800
MAX_AUTHORIZED_HOURLY = 0.70


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def locked_hashes():
    return {
        "project_sha256": sha256(ROOT / "pyproject.toml"),
        "lockfile_sha256": sha256(ROOT / "uv.lock"),
        "serving_config_sha256": sha256(ROOT / "configs/serving.json"),
        "adapter_sha256": sha256(ROOT / "runs/lora-quality-pilot/adapters/step-25.safetensors"),
        "service_sha256": sha256(ROOT / "src/emoji_studio/service.py"),
        "api_sha256": sha256(ROOT / "src/emoji_studio/api.py"),
        "client_sha256": sha256(ROOT / "src/emoji_studio/client.py"),
        "load_test_sha256": sha256(ROOT / "scripts/load_test_service.py"),
        "remote_test_sha256": sha256(ROOT / "scripts/remote_service_test.py"),
        "remote_shell_sha256": sha256(ROOT / "scripts/remote_service_test.sh"),
        "remote_launcher_sha256": sha256(ROOT / "scripts/remote_service_launch.py"),
        "environment_sha256": sha256(ROOT / "scripts/remote_environment.py"),
    }


def load_authorization(path, clock=time.time):
    path = path.resolve()
    if not path.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise ValueError("Service authorization must be inside its artifact directory")
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
        raise ValueError("Service authorization has unexpected or missing fields")
    expected = {"authorized": True, "experiment": EXPERIMENT, **locked_hashes()}
    if any(authorization.get(key) != value for key, value in expected.items()):
        raise ValueError("Service authorization does not match the locked experiment")
    identifier = authorization["authorization_id"]
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isalnum():
        raise ValueError("Authorization ID must be non-empty ASCII letters and digits")
    for name, ceiling in [
        ("max_total_dollars", MAX_AUTHORIZED_DOLLARS),
        ("max_hourly_dollars", MAX_AUTHORIZED_HOURLY),
        ("max_elapsed_seconds", MAX_AUTHORIZED_SECONDS),
    ]:
        value = authorization[name]
        if not vast_helpers.finite_number(value) or value <= 0 or value > ceiling:
            raise ValueError(f"Authorization {name} is outside the hard safety bounds")
    if authorization["max_elapsed_seconds"] < MIN_AUTHORIZED_SECONDS:
        raise ValueError("Authorization is too short for setup, testing, and safe teardown")
    if not vast_helpers.finite_number(authorization["expires_epoch"]):
        raise ValueError("Authorization expiry is invalid")
    if clock() >= authorization["expires_epoch"]:
        raise ValueError("Service authorization has expired")
    for allocation in ARTIFACT_ROOT.glob("*/allocation.json"):
        if read_json(allocation).get("authorization_id") == identifier:
            raise ValueError("Service authorization was already used")
    return authorization


def verify_locked_inputs():
    config = read_json(ROOT / "configs/serving.json")
    adapter = ROOT / config["adapter_path"]
    if config.get("selected_step") != 25 or sha256(adapter) != config.get("adapter_sha256"):
        raise ValueError("Serving config is not locked to the selected step-25 adapter")
    return locked_hashes()


def service_offer_allowed(offer, hourly_limit):
    try:
        numeric = [
            "num_gpus",
            "gpu_ram",
            "cpu_ram",
            "compute_cap",
            "dph_total",
            "inet_down_cost",
            "inet_up_cost",
            "reliability",
        ]
        if not all(math.isfinite(float(offer[key])) for key in numeric):
            return False
        return (
            offer["gpu_name"] != "RTX 4090"
            and offer["num_gpus"] == 1
            and offer["gpu_ram"] >= 40000
            and offer["cpu_ram"] >= 64000
            and offer["compute_cap"] >= 800
            and offer["reliability"] >= 0.98
            and 0 <= offer["dph_total"] <= hourly_limit
            and 0 <= offer["inet_down_cost"] <= 0.007
            and 0 <= offer["inet_up_cost"] <= 0.007
        )
    except (KeyError, TypeError, ValueError):
        return False


def build_archive(target):
    verify_locked_inputs()
    names = [
        "pyproject.toml",
        "uv.lock",
        "src",
        "configs/serving.json",
        "runs/lora-quality-pilot/adapters/step-25.safetensors",
        "scripts/load_test_service.py",
        "scripts/remote_environment.py",
        "scripts/remote_service_test.py",
        "scripts/remote_service_test.sh",
        "scripts/remote_service_launch.py",
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
        raise tarfile.TarError("Unsafe path in service result archive")
    return members


def validate_final_archive(path):
    required = {
        "runs/service-gpu-test/report.json",
        "runs/service-gpu-test/service.log",
        "runs/service-gpu-test/metrics.prom",
        "runs/service-gpu-test/gpu-samples.json",
        "runs/service-gpu-test/load-test.stdout",
        "runs/service-gpu-test/smoke-1.png",
        "runs/service-gpu-test/smoke-1.webp",
        "runs/service-gpu-test/smoke-2.png",
        "runs/service-gpu-test/smoke-2.webp",
        "service-test.log",
        "service-bootstrap.log",
        "service.exit",
    }
    with tarfile.open(path) as archive:
        names = {member.name for member in safe_members(archive)}
        if not required.issubset(names):
            raise tarfile.TarError("Final service result archive is incomplete")
        if archive.extractfile("service.exit").read().decode().strip() != "0":
            raise tarfile.TarError("Remote service test did not exit successfully")
        report = json.load(archive.extractfile("runs/service-gpu-test/report.json"))
        if report.get("status") != "completed" or not all(report.get("checks", {}).values()):
            raise tarfile.TarError("Service report did not pass every locked check")
        if report.get("serving_config_sha256") != locked_hashes()["serving_config_sha256"]:
            raise tarfile.TarError("Service report used a different serving configuration")
        if report.get("adapter_sha256") != locked_hashes()["adapter_sha256"]:
            raise tarfile.TarError("Service report used a different adapter")
        load = report.get("load_test", {})
        if load.get("requests") != 16 or load.get("concurrency") != 4:
            raise tarfile.TarError("Service report used a different load-test shape")
        if load.get("completed") != 16 or load.get("failed") != 0:
            raise tarfile.TarError("Service load test was not completely successful")
    return report


def sync_results(ssh, folder, final=False):
    temporary = folder / ("final-results.download" if final else "results.download")
    command = (
        "cd /workspace/emoji-studio && tar --ignore-failed-read -cz "
        "runs/service-gpu-test service-test.log service-bootstrap.log service.exit"
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
            print(
                "Durable service result:",
                report["load_test"]["throughput_images_per_minute"],
                "images/minute",
                flush=True,
            )
        else:
            with tarfile.open(temporary) as archive:
                safe_members(archive)
            temporary.replace(folder / "results.tar.gz")
            print("Durable partial service snapshot", flush=True)
        return True
    except (OSError, subprocess.SubprocessError, tarfile.TarError, ValueError, KeyError) as error:
        print("Service snapshot retry needed:", type(error).__name__, flush=True)
        return False


def print_remote_progress(ssh):
    try:
        result = subprocess.run(
            [
                *ssh,
                "tail -c 2500 /workspace/emoji-studio/service-bootstrap.log; "
                "tail -c 3500 /workspace/emoji-studio/service-test.log 2>/dev/null || true",
            ],
            capture_output=True,
            timeout=30,
        )
        print(result.stdout.decode("utf-8", errors="replace"), flush=True)
    except (OSError, subprocess.SubprocessError) as error:
        print("Service progress poll skipped:", type(error).__name__, flush=True)


def run(authorization_path, offer_id=None):
    authorization = load_authorization(authorization_path)
    verify_locked_inputs()
    balance = credit()
    if balance < authorization["max_total_dollars"]:
        raise ValueError("Prepaid credit is below the authorized experiment cap")
    existing = request("GET", "/v1/instances/")
    if existing.get("total_instances", 0):
        raise ValueError("Existing instances detected; reconcile them before service testing")
    hourly = authorization["max_hourly_dollars"]
    label = "emoji-service-" + uuid.uuid4().hex[:10]
    folder = ARTIFACT_ROOT / label
    folder.mkdir(parents=True)
    archive = folder / "project.tar.gz"
    build_archive(archive)
    identity_directory = tempfile.TemporaryDirectory(prefix="emoji-service-ssh-")
    identity = Path(identity_directory.name) / "id_ed25519"
    subprocess.run(
        ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity)],
        check=True,
        timeout=30,
    )
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
        "dph_total": {"lte": hourly},
        "inet_down_cost": {"lte": 0.007},
        "inet_up_cost": {"lte": 0.007},
        "reliability": {"gte": 0.98},
        "inet_down": {"gte": 500},
        "limit": 20,
        "order": [["dlperf", "desc"], ["inet_down", "desc"]],
    }
    offers = request("POST", "/v0/bundles/", query)["offers"]
    offers = [offer for offer in offers if service_offer_allowed(offer, hourly)]
    if offer_id:
        offers = [offer for offer in offers if offer.get("id") == offer_id]
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
        request(
            "POST",
            f"/v0/instances/{state['instance_id']}/ssh/",
            {"ssh_key": identity.with_suffix(".pub").read_text().strip()},
        )
        startup_deadline = min(start + 600, state["deadline_epoch"] - 1200)
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
            time.sleep(15)
        else:
            raise TimeoutError("Instance was not SSH-ready within the bounded startup window")
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
            "ConnectTimeout=20",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={folder / 'known_hosts'}",
            "-o",
            "ServerAliveInterval=15",
            "-o",
            "ServerAliveCountMax=3",
            "-P",
            str(row["ssh_port"]),
            "root@" + row["ssh_host"],
        ]
        remote_archive = "/root/emoji-service-project.tar.gz"
        archive_hash = sha256(archive)
        subprocess.run(
            [*ssh, f"touch {remote_archive}"],
            check=True,
            timeout=30,
        )
        uploaded = False
        for attempt in range(1, 7):
            try:
                batch = f"reput {archive} emoji-service-project.tar.gz\nbye\n"
                transfer = subprocess.run(
                    sftp,
                    input=batch.encode(),
                    capture_output=True,
                    timeout=300,
                )
                with (folder / "upload.log").open("ab") as log:
                    log.write(transfer.stdout)
                    log.write(transfer.stderr)
                if transfer.returncode == 0:
                    remote_hash = subprocess.run(
                        [*ssh, f"sha256sum {remote_archive}"],
                        capture_output=True,
                        text=True,
                        check=True,
                        timeout=30,
                    ).stdout.split()[0]
                    if remote_hash == archive_hash:
                        uploaded = True
                        break
                    subprocess.run(
                        [*ssh, f"rm -f {remote_archive}"],
                        check=True,
                        timeout=30,
                    )
                    print("Service bundle checksum retry:", attempt, flush=True)
                    continue
                raise subprocess.CalledProcessError(transfer.returncode, sftp)
            except (OSError, subprocess.SubprocessError) as error:
                print(
                    "Resumable service bundle upload retry:",
                    attempt,
                    type(error).__name__,
                    flush=True,
                )
                if attempt < 6:
                    time.sleep(15)
        if not uploaded:
            raise RuntimeError("Service bundle upload failed after six resumable attempts")
        subprocess.run(
            [
                *ssh,
                "rm -rf /workspace/emoji-studio && "
                "mkdir -p /workspace/emoji-studio && "
                f"tar -xzf {remote_archive} -C /workspace/emoji-studio",
            ],
            check=True,
            timeout=120,
        )
        seconds = int(state["deadline_epoch"] - time.time() - 180)
        if seconds < 1020:
            raise TimeoutError("Insufficient authorized time remains to start service testing")
        command = (
            "cd /workspace/emoji-studio && "
            f"python3 scripts/remote_service_launch.py {min(seconds, 2700)} "
            f"{state['offer']['dph_total']}"
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
                        "test ! -f /workspace/emoji-studio/service.exit || "
                        "cat /workspace/emoji-studio/service.exit",
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
                print("Service transport retry:", type(error).__name__, flush=True)
            time.sleep(30)
        print("Remote service test exit:", status, flush=True)
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
                print("Service cleanup retry:", type(error).__name__, flush=True)
                time.sleep(5)
        if not cleaned:
            raise RuntimeError(
                f"MANUAL CLEANUP REQUIRED: instance {state['instance_id']}; guard remains active"
            )
        time.sleep(5)
        after = credit()
        remaining = request("GET", "/v1/instances/").get("total_instances")
        write_json(
            folder / "cost.json",
            {
                "credit_before": balance,
                "credit_after": after,
                "observed_credit_change": balance - after,
                "elapsed_seconds": time.time() - start,
                "billing_may_lag": True,
                "independent_remaining_instances": remaining,
            },
        )
        print(
            "Destroyed service instance",
            state["instance_id"],
            "observed credit change",
            balance - after,
            "remaining instances",
            remaining,
            flush=True,
        )
        identity_directory.cleanup()
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
        vast_helpers.guard(args.state)
    elif args.command == "check-authorization":
        if args.authorization is None:
            parser.error("check-authorization requires --authorization")
        print(json.dumps(load_authorization(args.authorization), indent=2))
    else:
        if args.authorization is None:
            parser.error("run requires --authorization")
        sys.exit(run(args.authorization, args.offer))
