"""Token-free local wake-up checks for one explicitly authorized existing Codex thread."""

import argparse
import contextlib
import fcntl
import json
import subprocess
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "var/automation"


class AppServer:
    def __init__(self, socket_path):
        from websockets.sync.client import unix_connect

        self.connection = unix_connect(socket_path, uri="ws://localhost/", open_timeout=10)
        self.sequence = 0
        self.call("initialize", {"clientInfo": {"name": "emoji_studio_supervisor", "version": "1"},
                                 "capabilities": {"experimentalApi": True}})
        self.send({"method": "initialized"})

    def send(self, message):
        self.connection.send(json.dumps(message))

    def call(self, method, params=None, timeout=30):
        self.sequence += 1
        request_id = self.sequence
        self.send({"id": request_id, "method": method, "params": params or {}})
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            message = json.loads(self.connection.recv(timeout=max(0.1, deadline - time.monotonic())))
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(json.dumps(message["error"]))
                return message["result"]
        raise TimeoutError(f"App-server {method} timed out")

    def close(self):
        self.connection.close()


def next_reset(limits, now):
    buckets = list((limits.get("rateLimitsByLimitId") or {}).values())
    if not buckets and limits.get("rateLimits"):
        buckets = [limits["rateLimits"]]
    if not buckets:
        raise ValueError("Usage limits unavailable; deferring unattended continuation")
    resets = []
    for bucket in buckets:
        for name in ("primary", "secondary"):
            window = bucket.get(name)
            if window and window.get("usedPercent", 0) >= 100:
                resets.append(max(now + 900, (window.get("resetsAt") or now + 3600) + 60))
    return max(resets, default=now)


def save(state):
    state["checked_epoch"] = time.time()
    temporary = RUNTIME / "supervisor-state.tmp"
    temporary.write_text(json.dumps(state, indent=2) + "\n")
    temporary.replace(RUNTIME / "supervisor-state.json")


def cloud_state(config, queue=None):
    if queue and "cloud_run_id" in queue:
        run_id = str(queue["cloud_run_id"])
        repository = queue.get("cloud_repository")
        expected_head = queue.get("cloud_run_head")
        expected_workflow = queue.get("cloud_run_workflow", "AMD runtime CPU validation")
        allowed_receipts = {
            ("rk9595/emoji-studio", "AMD runtime CPU validation"),
            ("rk9595/emoji-studio", "AMD runtime private retention"),
            ("rk9595/emoji-studio", "AMD runtime retention reconciliation"),
            ("rk9595/emoji-studio-ops", "AMD two-image API smoke"),
        }
        if ((repository, expected_workflow) not in allowed_receipts or not run_id.isascii() or not run_id.isdecimal()
                or not isinstance(expected_head, str) or len(expected_head) != 40
                or any(c not in "0123456789abcdef" for c in expected_head)):
            raise ValueError("Invalid cloud receipt identity")
        result = subprocess.run(
            [config["gh"], "run", "view", run_id, "--repo", repository,
             "--json", "status,conclusion,headSha,url,workflowName"],
            check=True, capture_output=True, text=True, timeout=30,
        )
        receipt = json.loads(result.stdout)
        if (receipt["headSha"] != expected_head
                or receipt["workflowName"] != expected_workflow):
            raise ValueError("Cloud receipt differs from queued source/workflow")
        return {"status": ("completed" if receipt["conclusion"] == "success" else "failed")
                if receipt["status"] == "completed" else "running",
                "run_id": run_id, "conclusion": receipt["conclusion"]}
    with tempfile.TemporaryDirectory(prefix="emoji-cloud-status-") as directory:
        for attempt in range(3):
            try:
                subprocess.run(
                    [config["gh"], "release", "download", "amd-comparison-v1",
                     "--repo", "rk9595/emoji-studio-ops", "--pattern", "state.json",
                     "--dir", directory, "--clobber"],
                    check=True, capture_output=True, timeout=45,
                )
                break
            except (subprocess.SubprocessError, OSError):
                if attempt == 2:
                    raise
                time.sleep(5 * (attempt + 1))
        return json.loads((Path(directory) / "state.json").read_text())


