"""One-allocation AMD evaluation controller; runs entirely on GitHub Actions."""

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import shlex
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

API = "https://api.devcloud.amd.com/v2"
NAME = "emoji-ops-compare-v1"
TAG = "emoji-ops-compare-v1"
SIZE = "gpu-mi300x1-192gb-devcloud"
RELEASE = "amd-comparison-v1"
REMOTE = "/shared-docker/emoji-studio"
STATE = Path("state.json")
RESULTS = Path("results")


def command(args, **kwargs):
    result = subprocess.run(args, text=True, capture_output=True, **kwargs)
    if result.returncode:
        diagnostic = result.stderr[-6000:]
        for name in ("AMD_DEV_CLOUD_TOKEN", "GH_TOKEN"):
            if os.environ.get(name):
                diagnostic = diagnostic.replace(os.environ[name], "[REDACTED]")
        print(f"{args[0]} failed ({result.returncode}): {diagnostic}", flush=True)
        result.check_returncode()
    return result.stdout


def retry_command(args, **kwargs):
    for attempt in range(3):
        try:
            return command(args, **kwargs)
        except (subprocess.SubprocessError, OSError):
            if attempt == 2:
                raise
            time.sleep(10 * (attempt + 1))


def api(method, path, payload=None):
    request = urllib.request.Request(
        API + path, method=method,
        headers={"Authorization": "Bearer " + os.environ["AMD_DEV_CLOUD_TOKEN"],
                 "Content-Type": "application/json"},
        data=json.dumps(payload).encode() if payload is not None else None,
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read()
        return json.loads(raw) if raw else None


def release_file(path):
    command(["gh", "release", "upload", RELEASE, str(path), "--clobber"], timeout=180)


def record(state, **updates):
    state.update(updates, updated_at=dt.datetime.now(dt.UTC).isoformat())
    STATE.write_text(json.dumps(state, indent=2) + "\n")
    release_file(STATE)


def owned(droplet):
    return droplet.get("name") == NAME and TAG in droplet.get("tags", [])


def droplets():
    found, page = [], 1
    while True:
        response = api("GET", f"/droplets?per_page=200&page={page}")
        found.extend(d for d in response["droplets"] if owned(d))
        if not response.get("links", {}).get("pages", {}).get("next"):
            return found
        page += 1


def destroy(identifier):
    try:
        droplet = api("GET", f"/droplets/{identifier}")["droplet"]
    except urllib.error.HTTPError as error:
        if error.code == 404:
            return
        raise
    if not owned(droplet):
        raise ValueError("Refusing to delete a droplet outside this campaign")
    api("DELETE", f"/droplets/{identifier}")
    for _ in range(12):
        try:
            api("GET", f"/droplets/{identifier}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return
            raise
        time.sleep(5)
    raise TimeoutError("Deletion was requested but not confirmed")


def reap(now=None):
    now = now or time.time()
    removed = []
    for droplet in droplets():
        created = dt.datetime.fromisoformat(droplet["created_at"].replace("Z", "+00:00"))
        if now - created.timestamp() > 4500:
            destroy(droplet["id"])
            removed.append(droplet["id"])
    print(json.dumps({"reaped": removed}), flush=True)


def guard_user_data():
    # A root-only guard deletes its own verified instance even if the runner disappears.
    guard = '''import json, time, urllib.request, urllib.error
from pathlib import Path
token = Path('/root/emoji-ops-token').read_text().strip()
while True:
 try:
  ident = urllib.request.urlopen('http://169.254.169.254/metadata/v1/id', timeout=10).read().decode().strip()
  url = 'https://api.devcloud.amd.com/v2/droplets/' + str(int(ident))
  headers = {'Authorization': 'Bearer ' + token}
  row = json.load(urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30))['droplet']
  if row['name'] != 'emoji-ops-compare-v1' or 'emoji-ops-compare-v1' not in row['tags']:
   raise SystemExit('Ownership check failed')
  urllib.request.urlopen(urllib.request.Request(url, headers=headers, method='DELETE'), timeout=45).close()
 except urllib.error.HTTPError as exc:
  if exc.code == 404: break
 except Exception:
  pass
 time.sleep(30)
'''
    token = base64.b64encode(os.environ["AMD_DEV_CLOUD_TOKEN"].encode()).decode()
    script = base64.b64encode(guard.encode()).decode()
    return f'''#cloud-config
write_files:
  - path: /root/emoji-ops-token
    permissions: '0600'
    encoding: b64
    content: {token}
  - path: /root/emoji-ops-guard.py
    permissions: '0700'
    encoding: b64
    content: {script}
runcmd:
  - [systemd-run, --unit=emoji-ops-expiry, --on-active=65m, /usr/bin/python3, /root/emoji-ops-guard.py]
'''


def ssh_options(multiplex=True):
    options = ["-i", os.environ["AMD_SSH_KEY_FILE"], "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=15", "-o", "StrictHostKeyChecking=accept-new",
            "-o", "ServerAliveInterval=10", "-o", "ServerAliveCountMax=3"]
    if multiplex:
        options += ["-o", "ControlMaster=auto", "-o", "ControlPersist=600",
                    "-o", "ControlPath=/tmp/emoji-ops-ssh-%C"]
    else:
        options += ["-o", "ControlMaster=no", "-o", "ControlPath=none"]
    return options


def ssh(ip, text, timeout=60, multiplex=True):
    return retry_command(["ssh", *ssh_options(multiplex), f"root@{ip}", text], timeout=timeout)


def remote_ready(ip):
    marker = "EMOJI_OPS_READY_V1"
    output = ssh(ip, "test -f /var/lib/cloud/instance/boot-finished && "
                 "test -d /shared-docker && command -v rsync >/dev/null && "
                 "docker inspect rocm >/dev/null && "
                 "systemctl is-active --quiet emoji-ops-expiry.timer && "
                 f"printf '{marker}\\n'", timeout=30, multiplex=False)
    if output.strip() != marker:
        print(f"SSH initialization is not clean/ready: {output[-1200:]!r}", flush=True)
        return False
    return True


def snapshot(ip):
    RESULTS.mkdir(exist_ok=True)
    transport = shlex.join(["ssh", *ssh_options()])
    retry_command(["rsync", "-az", "--partial", "--timeout=45", "-e", transport,
             f"root@{ip}:{REMOTE}/runs/amd-comparison-v1/", str(RESULTS) + "/"], timeout=90)
    for filename in ("worker.log", "worker.exit"):
        content = ssh(ip, f"if test -f {REMOTE}/{filename}; then cat {REMOTE}/{filename}; fi")
        if content:
            (RESULTS / filename).write_text(content)
    with tarfile.open("live-results.tar.gz", "w:gz") as archive:
        archive.add(RESULTS, arcname="amd-comparison-v1")
    release_file(Path("live-results.tar.gz"))


def run():
    config = json.loads(Path("ops/campaign.json").read_text())
    command(["gh", "release", "download", RELEASE, "--pattern", "state.json", "--clobber"])
    state = json.loads(STATE.read_text())
    if state["status"] in ("completed", "failed", "expired"):
        print(json.dumps(state))
        return
    if time.time() > config["expires_epoch"]:
        record(state, status="expired")
        return
    if state.get("allocation_attempted"):
        # Recovery never allocates twice. A crashed controller is handled by the guard/reaper.
        print("Prior allocation is consumed; waiting for cleanup or explicit recovery.")
        return
    if len(state.get("previous_attempts", [])) >= config["max_allocations"]:
        raise ValueError("Campaign allocation limit reached")
    previous_seconds = sum(max(0, item["cleanup_epoch"] - item["started_epoch"])
                           for item in state.get("previous_attempts", []))
    # Budget conservatively for 75 more minutes, including initialization and cleanup margin.
    if (previous_seconds + 4500) * config["max_hourly_dollars"] / 3600 > config["spending_reserve_dollars"]:
        raise ValueError("Insufficient remaining campaign reserve for another guarded attempt")
    if droplets():
        raise ValueError("An instance already exists for this campaign")
    sizes = api("GET", "/sizes?per_page=200")["sizes"]
    size = next(row for row in sizes if row["slug"] == SIZE)
    if float(size["price_hourly"]) > config["max_hourly_dollars"]:
        raise ValueError("Current rate exceeds campaign ceiling")
    command(["gh", "release", "download", RELEASE, "--pattern", "inputs.tar.gz", "--clobber"])
    with Path("inputs.tar.gz").open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != config["input_sha256"]:
            raise ValueError("Input archive differs from lock")
    record(state, status="allocating", allocation_attempted=True, started_epoch=time.time())
    droplet_id, ip, worker_started = None, None, False
    try:
        try:
            response = api("POST", "/droplets", {
                "name": NAME, "region": "atl1", "size": SIZE,
                "image": 222743415, "ssh_keys": [int(os.environ["AMD_SSH_KEY_ID"])],
                "backups": False, "ipv6": False, "monitoring": True, "tags": [TAG],
                "user_data": guard_user_data(),
            })
        except urllib.error.HTTPError as error:
            body = error.read().decode()
            if error.code == 422 and ("unavailable" in body.lower() or "capacity" in body.lower()):
                record(state, status="waiting_capacity", allocation_attempted=False)
                return
            raise RuntimeError(f"AMD allocation HTTP {error.code}") from None
        droplet_id = response["droplet"]["id"]
        record(state, status="booting", droplet_id=droplet_id)
        deadline = state["started_epoch"] + 3300
        for _ in range(60):
            row = api("GET", f"/droplets/{droplet_id}")["droplet"]
            ip = next((n["ip_address"] for n in row["networks"]["v4"]
                       if n["type"] == "public"), None)
            if ip:
                try:
                    if remote_ready(ip):
                        break
                except (subprocess.SubprocessError, OSError):
                    pass
            time.sleep(10)
        else:
            raise TimeoutError("GPU image or independent expiry timer did not become ready")
        created = ssh(ip, f"mkdir -p {REMOTE}/runs/amd-comparison-v1 && printf 'DIRECTORY_READY\\n'")
        if created.strip() != "DIRECTORY_READY":
            raise RuntimeError("Remote shell did not confirm working-directory creation")
        retry_command(["rsync", "-az", "--partial", "--timeout=60", "-e",
                       shlex.join(["ssh", *ssh_options()]), "inputs.tar.gz",
                       f"root@{ip}:{REMOTE}/inputs.tar.gz"], timeout=240)
        check = ssh(ip, f"sha256sum {REMOTE}/inputs.tar.gz").split()[0]
        if check != config["input_sha256"]:
            raise ValueError("Transferred input checksum mismatch")
        ssh(ip, f"cd {REMOTE} && tar -xzf inputs.tar.gz --no-same-owner", timeout=60)
        launch = (
            "if test \"$(systemctl show --property=LoadState --value emoji-comparison-worker.service)\" = loaded; "
            "then true; else systemd-run --unit=emoji-comparison-worker "
            f"--property=WorkingDirectory={REMOTE} /bin/bash -c "
            + shlex.quote("exec bash ops/remote_compare.sh >worker.log 2>&1") + "; fi"
        )
        ssh(ip, launch, timeout=30)
        worker_started = True
        record(state, status="running")
        while time.time() < deadline:
            time.sleep(45)
            snapshot(ip)
            if (RESULTS / "worker.exit").exists():
                if (RESULTS / "worker.exit").read_text().strip() != "0":
                    raise RuntimeError("Remote evaluation failed; see backed-up worker.log")
                report = json.loads((RESULTS / "report.json").read_text())
                if report["status"] != "completed" or len(report["images"]) != 144:
                    raise ValueError("Final image count or status differs")
                for image in report["images"]:
                    source = RESULTS / image["image"]
                    if not source.resolve().is_relative_to(RESULTS.resolve()):
                        raise ValueError("Unsafe image path")
                    with source.open("rb") as stream:
                        if hashlib.file_digest(stream, "sha256").hexdigest() != image["sha256"]:
                            raise ValueError("Downloaded image checksum differs")
                Path("results.tar.gz").write_bytes(Path("live-results.tar.gz").read_bytes())
                release_file(Path("results.tar.gz"))
                record(state, status="completed", images=144, finished_epoch=time.time())
                return
        raise TimeoutError("Campaign runtime deadline reached")
    except BaseException as error:
        record(state, status="failed", error=type(error).__name__)
        raise
    finally:
        if ip and worker_started:
            try:
                snapshot(ip)
            except Exception as error:
                print(f"Final snapshot failed: {type(error).__name__}", flush=True)
        # Reconcile ambiguous POST results by exact name AND campaign ownership tag.
        for row in droplets():
            destroy(row["id"])
        record(state, cleanup_confirmed=True, cleanup_epoch=time.time())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["run", "reap"])
    args = parser.parse_args()
    reap() if args.command == "reap" else run()
