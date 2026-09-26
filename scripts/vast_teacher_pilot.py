"""One separately budgeted Qwen candidate trial. Credentials remain local."""

import argparse
import math
import subprocess
import sys
import tarfile
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from remote_teacher_pilot import TRIALS  # noqa: E402
from sample_interaction_teacher import OUTPUT, make_plan, sha256, validate_report  # noqa: E402
from vast_alpha_session import start_guard, upload, wait_for_ssh  # noqa: E402
from vast_smoke import IMAGE, credit, destroy, request  # noqa: E402
from vast_train import finite_number  # noqa: E402

from emoji_studio.common import read_json, write_json  # noqa: E402

ARTIFACT_ROOT = ROOT / "artifacts/vast-teacher-pilot"
FILES = [
    "pyproject.toml", "uv.lock", "src", "configs/high-five-teacher-pilot.json",
    "benchmarks/high-five-v1.json", "scripts/remote_environment.py",
    "scripts/sample_interaction_teacher.py", "scripts/remote_teacher_pilot.py",
    f"{OUTPUT}/plan.json",
]


def trial_plan(trial="pilot"):
    if trial not in TRIALS:
        raise ValueError("Unknown teacher trial")
    if trial == "pilot":
        return make_plan()
    from sample_golden_teacher import make_plan as golden_plan
    return golden_plan(ROOT)


def artifact_root(trial="pilot"):
    return ARTIFACT_ROOT if trial == "pilot" else ROOT / "artifacts/vast-golden-audition"


def locked_inputs(trial="pilot"):
    return {
        "plan_hash": trial_plan(trial)["plan_hash"],
        "launcher_sha256": sha256(Path(__file__)),
        "guard_sha256": sha256(ROOT / "scripts/vast_train.py"),
        "api_helper_sha256": sha256(ROOT / "scripts/vast_smoke.py"),
        "ssh_helper_sha256": sha256(ROOT / "scripts/vast_alpha_session.py"),
        "remote_launcher_sha256": sha256(ROOT / "scripts/remote_teacher_pilot.py"),
        "environment_sha256": sha256(ROOT / "scripts/remote_environment.py"),
    }


def load_authorization(path, trial="pilot"):
    root = artifact_root(trial)
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError("Authorization must be inside the teacher artifact directory")
    auth = read_json(path)
    expected = {"authorized": True, "experiment": TRIALS[trial]["experiment"],
                **locked_inputs(trial)}
    required = {*expected, "authorization_id", "max_total_dollars", "max_hourly_dollars",
                "max_elapsed_seconds", "expires_epoch"}
    if (set(auth) != required or auth.get("authorized") is not True
            or any(auth.get(k) != v for k, v in expected.items())):
        raise ValueError("Authorization does not match the locked candidate trial")
    identifier = auth["authorization_id"]
    if not isinstance(identifier, str) or not identifier.isascii() or not identifier.isalnum():
        raise ValueError("Invalid authorization ID")
    total_cap, elapsed_cap = (1.25, 2700) if trial == "golden" else (1.50, 3600)
    for key, lower, upper in [
        ("max_total_dollars", 0.50, total_cap), ("max_hourly_dollars", 0.01, 0.80),
        ("max_elapsed_seconds", 1800, elapsed_cap),
    ]:
        if not finite_number(auth[key]) or not lower <= auth[key] <= upper:
            raise ValueError(f"Invalid {key}")
    if not finite_number(auth["expires_epoch"]) or time.time() >= auth["expires_epoch"]:
        raise ValueError("Authorization expired")
    for prior in root.glob("*/attempt.json"):
        if read_json(prior).get("authorization_id") == identifier:
            raise ValueError("Authorization already consumed")
    return auth


def offer_allowed(row, hourly):
    try:
        limits = {"num_gpus": (1, 1), "gpu_ram": (48000, math.inf),
                  "cpu_ram": (128000, math.inf), "disk_space": (160, math.inf),
                  "compute_cap": (800, math.inf), "reliability": (0.98, 1),
                  "dph_total": (0, hourly), "inet_down_cost": (0, 0.007),
                  "inet_up_cost": (0, 0.007)}
        return all(finite_number(row[k]) and low <= row[k] <= high
                   for k, (low, high) in limits.items())
    except (KeyError, TypeError):
        return False


def offers(hourly):
    query = {
        "type": "ondemand", "allocated_storage": 160, "verified": {"eq": True},
        "rentable": {"eq": True}, "rented": {"eq": False}, "num_gpus": {"eq": 1},
        "gpu_ram": {"gte": 48000}, "cpu_ram": {"gte": 128000},
        "disk_space": {"gte": 160}, "compute_cap": {"gte": 800},
        "cuda_max_good": {"gte": 12.8}, "dph_total": {"lte": hourly},
        "inet_down_cost": {"lte": 0.007}, "inet_up_cost": {"lte": 0.007},
        "reliability": {"gte": 0.98}, "inet_down": {"gte": 500},
        "direct_port_count": {"gte": 1}, "limit": 20,
        "order": [["dlperf", "desc"], ["inet_down", "desc"]],
    }
    return [r for r in request("POST", "/v0/bundles/", query)["offers"]
            if offer_allowed(r, hourly)]


