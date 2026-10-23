"""Disposable, POSIX-only real HTTP smoke. Never provisions or uses a GPU.

Run with ``python -m emoji_studio.smoke_http``. No endpoint/database override:
all listeners are loopback, all data temporary, and all tokens ephemeral.
"""

import hashlib
import http.client
import io
import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import urlsplit

from PIL import Image


class SmokeFailure(RuntimeError):
    """Bounded, non-secret diagnostic suitable for a CI log."""


def require(condition, label):
    if not condition:
        raise SmokeFailure(label)


def local_path(path):
    """Never send an auth token to a response-supplied origin or redirect."""
    parts = urlsplit(path)
    if (
        not path.startswith("/") or path.startswith("//")
        or parts.scheme or parts.netloc or parts.fragment
        or "\\" in path or any(ord(char) < 33 for char in path)
    ):
        raise SmokeFailure("Non-local HTTP path rejected")
    return path


class LocalClient:
    def __init__(self, port, tokens, deadline):
        self.port, self.tokens, self.deadline = port, tokens, deadline

    def remaining(self):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise SmokeFailure("Smoke deadline exceeded")
        return min(2, remaining)

    def request(self, method, path, *, user="alice", payload=None, status=200, raw=False):
        path = local_path(path)
        headers = {"X-Request-ID": "local-http-smoke"}
        if user is not None:
            headers["Authorization"] = "Bearer " + self.tokens[user]
        data = None if payload is None else json.dumps(payload).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=self.remaining())
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            # No redirects/proxies; a bounded read also bounds unexpected output.
            content = response.read(4 * 1024 * 1024 + 1)
            require(len(content) <= 4 * 1024 * 1024, "HTTP response too large")
            require(response.status == status, f"HTTP status mismatch: {method} expected {status}")
            require(response.getheader("X-Request-ID") == "local-http-smoke", "Request ID lost")
            if raw:
                return content, response.getheader("Content-Type")
            return json.loads(content) if content else None
        finally:
            connection.close()

    def wait(self, path):
        while True:
            job = self.request("GET", path)
            require(job["status"] != "failed", "Mock rendering failed")
            if job["status"] == "succeeded":
                return job
            time.sleep(min(0.03, self.remaining()))


def stop_child(process):
    """Reap only the child created by this runner, including on failed checks."""
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)


