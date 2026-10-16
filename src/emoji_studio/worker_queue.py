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


class QuotaExceeded(ValueError):
    def __init__(self, scope, used, limit, *, resets_at=None):
        super().__init__(f"{scope} image quota exceeded; {max(0, limit - used)} remaining")
        self.scope = scope
        self.used = used
        self.limit = limit
        self.resets_at = resets_at


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
    def __init__(self, path, *, clock=time.time, trial_image_cap=None):
        if trial_image_cap is not None:
            _integer(trial_image_cap, 1, 100_000)
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
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if version not in (0, 2):
                raise ValueError("Unsupported worker queue schema")
            if (
                version == 2
                and not {"jobs", "artifacts", "usage_ledger", "queue_settings"} <= tables
            ):
                raise ValueError(
                    "Incomplete worker queue schema; restore instead of resetting usage"
                )
            if version == 0 and tables:
                raise ValueError(
                    "Legacy or unversioned database requires an explicit usage-ledger migration"
                )
            connection.execute("""CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('queued','running','succeeded','failed')),
                attempt INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
                worker TEXT, token TEXT, expires REAL, error TEXT,
                created REAL NOT NULL, updated REAL NOT NULL,
                FOREIGN KEY(id) REFERENCES usage_ledger(job_id)
            )""")
            connection.execute("""CREATE UNIQUE INDEX IF NOT EXISTS one_running_job
                ON jobs(status) WHERE status = 'running'""")
            connection.execute("""CREATE TABLE IF NOT EXISTS artifacts (
                job_id TEXT NOT NULL REFERENCES jobs(id), name TEXT NOT NULL,
                sha256 TEXT NOT NULL, content BLOB NOT NULL,
                PRIMARY KEY(job_id, name)
            )""")
            connection.execute("""CREATE TABLE IF NOT EXISTS usage_ledger (
                job_id TEXT PRIMARY KEY, owner TEXT NOT NULL, payload_sha256 TEXT NOT NULL,
                max_attempts INTEGER NOT NULL, images INTEGER NOT NULL CHECK(images BETWEEN 1 AND 16),
                admitted REAL NOT NULL
            )""")
            connection.execute("""CREATE INDEX IF NOT EXISTS usage_by_owner_day
                ON usage_ledger(owner,admitted)""")
            connection.execute("""CREATE TABLE IF NOT EXISTS queue_settings (
                id INTEGER PRIMARY KEY CHECK(id=1),
                trial_image_cap INTEGER NOT NULL CHECK(trial_image_cap BETWEEN 1 AND 100000)
            )""")
            if connection.execute("PRAGMA foreign_key_check").fetchone():
                raise ValueError("Inconsistent job/artifact/usage references; restore required")
            settings = connection.execute(
                "SELECT trial_image_cap FROM queue_settings WHERE id=1"
            ).fetchone()
            if settings is None:
                if version == 2:
                    raise ValueError("Missing persisted trial policy; refusing to reset")
                connection.execute(
                    "INSERT INTO queue_settings VALUES(1,?)",
                    (trial_image_cap if trial_image_cap is not None else 100,),
                )
            elif trial_image_cap is not None and trial_image_cap != settings[0]:
                raise Conflict(
                    "Trial cap differs from persisted policy; explicit policy change required"
                )
            connection.execute("PRAGMA user_version = 2")

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

    def enqueue(self, job_id, owner_id, prompts, seeds, *, max_attempts=3, daily_image_quota=1000):
        """Atomically admit a logical job and reserve daily/lifetime image usage.

        Limits come from trusted control-plane policy, never a worker or client.
        Idempotent resubmission does not charge twice; deleted IDs cannot be reused.
        """
        _identifier(job_id)
        _identifier(owner_id)
        _integer(max_attempts, 1, 10)
        _integer(daily_image_quota, 1, 1000)
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
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        with self._transaction() as connection:
            existing = connection.execute(
                "SELECT * FROM usage_ledger WHERE job_id=?", (job_id,)
            ).fetchone()
            if existing:
                if (existing["owner"], existing["payload_sha256"], existing["max_attempts"]) != (
                    owner_id,
                    payload_hash,
                    max_attempts,
                ):
                    raise Conflict("Job ID already belongs to a different admission")
                if not connection.execute("SELECT 1 FROM jobs WHERE id=?", (job_id,)).fetchone():
                    raise Conflict("Deleted job ID cannot be reused")
                return job_id
            now = self._now()
            usage = self._usage(connection, owner_id, daily_image_quota, now)
            for scope in ("daily", "trial"):
                quota = usage[scope]
                if len(seeds) > quota["remaining"]:
                    raise QuotaExceeded(
                        scope, quota["used"], quota["limit"], resets_at=quota.get("resets_at")
                    )
            connection.execute(
                "INSERT INTO usage_ledger VALUES(?,?,?,?,?,?)",
                (job_id, owner_id, payload_hash, max_attempts, len(seeds), now),
            )
            connection.execute(
                """INSERT INTO jobs
                (id,owner,payload,status,max_attempts,created,updated)
                VALUES (?,?,?,'queued',?,?,?)""",
                (job_id, owner_id, payload, max_attempts, now, now),
            )
        return job_id

    @staticmethod
    def _usage(connection, owner_id, daily_image_quota, now):
        midnight = now // 86400 * 86400
        total, latest = connection.execute(
            "SELECT COALESCE(SUM(images),0),MAX(admitted) FROM usage_ledger"
        ).fetchone()
        if latest is not None and now < latest:
            raise ValueError("Control-plane clock predates admitted usage; refusing quota reset")
        daily = connection.execute(
            """SELECT COALESCE(SUM(images),0) FROM usage_ledger
            WHERE owner=? AND admitted>=? AND admitted<?""",
            (owner_id, midnight, midnight + 86400),
        ).fetchone()[0]
        trial = connection.execute(
            "SELECT trial_image_cap FROM queue_settings WHERE id=1"
        ).fetchone()[0]
        return {
            "daily": {
                "used": daily,
                "limit": daily_image_quota,
                "remaining": max(0, daily_image_quota - daily),
                "resets_at": midnight + 86400,
            },
            "trial": {"used": total, "limit": trial, "remaining": max(0, trial - total)},
        }

    def usage(self, owner_id, *, daily_image_quota=1000):
        _identifier(owner_id)
        _integer(daily_image_quota, 1, 1000)
        with self._transaction() as connection:
            return self._usage(connection, owner_id, daily_image_quota, self._now())

    def delete(self, job_id, owner_id):
        """Remove terminal content, preserving minimal accounting and ID tombstone.

        This is logical deletion, not secure erasure of SQLite pages or backups.
        No background deletion is installed.
        """
        with self._transaction() as connection:
            row = connection.execute(
                "SELECT status FROM jobs WHERE id=? AND owner=?", (job_id, owner_id)
            ).fetchone()
            if row is None:
                return False
            if row["status"] not in ("succeeded", "failed"):
                raise Conflict("Only terminal job content can be deleted")
            connection.execute("DELETE FROM artifacts WHERE job_id=?", (job_id,))
            connection.execute("DELETE FROM jobs WHERE id=?", (job_id,))
            return True

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