def build_archive(path, trial="pilot"):
    output = TRIALS[trial]["output"]
    plan = trial_plan(trial)
    if read_json(ROOT / output / "plan.json") != plan:
        raise ValueError("Local plan differs from locked inputs")
    names = list(FILES)
    if trial != "pilot":
        names.remove(TRIALS["pilot"]["config"])
        names.remove(f"{OUTPUT}/plan.json")
        names.extend([TRIALS[trial]["config"], TRIALS[trial]["sampler"], f"{output}/plan.json"])
    if (ROOT / output / "report.json").exists():
        report = validate_report(ROOT / output, plan, require_complete=False)
        names.append(f"{output}/report.json")
        for row in report["images"]:
            image = f"images/{row['job']['id']}.png"
            if row["image"] != image:
                raise ValueError("Unexpected resume image path")
            names.append(f"{output}/{image}")
    with tarfile.open(path, "w:gz") as archive:
        for name in names:
            archive.add(ROOT / name, arcname=name,
                        filter=lambda row: None if "__pycache__" in row.name else row)


def require_live_budget(state, folder):
    current = time.time()
    if current >= state["deadline_epoch"] - 240:
        raise TimeoutError("Teacher pilot reached its cleanup reserve")
    heartbeat = read_json(folder / "guard-heartbeat.json")
    if current - heartbeat["time"] > 90:
        raise RuntimeError("Budget watchdog heartbeat is stale")
    if heartbeat.get("stop_reason") or (folder / "guard-result.json").exists():
        raise RuntimeError("Budget watchdog has requested shutdown")
    if heartbeat.get("observed_spent", 0) >= state["max_total_dollars"]:
        raise TimeoutError("Teacher pilot credit guard reached")


def read_with_retries(operation, state, folder):
    """Retry only read-only SSH transport failures, never allocation or launch."""
    for attempt in range(3):
        require_live_budget(state, folder)
        try:
            return operation()
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            if isinstance(error, subprocess.CalledProcessError) and error.returncode != 255:
                raise
            event_path = folder / "transport-retries.json"
            events = read_json(event_path) if event_path.exists() else []
            events.append({"time": time.time(), "attempt": attempt + 1,
                           "error_type": type(error).__name__,
                           "returncode": getattr(error, "returncode", None)})
            write_json(event_path, events)
            if attempt == 2:
                raise
            print(f"Read-only SSH retry {attempt + 1}/2: {type(error).__name__}", flush=True)
            time.sleep(5)


def snapshot(ssh, folder, *, final=False, trial="pilot"):
    relative = TRIALS[trial]["output"]
    path = folder / "results.download"
    with path.open("wb") as stream:
        subprocess.run([
            *ssh, "cd /workspace/emoji-studio && "
                  f"python3 scripts/remote_teacher_pilot.py --snapshot --trial {trial}",
        ], stdout=stream, stderr=subprocess.PIPE, check=True, timeout=60)
    with tarfile.open(path) as archive:
        for member in archive.getmembers():
            if (member.name.startswith("/") or ".." in Path(member.name).parts
                    or not (member.name == "teacher.log" or member.name == relative
                            or member.name.startswith(relative + "/"))
                    or not (member.isfile() or member.isdir())):
                raise ValueError("Unexpected result archive member")
        with tempfile.TemporaryDirectory() as temp:
            archive.extractall(temp, filter="data")
            output = Path(temp) / relative
            if read_json(output / "plan.json") != trial_plan(trial):
                raise ValueError("Remote plan differs from local plan")
            if (output / "report.json").exists():
                validate_report(output, trial_plan(trial), require_complete=final)
            elif final:
                raise ValueError("No teacher report returned")
        # Preserve validated results locally, including partial progress.
        archive.extractall(ROOT, filter="data")
    path.replace(folder / ("final-results.tar.gz" if final else "results.tar.gz"))