def tick(config, diagnostic=False):
    state_path = RUNTIME / "supervisor-state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    if not config.get("enabled") and not diagnostic:
        return
    now = time.time()
    if now < state.get("not_before_epoch", 0) and not diagnostic:
        return
    server = AppServer(config["socket_path"])
    try:
        thread = server.call("thread/read", {"threadId": config["thread_id"],
                                             "includeTurns": False})["thread"]
        limits = server.call("account/rateLimits/read")
        state.update(thread_status=thread["status"], not_before_epoch=next_reset(limits, now))
        if diagnostic:
            state.update(reason="diagnostic_passed")
            state.pop("error", None)
            save(state)
            print(json.dumps(state, indent=2))
            return
        if state["not_before_epoch"] > now:
            state["reason"] = "waiting_for_usage_reset"
            save(state)
            return
        status = thread["status"]["type"]
        if status == "active":
            state["reason"] = "thread_already_active"
            save(state)
            return
        queue = json.loads((ROOT / "ops/work-queue.json").read_text())
        if queue["status"] in ("complete", "waiting_user", "paused"):
            state["reason"] = queue["status"]
            save(state)
            return
        if queue["status"] == "waiting_cloud":
            remote = cloud_state(config, queue)
            state["cloud_status"] = remote["status"]
            if remote["status"] not in ("completed", "failed", "expired"):
                state["reason"] = "cloud_still_working"
                save(state)
                return
        if status in ("notLoaded", "systemError"):
            server.call("thread/resume", {"threadId": config["thread_id"]})
        elif status != "idle":
            state["reason"] = f"unsupported_thread_status:{status}"
            save(state)
            return
        # Only compact between turns, after several continuations and a fresh durable handoff.
        memory = ROOT / "docs/automation-state.md"
        count = state.get("continuations", 0)
        if count and count % 6 == 0 and state.get("last_compacted_count") != count:
            if memory.stat().st_mtime > state.get("last_started_epoch", 0):
                server.call("thread/compact/start", {"threadId": config["thread_id"]})
                state.update(last_compacted_count=count, reason="compacting_saved_context")
                save(state)
                return
        # Persist before dispatch so a crash or uncertain response cannot trigger a fast repeat.
        state.update(last_started_epoch=now, not_before_epoch=now + 1800,
                     continuations=count + 1, reason="continuation_dispatched")
        state.pop("error", None)
        save(state)
        prompt = (
            "Scheduled continuation authorized by the user on 2026-10-12. "
            "Read /Users/rakeshkariya/emoji-studio-recovered/AGENTS.md, "
            "docs/automation-state.md and ops/work-queue.json there. "
            "Inspect current evidence, advance the next ready Emoji Studio task, and update those "
            "short memory/queue files before ending. If waiting on the GPU, use the cloud receipts "
            "and avoid token-consuming polling. Preserve existing spending bounds and do not "
            "repeat the consumed comparison allocation. Mark waiting_user if user judgment or "
            "missing authority is required; mark complete when this milestone is done."
        )
        server.call("turn/start", {"threadId": config["thread_id"],
                                   "input": [{"type": "text", "text": prompt}]})
    finally:
        server.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", action="store_true")
    args = parser.parse_args()
    RUNTIME.mkdir(parents=True, exist_ok=True)
    config = json.loads((RUNTIME / "supervisor.json").read_text())
    with (RUNTIME / "supervisor.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            tick(config, args.diagnostic)
        except Exception as error:
            # Never store credentials or raw protocol payloads in status receipts.
            with contextlib.suppress(Exception):
                state_path = RUNTIME / "supervisor-state.json"
                state = json.loads(state_path.read_text()) if state_path.exists() else {}
                state.update(reason="check_failed", error=type(error).__name__,
                             not_before_epoch=time.time() + 900)
                save(state)
            raise


if __name__ == "__main__":
    main()
