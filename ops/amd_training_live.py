"""Dedicated bounded coverage training; preserves all consumed API/comparison campaigns."""

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

API = "https://api.devcloud.amd.com/v2"
SIZE = "gpu-mi300x1-192gb-devcloud"
RELEASE = "amd-coverage-20261031a"
NAME = "emoji-coverage-20261031a"
REMOTE = "/shared-docker/emoji-training-smoke"
PLAN = Path("ops/amd-training-live-plan.json")


class ProviderError(RuntimeError):
    def __init__(self, code, method, path):
        self.code = code
        super().__init__(f"AMD HTTP {code}: {method} {path.split('?')[0]}")


def api(method, path, payload=None):
    request = urllib.request.Request(
        API + path, method=method,
        headers={"Authorization": "Bearer " + os.environ["AMD_DEV_CLOUD_TOKEN"],
                 "Content-Type": "application/json"},
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        # Never expose response bodies or credentials in workflow logs.
        raise ProviderError(error.code, method, path) from None


def preflight():
    result = {"allocation_attempted": False}
    for name, path in (
        ("account", "/account"), ("balance", "/customers/my/balance"),
        ("sizes", "/sizes?per_page=200"),
        ("image", "/images/222743415"), ("droplets", "/droplets?per_page=200"),
    ):
        try:
            response = api("GET", path)
            if name == "account":
                result[name] = {k: response["account"].get(k) for k in ("status", "droplet_limit")}
            elif name == "balance":
                result[name] = {k: response.get(k) for k in (
                    "account_balance", "month_to_date_balance", "month_to_date_usage", "generated_at"
                )}
            elif name == "sizes":
                result[name] = [{k: row.get(k) for k in (
                    "slug", "price_hourly", "available", "regions", "disk", "memory", "vcpus"
                )} for row in response["sizes"] if row["slug"] == SIZE]
            elif name == "image":
                result[name] = {k: response["image"].get(k) for k in (
                    "id", "name", "status", "regions", "min_disk_size", "created_at"
                )}
            else:
                result[name] = {"count": len(response["droplets"]),
                                "has_next_page": bool(response.get("links", {}).get("pages", {}).get("next"))}
        except Exception as error:
            result[name] = {"error": str(error) if isinstance(error, RuntimeError) else type(error).__name__}
    Path("training-preflight.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    return result


class CommandError(RuntimeError):
    def __init__(self, program, code):
        self.code = code
        super().__init__(f"{program} exited {code}")


class ProviderInitializing(RuntimeError):
    pass


def transport_diagnostic(program, code, detail):
    detail = detail[-4096:]
    for name in ("AMD_DEV_CLOUD_TOKEN", "GH_TOKEN", "AMD_SSH_PRIVATE_KEY"):
        if os.environ.get(name):
            detail = detail.replace(os.environ[name], "[REDACTED]")
    with Path("transport-errors.jsonl").open("a") as log:
        log.write(json.dumps({"program": program, "code": code,
                              "detail": detail, "epoch": time.time()}) + "\n")


def command(args, timeout=30):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # Keep useful transport diagnostics privately, without command lines/secrets.
        diagnostic = result.stderr + (result.stdout if Path(args[0]).name == "ssh" else "")
        transport_diagnostic(Path(args[0]).name, result.returncode, diagnostic)
        raise CommandError(Path(args[0]).name, result.returncode)
    return result.stdout


def put(name, value, replace=False):
    Path(name).write_text(json.dumps(value, indent=2) + "\n")
    args = ["gh", "release", "upload", RELEASE, name]
    if replace:
        args.append("--clobber")
    command(args, timeout=30)


def get(name):
    return json.loads(command(["gh", "release", "download", RELEASE, "-p", name, "-O", "-"], timeout=30))


def stop_requested():
    assets = json.loads(command(["gh", "release", "view", RELEASE, "--json", "assets"]))["assets"]
    if not any(item["name"] == "stop-request.json" for item in assets):
        return False
    request = get("stop-request.json")
    if request.get("campaign") != RELEASE or request.get("run_id") != os.environ["GITHUB_RUN_ID"]:
        raise ValueError("Stop request identity mismatch")
    return True


def check_stop():
    if stop_requested():
        raise RuntimeError("Early cleanup requested by usage guard")


def owned(row, intent):
    created = dt.datetime.fromisoformat(row["created_at"].replace("Z", "+00:00")).timestamp()
    return (row.get("name") == NAME and NAME in row.get("tags", [])
            and row.get("size_slug") == SIZE and row.get("region", {}).get("slug") == "atl1"
            and intent["started_epoch"] - 5 <= created <= intent["started_epoch"] + 120)


def candidates(intent):
    response = api("GET", f"/droplets?tag_name={NAME}&per_page=200")
    if response.get("links", {}).get("pages", {}).get("next"):
        raise RuntimeError("Ambiguous owned-resource listing")
    return [row for row in response["droplets"] if owned(row, intent)]


def delete_exact(identifier, intent):
    try:
        row = api("GET", f"/droplets/{int(identifier)}")["droplet"]
    except ProviderError as error:
        if error.code == 404:
            return True
        raise
    if not owned(row, intent):
        raise RuntimeError("Exact resource ownership mismatch")
    try:
        api("DELETE", f"/droplets/{int(identifier)}")
    except ProviderError as error:
        if error.code != 404:
            raise
    # Only a subsequent authenticated exact-resource 404 confirms cleanup.
    for _ in range(12):
        try:
            api("GET", f"/droplets/{int(identifier)}")
        except ProviderError as error:
            if error.code == 404:
                return True
            raise
        time.sleep(5)
    return False


def cloud_init(intent):
    # Absolute expiry survives controller loss and model usage exhaustion.
    guard = '''import json,time,urllib.request,urllib.error
from pathlib import Path
token=Path('/root/emoji-training-token').read_text()
intent=json.loads(Path('/root/emoji-training-intent').read_text())
while True:
 try:
  ident=int(urllib.request.urlopen('http://169.254.169.254/metadata/v1/id',timeout=10).read())
  url='https://api.devcloud.amd.com/v2/droplets/'+str(ident)
  headers={'Authorization':'Bearer '+token}
  row=json.load(urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=15))['droplet']
  if row['name'] != 'CAMPAIGN_NAME' or 'CAMPAIGN_NAME' not in row['tags']:
   raise SystemExit('Ownership mismatch')
  urllib.request.urlopen(urllib.request.Request(url,headers=headers,method='DELETE'),timeout=15).close()
 except urllib.error.HTTPError as e:
  if e.code==404: break
 except Exception: pass
 time.sleep(15)
'''.replace("CAMPAIGN_NAME", NAME)
    values = {"token": os.environ["AMD_DEV_CLOUD_TOKEN"], "intent": json.dumps(intent), "guard.py": guard}
    data = "#cloud-config\nwrite_files:\n"
    for name, value in values.items():
        data += (f"  - path: /root/emoji-training-{name}\n    permissions: '0600'\n"
                 f"    encoding: b64\n    content: {base64.b64encode(value.encode()).decode()}\n")
    expiry = int(intent["started_epoch"] + 3360)
    data += ("runcmd:\n  - [systemd-run, --unit=emoji-training-expiry, "
             f"'--on-calendar=@{expiry}', /usr/bin/python3, /root/emoji-training-guard.py]\n")
    return data


def ssh_args(master=False):
    return ["-i", os.environ["AMD_SSH_KEY_FILE"], "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
            "-o", "StrictHostKeyChecking=accept-new", "-o", "ServerAliveInterval=10",
            "-o", "ServerAliveCountMax=2", "-o", "ControlMaster=yes" if master else "ControlMaster=no",
            "-o", "ControlPersist=600", "-o", "ControlPath=/tmp/emoji-training-%C"]


def start_control(ip):
    # Never create a background master from a capture_output=True call: inherited
    # pipe handles can prevent communicate() from seeing EOF after a probe ends.
    with tempfile.TemporaryFile(mode="w+") as diagnostic:
        result = subprocess.run(["ssh", *ssh_args(master=True), "-N", "-f", f"root@{ip}"],
                                stdout=subprocess.DEVNULL, stderr=diagnostic, timeout=20)
        if result.returncode:
            diagnostic.seek(0)
            transport_diagnostic("ssh-control", result.returncode, diagnostic.read())
            raise CommandError("ssh-control", result.returncode)


def ssh(ip, script, timeout=30):
    # Provider images can print a banner from shell startup files. Frame the
    # command's stdout instead of interpreting the entire SSH stream as data.
    marker = "EMOJI_API_" + uuid.uuid4().hex
    framed = (f"printf '\\n{marker}:BEGIN\\n'; ( {script} ); rc=$?; "
              f"printf '\\n{marker}:END:%s\\n' \"$rc\"; exit \"$rc\"")
    try:
        output = command(["ssh", *ssh_args(), f"root@{ip}", framed], timeout=timeout)
    except subprocess.TimeoutExpired as error:
        partial = error.stdout or b""
        transport_diagnostic("ssh", "timeout", partial.decode(errors="replace") if isinstance(partial, bytes) else partial)
        raise
    begin, end = f"{marker}:BEGIN\n", f"\n{marker}:END:0"
    if output.count(begin) != 1 or output.count(end) != 1:
        transport_diagnostic("ssh", "framing_missing", output)
        if "Please wait while we get your droplet ready" in output:
            raise ProviderInitializing("Provider image initialization is still running")
        raise RuntimeError("SSH response framing missing; no command result accepted")
    return output.split(begin, 1)[1].split(end, 1)[0]


def ssh_read(ip, script, timeout=30):
    """Explicit read-only calls may reconnect; never wrap launches or API POSTs."""
    for attempt in range(3):
        try:
            return ssh(ip, script, timeout=timeout)
        except CommandError as error:
            if error.code != 255 or attempt == 2:
                raise
        except subprocess.TimeoutExpired:
            if attempt == 2:
                raise
        time.sleep(3)


def validate_plan(plan):
    expected = {"max_allocations": 1, "max_concurrent_gpus": 1,
                "max_lifetime_seconds": 3600, "work_cutoff_seconds": 3300,
                "self_expiry_seconds": 3360, "max_hourly_dollars": 1.99,
                "reserve_dollars": 2.25, "max_training_steps": 624,
                "smoke_steps": 2, "max_physical_renders": 49}
    if any(plan.get(key) != value for key, value in expected.items()):
        raise ValueError("Training lifecycle bounds differ")
    if plan.get("campaign") != RELEASE or plan.get("previous_attempt"):
        raise ValueError("Fresh training campaign required")


def checked_files(report):
    allowed = {"smoke.safetensors", "smoke.png", "step-624.safetensors"}
    allowed.update(f"step-{step}.safetensors" for step in (125, 250, 375, 500))
    allowed.update(f"evaluation-{index:02d}.png" for index in range(48))
    files = report.get("files")
    if not isinstance(files, dict) or not set(files).issubset(allowed):
        raise ValueError("Unexpected result files")
    for value in files.values():
        if (not isinstance(value, dict) or type(value.get("bytes")) is not int
                or not 0 < value["bytes"] <= 50_000_000
                or not isinstance(value.get("sha256"), str) or len(value["sha256"]) != 64
                or any(c not in "0123456789abcdef" for c in value["sha256"])):
            raise ValueError("Invalid artifact descriptor")
    return files


def snapshot(ip):
    Path("training-results").mkdir(exist_ok=True)
    # No report is expected until environment installation finishes.
    present = ssh_read(ip, f"test -f {REMOTE}/training-results/report.json && echo yes || true")
    if present.strip() != "yes":
        return
    command(["scp", *ssh_args(), f"root@{ip}:{REMOTE}/training-results/report.json",
             "training-results/report.json"], timeout=30)
    report = json.loads(Path("training-results/report.json").read_bytes())
    for name, value in checked_files(report).items():
        target = Path("training-results", name)
        if target.exists():
            if hashlib.sha256(target.read_bytes()).hexdigest() != value["sha256"]:
                raise ValueError("Existing artifact changed")
            continue
        command(["scp", *ssh_args(), f"root@{ip}:{REMOTE}/training-results/{name}", str(target)], timeout=60)
        if target.stat().st_size != value["bytes"] or hashlib.sha256(target.read_bytes()).hexdigest() != value["sha256"]:
            raise ValueError("Downloaded training artifact checksum differs")
        # Persist immutable checkpoints as they appear, before any teardown.
        command(["gh", "release", "upload", RELEASE, str(target)], timeout=60)
    put("training-progress.json", report, replace=True)


def verify_results():
    report = json.loads(Path("training-results/report.json").read_bytes())
    plan = json.loads(PLAN.read_bytes())
    files = checked_files(report)
    if (report.get("status") != "completed" or report.get("gpu_count") != 1
            or report.get("plan_sha256") != hashlib.sha256(PLAN.read_bytes()).hexdigest()
            or report.get("recipe_sha256") != plan["source_files"]["configs/lora-coverage-v1.json"]
            or len(report.get("images", [])) != 49):
        raise ValueError("Training acceptance failed")
    for phase, steps, losses in (("smoke", 2, 8), ("training", 624, 2496)):
        result = report["phases"][phase]
        if result.get("completed_steps") != steps or result.get("loss_values") != losses or result.get("all_losses_finite") is not True:
            raise ValueError("Finite-loss training receipt differs")
    required = {"smoke.safetensors", "smoke.png", "step-500.safetensors", "step-624.safetensors"}
    required.update(f"evaluation-{index:02d}.png" for index in range(48))
    if not required.issubset(files):
        raise ValueError("Missing training/evaluation artifacts")
    for name, value in files.items():
        payload = Path("training-results", name).read_bytes()
        if len(payload) != value["bytes"] or hashlib.sha256(payload).hexdigest() != value["sha256"]:
            raise ValueError("Downloaded artifact changed")
    return report


def run():
    if os.environ.get("AMD_TRAINING_SOURCE") != os.environ.get("GITHUB_SHA"):
        raise RuntimeError("Exact approved source required")
    if os.environ.get("GITHUB_RUN_ATTEMPT") != "1":
        raise RuntimeError("Workflow reruns cannot allocate")
    plan = json.loads(PLAN.read_text())
    if time.time() >= plan["allocation_expires_epoch"]:
        raise RuntimeError("Allocation authorization expired")
    if os.environ.get("GH_REPO") != "rk9595/emoji-studio-ops":
        raise RuntimeError("Private execution repository required")
    if not json.loads(command(["gh", "repo", "view", "--json", "isPrivate"]))["isPrivate"]:
        raise RuntimeError("Private export destination required")
    prior_cost = 0.0
    validate_plan(plan)
    inspection = preflight()
    size = inspection["sizes"][0]
    if (inspection["account"]["status"] != "active" or size["price_hourly"] > 1.99
            or not size["available"] or "atl1" not in size["regions"]
            or inspection["droplets"] != {"count": 0, "has_next_page": False}):
        raise RuntimeError("Account/rate/capacity/concurrency check failed")
    command(["gh", "release", "download", RELEASE, "-p", "inputs.tar.gz", "--clobber"], timeout=120)
    if hashlib.sha256(Path("inputs.tar.gz").read_bytes()).hexdigest() != plan["input_sha256"]:
        raise ValueError("Input archive changed")
    for _ in range(18):
        try:
            registered = get("watchdog-ready.json")
            if (registered["run_id"] == os.environ["GITHUB_RUN_ID"]
                    and time.time() - registered["started_epoch"] < 180):
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        raise RuntimeError("Independent cloud watchdog is not registered")
    check_stop()
    intent = {"campaign": RELEASE, "started_epoch": time.time(), "run_id": os.environ["GITHUB_RUN_ID"],
              "source": os.environ["GITHUB_SHA"], "max_allocations": 1,
              "plan_sha256": hashlib.sha256(PLAN.read_bytes()).hexdigest(),
              "rate_hourly": size["price_hourly"]}
    # GitHub rejects a second asset with this name; never clobber this allocation claim.
    put("allocation-intent.json", intent)
    state = {**intent, "status": "allocating", "cleanup_confirmed": False}
    state["prior_attempt_cost_dollars"] = prior_cost
    identifier, ip = None, None
    try:
        response = api("POST", "/droplets", {
            "name": NAME, "region": "atl1", "size": SIZE, "image": 222743415,
            "ssh_keys": [int(os.environ["AMD_SSH_KEY_ID"])], "backups": False,
            "ipv6": False, "monitoring": True, "tags": [NAME], "user_data": cloud_init(intent),
        })
        identifier = response["droplet"]["id"]
        state.update(status="booting", droplet_id=identifier)
        put("training-state.json", state, replace=True)
        stop = intent["started_epoch"] + 3300
        # Startup gets at most15 minutes inside the55-minute work cutoff.
        while time.time() < min(stop - 300, intent["started_epoch"] + 900):
            check_stop()
            row = api("GET", f"/droplets/{identifier}")["droplet"]
            if not owned(row, intent):
                raise ValueError("Allocated resource differs from intent")
            ip = next((n["ip_address"] for n in row["networks"]["v4"] if n["type"] == "public"), None)
            if ip:
                try:
                    ready = ssh(ip, "test -f /var/lib/cloud/instance/boot-finished && "
                                "docker inspect rocm >/dev/null && "
                                "systemctl is-active --quiet emoji-training-expiry.timer && echo READY")
                    if ready.strip() == "READY":
                        break
                except ProviderInitializing:
                    if not state.get("provider_initialization_notice"):
                        state["provider_initialization_notice"] = True
                        put("training-state.json", state, replace=True)
                except Exception:
                    pass
            time.sleep(10)
        else:
            raise TimeoutError("ROCm image or expiry timer not ready")
        start_control(ip)
        ssh(ip, f"mkdir -p {REMOTE} && chmod 700 {REMOTE}")
        command(["scp", *ssh_args(), "inputs.tar.gz", f"root@{ip}:{REMOTE}/inputs.tar.gz"], timeout=120)
        if ssh_read(ip, f"sha256sum {REMOTE}/inputs.tar.gz").split()[0] != plan["input_sha256"]:
            raise ValueError("Transferred source checksum differs")
        ssh(ip, f"cd {REMOTE} && tar -xzf inputs.tar.gz --no-same-owner", timeout=30)
        command(["scp", *ssh_args(), str(PLAN), f"root@{ip}:{REMOTE}/ops/amd-training-live-plan.json"], timeout=30)
        if ssh_read(ip, f"sha256sum {REMOTE}/ops/amd-training-live-plan.json").split()[0] != intent["plan_sha256"]:
            raise ValueError("Transferred plan checksum differs")
        remaining = int(stop - time.time())
        if remaining < 2100:
            raise TimeoutError("Insufficient training time")
        check_stop()
        # Kill the container at the work cutoff even if a CUDA/HIP call is hung.
        ssh(ip, f"systemd-run --unit=emoji-training-stop --on-calendar=@{int(stop)} /usr/bin/docker stop -t 5 rocm")
        script = (f"cd {REMOTE}; "
                  "docker exec -e PYTHONPATH=src -e HF_HOME=/shared-docker/hf-cache "
                  f"-w {REMOTE} rocm bash -lc " + shlex.quote(
                      "python3 ops/amd_training_worker.py inventory && "
                      "python3 -m pip install --disable-pip-version-check --only-binary=:all: --no-deps --require-hashes "
                      "-r configs/amd-training-overlay-linux-py312.txt && python3 -m pip check && "
                      f"python3 ops/amd_training_worker.py run --allocation {identifier} --deadline {stop}"
                  ) + "; code=$?; echo $code > worker.exit; exit $code")
        # No systemd restart and no retry of worker launch.
        ssh(ip, "systemd-run --unit=emoji-training-worker "
            f"--property=RuntimeMaxSec={remaining} /bin/bash -c "
            + shlex.quote("(" + script + f") >{REMOTE}/worker.log 2>&1"))
        state.update(status="running", worker_deadline_epoch=stop)
        put("training-state.json", state, replace=True)
        while time.time() < stop:
            time.sleep(20)
            check_stop()
            exit_code = ssh_read(ip, f"cat {REMOTE}/worker.exit 2>/dev/null || true").strip()
            snapshot(ip)
            if exit_code:
                if exit_code != "0":
                    raise RuntimeError("GPU worker failed")
                report = verify_results()
                with tarfile.open("training-results.tar.gz", "w:gz") as archive:
                    archive.add("training-results", arcname="training-results")
                command(["gh", "release", "upload", RELEASE, "training-results.tar.gz"], timeout=60)
                # Independent transfer from GitHub, compared with the local archive hash.
                command(["gh", "release", "download", RELEASE, "-p", "training-results.tar.gz",
                         "-O", "verified-results.tar.gz"], timeout=60)
                if hashlib.sha256(Path("training-results.tar.gz").read_bytes()).digest() != hashlib.sha256(Path("verified-results.tar.gz").read_bytes()).digest():
                    raise ValueError("Private export download mismatch")
                state.update(status="training_verified", images=len(report["images"]), training_steps=624,
                             results_sha256=hashlib.sha256(Path("training-results.tar.gz").read_bytes()).hexdigest())
                break
        else:
            raise TimeoutError("GPU lifetime work cutoff")
    except BaseException as error:
        state.update(status="failed", error=str(error) if isinstance(error, (RuntimeError, ValueError)) else type(error).__name__)
        raise
    finally:
        # Best-effort diagnostics must not prevent deletion.
        if ip:
            try:
                log = ssh_read(ip, f"tail -c 16000 {REMOTE}/worker.log 2>/dev/null || true", timeout=15)
                Path("worker.log").write_text(log)
                snapshot(ip)
                for phase in ("smoke", "reload", "training", "evaluation"):
                    detail = ssh_read(ip, f"tail -c 32000 {REMOTE}/training-results/{phase}.log 2>/dev/null || true", timeout=15)
                    Path("training-results", phase + ".log").write_text(detail)
            except Exception:
                pass
        try:
            ids = {identifier} if identifier else set()
            # A failed list request must never block deletion of a known exact ID.
            if not ids:
                ids.update(row["id"] for row in candidates(intent))
            if len(ids) == 1:
                state["droplet_id"] = next(iter(ids))
            confirmations = [delete_exact(ident, intent) for ident in ids]
            state["cleanup_confirmed"] = bool(ids) and all(confirmations)
            state["cleanup_epoch"] = time.time()
            state["estimated_cost_dollars"] = round((time.time() - intent["started_epoch"]) * size["price_hourly"] / 3600, 4)
            state["milestone_estimated_cost_dollars"] = round(prior_cost + state["estimated_cost_dollars"], 4)
            if state["status"] == "training_verified" and state["cleanup_confirmed"]:
                state["status"] = "complete"
        finally:
            put("training-state.json", state, replace=True)


def watchdog():
    start = time.time()
    put("watchdog-ready.json", {"run_id": os.environ["GITHUB_RUN_ID"], "started_epoch": start}, replace=True)
    intent = None
    while time.time() < start + 3900:
        try:
            intent = get("allocation-intent.json")
        except Exception:
            if time.time() > start + 300:
                put("watchdog-result.json", {"allocation_intent_found": False,
                                           "status": "no_allocation_claim"}, replace=True)
                return
            time.sleep(10)
            continue
        # Keep the registered cloud job alive until cleanup is durably confirmed.
        state = {}
        try:
            state = get("training-state.json")
            if state.get("cleanup_confirmed"):
                # Independently check the exact resource, not just the controller's flag.
                if delete_exact(state["droplet_id"], intent):
                    put("watchdog-result.json", {"cleanup_confirmed": True, "droplet_id": state["droplet_id"],
                                               "checked_epoch": time.time(), "independent": True}, replace=True)
                    return
        except Exception:
            pass
        try:
            early_stop = stop_requested()
        except Exception:
            early_stop = False  # Expiry still applies if GitHub is unavailable.
        if early_stop or time.time() >= intent["started_epoch"] + 3360:
            ids = {state["droplet_id"]} if state.get("droplet_id") else set()
            if not ids:
                ids.update(row["id"] for row in candidates(intent))
            confirmations = [delete_exact(identifier, intent) for identifier in ids]
            if ids and all(confirmations):
                put("watchdog-result.json", {"cleanup_confirmed": True, "ids": sorted(ids),
                                           "droplet_id": next(iter(ids)) if len(ids) == 1 else None,
                                           "checked_epoch": time.time(), "independent": True,
                                           "early_stop": early_stop}, replace=True)
                return
        time.sleep(15)
    put("watchdog-result.json", {"cleanup_confirmed": False, "status": "needs_reconciliation"}, replace=True)
    raise RuntimeError("Watchdog requires exact-resource reconciliation")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", nargs="?", default="preflight", choices=["preflight", "run", "watchdog"])
    args = parser.parse_args()
    {"preflight": preflight, "run": run, "watchdog": watchdog}[args.command]()