@contextmanager
def server(database, tokens, deadline, *, worker_enabled):
    # Inherit an already-bound socket: no port-selection race or public bind.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(16)
        port = listener.getsockname()[1]
        command = [
            sys.executable, "-m", "emoji_studio.smoke_http", "--child",
            str(listener.fileno()), str(database), str(int(worker_enabled)),
        ]
        process = subprocess.Popen(
            command, pass_fds=(listener.fileno(),), stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        try:
            # Send only token hashes through a pipe, never argv, files or logs.
            hashes = {name: hashlib.sha256(token.encode()).hexdigest()
                      for name, token in tokens.items()}
            process.stdin.write(json.dumps(hashes).encode())
            process.stdin.close()
            client = LocalClient(port, tokens, deadline)
            startup_deadline = min(deadline, time.monotonic() + 10)
            while True:
                require(process.poll() is None, "Local API child exited during startup")
                require(time.monotonic() < startup_deadline, "Local API startup timed out")
                try:
                    health = client.request("GET", "/healthz", user=None)
                    require(health["status"] == "ok", "Local API health degraded")
                    require(health["renderer"] == "MockRenderer", "Unexpected renderer")
                    require(health["worker_enabled"] == worker_enabled, "Unexpected worker mode")
                    break
                except (OSError, http.client.HTTPException):
                    time.sleep(min(0.03, client.remaining()))
            yield client
        finally:
            if not process.stdin.closed:
                process.stdin.close()
            stop_child(process)


def child_main(fd, database, enabled):
    # Independent of the parent: an interrupted runner cannot leave this mock
    # listener alive indefinitely. This is not a GPU/provider billing watchdog.
    watchdog = threading.Timer(60, os._exit, args=(124,))
    watchdog.daemon = True
    watchdog.start()
    import uvicorn

    from .alpha import AccessPolicy, AlphaUser
    from .durable_api import create_app
    from .service import MockRenderer

    hashes = json.loads(sys.stdin.buffer.read(4096))
    users = [AlphaUser(name, digest, 2 if name == "alice" else 4, 120, name == "admin")
             for name, digest in hashes.items()]
    with socket.socket(fileno=int(fd)) as listener:
        require(listener.getsockname()[0] == "127.0.0.1", "Non-loopback socket rejected")
        app = create_app(
            database, renderer=MockRenderer(), access_policy=AccessPolicy(users),
            trial_image_cap=2, worker_enabled=enabled == "1", poll_seconds=0.02,
        )
        config = uvicorn.Config(app, log_level="critical", access_log=False,
                                timeout_graceful_shutdown=2)
        uvicorn.Server(config).run(sockets=[listener])


def exports(client, job):
    hashes = {}
    for index, result in enumerate(job["results"]):
        for extension in ("png", "webp"):
            content, mime = client.request("GET", result[f"{extension}_url"], raw=True)
            require(mime == f"image/{extension}", "Wrong export content type")
            with Image.open(io.BytesIO(content)) as image:
                image.load()
                require(image.format == extension.upper(), "Wrong export format")
                require(image.mode == "RGBA" and image.size == (512, 512), "Invalid sticker")
                require(image.getextrema()[3][0] == 0, "Missing transparency")
            hashes[f"{index}.{extension}"] = hashlib.sha256(content).hexdigest()
    require(bool(hashes), "Missing exports")
    return hashes


def run_smoke():
    started = time.monotonic()
    deadline = started + 45
    tokens = {name: secrets.token_urlsafe(32) for name in ("alice", "bob", "admin")}
    checks = []
    payload = {"prompt": "a cheerful red apple sticker", "seed": 7}
    with tempfile.TemporaryDirectory(prefix="emoji-http-smoke-") as temporary:
        database = Path(temporary) / "jobs.sqlite3"
        with server(database, tokens, deadline, worker_enabled=False) as client:
            client.request("GET", "/v1/me", user=None, status=401)
            client.request("POST", "/v1/generations", user=None, payload=payload, status=401)
            client.request("GET", "/metrics", status=403)
            client.request("GET", "/metrics", user="admin", raw=True)
            checks.append("auth_and_admin")
            queued = client.request("POST", "/v1/generations", payload=payload, status=202)
            require(queued["status"] == "queued", "Disabled worker processed job")
            path = "/v1/generations/" + queued["id"]
            client.request("DELETE", path, status=409)
            checks.append("queued_admission")
        with server(database, tokens, deadline, worker_enabled=True) as client:
            job = client.wait(path)
            require(job["seeds"] == [7], "Seed changed")
            require(job["request_id"] == "local-http-smoke", "Stored request ID lost")
            first_hashes = exports(client, job)
            checks.extend(["queued_process_restart", "png_webp_transparency"])
            client.request("GET", path, user="bob", status=404)
            client.request("GET", job["results"][0]["png_url"], user="bob", status=404)
            require(client.request("GET", "/v1/generations", user="bob") == {"jobs": []},
                    "History ownership failure")
            checks.append("owner_isolation")
            second = client.request("POST", "/v1/generations", payload=payload, status=202)
            second_path = "/v1/generations/" + second["id"]
            require(exports(client, client.wait(second_path)) == first_hashes,
                    "Seeded exports are not deterministic")
            checks.append("deterministic_exports")
            feedback = client.request("POST", path + "/feedback", status=201,
                                      payload={"rating": "up", "comment": " smoke "})
            require(feedback["comment"] == "smoke", "Feedback failed")
            client.request("POST", "/v1/generations", payload=payload, status=429)
            client.request("POST", "/v1/generations", user="bob", payload=payload, status=429)
            checks.extend(["feedback", "daily_and_trial_quotas"])
        with server(database, tokens, deadline, worker_enabled=True) as client:
            persisted = client.request("GET", path)
            require(persisted == job, "Completed job changed on restart")
            require(exports(client, persisted) == first_hashes, "Export changed on restart")
            history = client.request("GET", "/v1/generations")["jobs"]
            require({row["id"] for row in history} == {job["id"], second["id"]},
                    "History did not survive restart")
            checks.append("completed_process_restart")
            client.request("DELETE", path, user="bob", status=404)
            client.request("DELETE", path, status=204)
            client.request("GET", path, status=404)
            client.request("GET", job["results"][0]["png_url"], status=404)
            usage = client.request("GET", "/v1/me")
            require(usage["quota"]["used"] == 2 and usage["trial"]["used"] == 2,
                    "Deletion refunded usage")
            client.request("POST", "/v1/generations", payload=payload, status=429)
            checks.append("deletion_preserves_usage")
    checks.append("children_reaped_and_temporary_data_removed")
    source_dir = Path(__file__).parent
    return {
        "status": "passed", "renderer": "MockRenderer", "bind": "127.0.0.1",
        "images_admitted": 2, "gpu_allocations": 0, "process_starts": 3,
        "elapsed_seconds": round(time.monotonic() - started, 3), "checks": checks,
        "source_sha256": {name: hashlib.sha256((source_dir / name).read_bytes()).hexdigest()
                          for name in ("smoke_http.py", "durable_api.py", "durable_worker.py",
                                       "worker_queue.py", "service.py", "alpha.py", "api.py")},
    }


def main():
    if len(sys.argv) == 5 and sys.argv[1] == "--child":
        child_main(*sys.argv[2:])
    elif len(sys.argv) == 1:
        try:
            print(json.dumps(run_smoke(), indent=2, sort_keys=True))
        except Exception as error:
            # No response bodies, credentials, arbitrary exception text or private paths.
            print(json.dumps({"status": "failed", "error_type": type(error).__name__}))
            raise SystemExit(1) from None
    else:
        raise SystemExit("Usage: python -m emoji_studio.smoke_http")


if __name__ == "__main__":
    main()
