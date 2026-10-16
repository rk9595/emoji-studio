"""Offline single-worker lease contract; not yet wired into the public API.

All state and bounded output blobs commit in one local SQLite database. This
survives process restarts, not disk loss. Only trusted control-plane code calls
these methods; a lease token is not a substitute for remote worker authentication.
"""

import hashlib
import json
import math
import os
import re
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z")
MAX_OUTPUT_BYTES = 64 * 1024 * 1024


class LeaseLost(ValueError):
    """Expired, superseded, or otherwise invalid worker authority."""


class Conflict(ValueError):
    """An idempotency key was reused with different content."""


@dataclass(frozen=True)
class Lease:
    job_id: str
    worker_id: str
    attempt: int
    expires_at: float
    payload: dict
    token: str = field(repr=False)


def _identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid identifier")


def _integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError("Integer outside allowed range")


class WorkerQueue:
    def __init__(self, path, *, clock=time.time):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.clock = clock
        # New databases contain private prompts and fencing tokens. Existing
        # file permissions belong to the operator and are not silently changed.
        try:
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(descriptor)
        with self._transaction() as connection:
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                worker TEXT, token TEXT, expires REAL, error TEXT,
                created REAL NOT NULL, updated REAL NOT NULL
            )""")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_running_job
                ON jobs(status) WHERE status = 'running'""")
            connection.execute("""CREATE TABLE IF NOT EXISTS artifacts (
                job_id TEXT NOT NULL REFERENCES jobs(id), name TEXT NOT NULL,
                sha256 TEXT NOT NULL, content BLOB NOT NULL,
                PRIMARY KEY(job_id, name)
            )""")

    @contextmanager
    def _transaction(self):
        connection = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA synchronous = FULL")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _now(self):
        value = float(self.clock())
        if not math.isfinite(value) or value < 0:
            raise ValueError("Invalid control-plane clock")
        return value

    def enqueue(self, job_id, owner_id, prompts, seeds, *, max_attempts=3):
        """Idempotent admission of an already quota-approved logical job."""
        _identifier(job_id)
        _identifier(owner_id)
        _integer(max_attempts, 1, 10)
        if (
            not isinstance(prompts, list)
            or not isinstance(seeds, list)
            or not 1 <= len(prompts) <= 16
            or len(prompts) != len(seeds)
            or any(not isinstance(p, str) or not p.strip() or len(p) > 500 for p in prompts)
        ):
            raise ValueError("Invalid prompts or seeds")
        for seed in seeds:
            _integer(seed, 0, 2**32 - 1)
        payload = json.dumps({"prompts": prompts, "seeds": seeds}, sort_keys=True)
        with self._transaction() as connection:
            existing = connection.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            if existing:
                if (existing["owner"], existing["payload"], existing["max_attempts"]) != (
                    owner_id,
                    payload,
                    max_attempts,
                ):
                    raise Conflict("Job ID already belongs to a different admission")
                return job_id
            now = self._now()
            connection.execute(
                """INSERT INTO jobs
                (id,owner,payload,status,max_attempts,created,updated)
                VALUES (?,?,?,'queued',?,?,?)""",
                (job_id, owner_id, payload, max_attempts, now, now),
            )
        return job_id

    @staticmethod
    def _recover(connection, now):
        return connection.execute(
            """UPDATE jobs SET
            status=CASE WHEN attempt < max_attempts THEN 'queued' ELSE 'failed' END,
            token=NULL, worker=NULL, expires=NULL, error='Worker lease expired', updated=?
            WHERE status='running' AND expires<=?""",
            (now, now),
        ).rowcount

    def recover(self):
        """Requeue expired work (or fail it at its bounded attempt limit)."""
        with self._transaction() as connection:
            return self._recover(connection, self._now())

    def claim(self, worker_id, *, ttl=60):
        _identifier(worker_id)
        _integer(ttl, 1, 3600)
        with self._transaction() as connection:
            now = self._now()
            self._recover(connection, now)
            if connection.execute("SELECT 1 FROM jobs WHERE status='running'").fetchone():
                return None
            row = connection.execute("""SELECT * FROM jobs WHERE status='queued'
                ORDER BY created,id LIMIT 1""").fetchone()
            if row is None:
                return None
            token = uuid.uuid4().hex
            attempt, expires = row["attempt"] + 1, now + ttl
            connection.execute(
                """UPDATE jobs SET status='running',attempt=?,worker=?,token=?,
                expires=?,error=NULL,updated=? WHERE id=?""",
                (attempt, worker_id, token, expires, now, row["id"]),
            )
            return Lease(row["id"], worker_id, attempt, expires, json.loads(row["payload"]), token)

    @staticmethod
    def _owned_lease(connection, lease):
        row = connection.execute("SELECT * FROM jobs WHERE id=?", (lease.job_id,)).fetchone()
        if row is None or (row["token"], row["worker"], row["attempt"]) != (
            lease.token,
            lease.worker_id,
            lease.attempt,
        ):
            raise LeaseLost("Worker lease no longer owns this job")
        return row

    @staticmethod
    def _active(row, now):
        if row["status"] != "running" or row["expires"] <= now:
            raise LeaseLost("Worker lease is not active")

    def heartbeat(self, lease, *, ttl=60):
        _integer(ttl, 1, 3600)
        with self._transaction() as connection:
            now = self._now()
            row = self._owned_lease(connection, lease)
            self._active(row, now)
            expires = max(row["expires"], now + ttl)
            connection.execute(
                "UPDATE jobs SET expires=?,updated=? WHERE id=?", (expires, now, lease.job_id)
            )
            return expires

    def fail(self, lease, *, retryable=False, error="Worker failed"):
        if type(retryable) is not bool or not isinstance(error, str) or len(error) > 500:
            raise ValueError("Invalid failure details; use a bounded, non-secret diagnostic")
        with self._transaction() as connection:
            now = self._now()
            row = self._owned_lease(connection, lease)
            self._active(row, now)
            status = "queued" if retryable and row["attempt"] < row["max_attempts"] else "failed"
            connection.execute(
                """UPDATE jobs SET status=?,error=?,token=NULL,worker=NULL,
                expires=NULL,updated=? WHERE id=?""",
                (status, error, now, lease.job_id),
            )
            return status

    @staticmethod
    def _manifest(connection, job_id):
        return {
            row["name"]: row["sha256"]
            for row in connection.execute(
                "SELECT name,sha256 FROM artifacts WHERE job_id=? ORDER BY name", (job_id,)
            )
        }

    def complete(self, lease, outputs, expected_hashes):
        """Commit a full PNG/WebP pack atomically; identical retries are safe.

        Hashes establish byte integrity, not image validity or visual quality.
        Actual image/metadata validation belongs at the worker transport boundary.
        """
        if not isinstance(outputs, dict) or not isinstance(expected_hashes, dict):
            raise ValueError("Outputs and hashes must be mappings")
        if (
            not outputs
            or len(outputs) > 32
            or set(outputs) != set(expected_hashes)
            or any(type(value) is not bytes or not value for value in outputs.values())
        ):
            raise ValueError("Invalid output pack")
        if sum(len(value) for value in outputs.values()) > MAX_OUTPUT_BYTES:
            raise ValueError("Output pack exceeds byte limit")
        manifest = {name: hashlib.sha256(value).hexdigest() for name, value in outputs.items()}
        if manifest != expected_hashes:
            raise ValueError("Output checksum mismatch")
        with self._transaction() as connection:
            row = self._owned_lease(connection, lease)
            payload = json.loads(row["payload"])
            names = {
                f"{index:02d}-{seed}.{extension}"
                for index, seed in enumerate(payload["seeds"])
                for extension in ("png", "webp")
            }
            if set(outputs) != names:
                raise ValueError("Output pack does not match admitted seeds and formats")
            if row["status"] == "succeeded":
                if self._manifest(connection, lease.job_id) != manifest:
                    raise Conflict("Completed job cannot be overwritten")
                return manifest
            now = self._now()
            self._active(row, now)
            connection.executemany(
                "INSERT INTO artifacts(job_id,name,sha256,content) VALUES(?,?,?,?)",
                [(lease.job_id, name, manifest[name], value) for name, value in outputs.items()],
            )
            connection.execute(
                "UPDATE jobs SET status='succeeded',expires=NULL,updated=? WHERE id=?",
                (now, lease.job_id),
            )
        return manifest

    def get(self, job_id, owner_id):
        """Owner-scoped public state. Never expose worker lease credentials."""
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT * FROM jobs WHERE id=? AND owner=?", (job_id, owner_id)
            ).fetchone()
            if row is None:
                return None
            return {
                "id": row["id"],
                "status": row["status"],
                "attempt": row["attempt"],
                "payload": json.loads(row["payload"]),
                "error": row["error"],
                "artifacts": self._manifest(connection, job_id),
            }

    def artifact(self, job_id, owner_id, name):
        with self._transaction() as connection:
            row = connection.execute(
                """SELECT a.content,a.sha256 FROM artifacts a
                JOIN jobs j ON j.id=a.job_id
                WHERE j.id=? AND j.owner=? AND j.status='succeeded' AND a.name=?""",
                (job_id, owner_id, name),
            ).fetchone()
            if row is None:
                return None
            content = bytes(row["content"])
            if hashlib.sha256(content).hexdigest() != row["sha256"]:
                raise ValueError("Stored artifact checksum mismatch")
            return content