def run(path, trial="pilot"):
    auth = load_authorization(path, trial)
    plan = trial_plan(trial)
    total = len(plan["jobs"])
    output = TRIALS[trial]["output"]
    if (ROOT / output / "report.json").exists():
        saved = validate_report(ROOT / output, plan, require_complete=False)
        if len(saved["images"]) == total:
            raise ValueError("All candidate images already exist; refusing an unnecessary rental")
    if request("GET", "/v1/instances/").get("total_instances", 0):
        raise ValueError("An existing GPU instance must be reconciled first")
    balance = credit()
    if balance < auth["max_total_dollars"]:
        raise ValueError("Insufficient prepaid credit")
    available = offers(auth["max_hourly_dollars"])
    if not available:
        raise ValueError("No compatible 48 GB GPU / 128 GB RAM offer inside the rate limit")
    offer = available[0]
    folder = artifact_root(trial) / ("emoji-teacher-" + uuid.uuid4().hex[:10])
    folder.mkdir(parents=True)
    archive = folder / "project.tar.gz"
    build_archive(archive, trial)
    identity = folder / "id_ed25519"
    subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(identity)],
                   check=True, timeout=30)
    state = {
        "authorization_id": auth["authorization_id"], "label": folder.name,
        "created_epoch": time.time(),
        "credit_before": balance, "authorized_total_dollars": auth["max_total_dollars"],
        "max_total_dollars": auth["max_total_dollars"] - 0.15,
        "deadline_epoch": time.time() + auth["max_elapsed_seconds"],
        "cleanup_lead_seconds": 180, "offer": offer, "trial": trial, **locked_inputs(trial),
    }
    write_json(folder / "attempt.json", state)
    ssh = None
    try:
        try:
            created = request("PUT", f"/v0/asks/{offer['id']}/", {
                "image": IMAGE, "disk": 160, "label": state["label"], "runtype": "ssh",
                "target_state": "running", "cancel_unavail": True,
                "onstart": "chown root:root /root/.ssh /root/.ssh/authorized_keys\n"
                           "chmod 700 /root/.ssh\nchmod 600 /root/.ssh/authorized_keys\n",
            })
            state["instance_id"] = created["new_contract"]
        except Exception:
            # A lost response can still represent a committed rental. Never blindly retry.
            matches = [r for r in request("GET", "/v1/instances/").get("instances", [])
                       if r.get("label") == state["label"]]
            if len(matches) == 1:
                state["instance_id"] = matches[0]["id"]
            else:
                raise
        state_path = folder / "allocation.json"
        write_json(state_path, state)
        start_guard(state_path, folder)
        guard_ready_deadline = time.time() + 50
        while not (folder / "guard-heartbeat.json").exists():
            if (folder / "guard-result.json").exists() or time.time() >= guard_ready_deadline:
                raise RuntimeError("Budget watchdog did not confirm a live heartbeat")
            time.sleep(1)
        request("POST", f"/v0/instances/{state['instance_id']}/ssh/",
                {"ssh_key": identity.with_suffix(".pub").read_text().strip()})
        ssh = wait_for_ssh(state, identity)
        upload(ssh, identity, archive)
        subprocess.run([*ssh, "mkdir -p /workspace/emoji-studio && "
                        "tar -xzf /root/emoji-alpha.tar.gz -C /workspace/emoji-studio"],
                       check=True, timeout=60)
        seconds = min(3300, int(state["deadline_epoch"] - time.time() - 300))
        if seconds < 900:
            raise TimeoutError("Insufficient time remains after setup")
        subprocess.run([*ssh, "cd /workspace/emoji-studio && python3 "
                        f"scripts/remote_teacher_pilot.py --seconds {seconds} --trial {trial}"],
                       check=True, timeout=30)
        last_snapshot = 0
        while time.time() < state["deadline_epoch"] - 240:
            require_live_budget(state, folder)
            if state["credit_before"] - credit() >= state["max_total_dollars"]:
                raise TimeoutError("Teacher pilot credit guard reached")
            result = read_with_retries(lambda: subprocess.run(
                [*ssh, "cd /workspace/emoji-studio && "
                 "if test -f teacher.exit; then cat teacher.exit; fi"],
                capture_output=True, text=True, timeout=30, check=True), state, folder)
            if result.stdout.strip():
                read_with_retries(
                    lambda: snapshot(ssh, folder, final=result.stdout.strip() == "0", trial=trial),
                    state, folder)
                if result.stdout.strip() != "0":
                    raise RuntimeError("Remote teacher trial failed; saved its partial results")
                print(f"{total} candidates verified; training review remains pending", flush=True)
                return
            if time.time() - last_snapshot >= 60:
                read_with_retries(lambda: snapshot(ssh, folder, trial=trial), state, folder)
                last_snapshot = time.time()
                report = ROOT / output / "report.json"
                count = len(read_json(report)["images"]) if report.exists() else 0
                print(f"Candidate progress: {count}/{total}", flush=True)
            time.sleep(15)
        raise TimeoutError("Teacher pilot reached its cleanup reserve")
    finally:
        if "instance_id" in state:
            # Never make successful cleanup depend on billing or a result download.
            for attempt in range(3):
                try:
                    result = destroy(state)
                    write_json(folder / "cleanup.json", {"result": result, "time": time.time()})
                    break
                except Exception as error:
                    print(f"Cleanup retry {attempt + 1}: {type(error).__name__}", flush=True)
                    time.sleep(5)
            else:
                raise RuntimeError(f"Cleanup unconfirmed; inspect instance {state['instance_id']}")
            reconciliation = {"credit_before": balance, "billing_may_lag": True,
                              "elapsed_seconds": time.time() - state["created_epoch"]}
            try:
                instances = request("GET", "/v1/instances/").get("instances", [])
                reconciliation["owned_instance_absent"] = not any(
                    row.get("id") == state["instance_id"] for row in instances
                )
                after = credit()
                reconciliation.update(credit_after=after, observed_credit_change=balance - after)
            except Exception as error:
                reconciliation["observation_error"] = type(error).__name__
            write_json(folder / "cost.json", reconciliation)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorization", type=Path, required=True)
    parser.add_argument("--trial", choices=TRIALS, default="pilot")
    args = parser.parse_args()
    run(args.authorization, args.trial)
