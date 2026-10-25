"""Offline smoke cleanup contract. No credentials, network adapter or scheduler.

A trusted future controller must durably register the exact allocation with an
independent service before rendering. This module does not authorize allocation.
"""

import fcntl
import json
import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from typing import Protocol

from emoji_studio.render_budget import checked_path, checksum, identifier

CAMPAIGN = "amd-api-smoke-v1"


class CleanupDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class Binding:
    provider: str
    account_id: str
    allocation_id: str
    resource_id: str
    plan_sha256: str
    created_epoch: int
    campaign: str = CAMPAIGN

    def __post_init__(self):
        if self.provider != "amd-devcloud" or self.campaign != CAMPAIGN:
            raise ValueError("Only the separate AMD API smoke is supported")
        identifier(self.account_id)
        checksum(self.plan_sha256)
        if not isinstance(self.allocation_id, str) or not re.fullmatch(
            r"[0-9a-f]{32}", self.allocation_id
        ):
            raise ValueError("Expected fresh allocation nonce")
        if not isinstance(self.resource_id, str) or not re.fullmatch(
            r"[1-9][0-9]{0,19}", self.resource_id
        ):
            raise ValueError("Expected exact numeric resource ID")
        if type(self.created_epoch) is not int or self.created_epoch <= 0:
            raise ValueError("Expected provider creation time in UTC seconds")

    @property
    def stop_epoch(self):
        return self.created_epoch + 1500

    @property
    def deadline_epoch(self):
        return self.created_epoch + 1800

    @property
    def name(self):
        return f"{CAMPAIGN}-{self.allocation_id}"

    @property
    def tags(self):
        return (CAMPAIGN, f"allocation-{self.allocation_id}", f"plan-{self.plan_sha256}")

    def encoded(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class Lookup:
    """Normalized exact-ID response; only an authenticated exact GET may yield 404.

    A future adapter must not map exceptions, list misses, redirects, permission
    failures or DELETE acknowledgments to absence. Resource timestamps must be
    normalized without rounding. This is an internal contract, not provider JSON.
    """

    status: int
    resource: dict | None = None


class Provider(Protocol):
    provider: str
    account_id: str

    def lookup(self, resource_id: str) -> Lookup: ...

    def delete(self, resource_id: str) -> int: ...


def _owned(binding, response):
    if not isinstance(response, Lookup) or type(response.status) is not int:
        return False
    row = response.resource
    if response.status != 200 or not isinstance(row, dict):
        return False
    tags = row.get("tags")
    return (
        row.get("id") == binding.resource_id
        and row.get("name") == binding.name
        and type(row.get("created_epoch")) is int
        and row["created_epoch"] == binding.created_epoch
        and isinstance(tags, list)
        and all(isinstance(tag, str) for tag in tags)
        and set(binding.tags).issubset(tags)
    )


def _absent(response):
    return (isinstance(response, Lookup) and type(response.status) is int
            and response.status == 404 and response.resource is None)


class CleanupLedger:
    """One allocation, durable pending state, bounded reconciliation per tick.

    POSIX/trusted private local disk only. Independent replicas need a shared,
    conditional durable store, not copies of this SQLite file. No reset/rebind,
    provisioning, discovery, list-wide deletion, sleep or retry loop is provided.
    """

    def __init__(self, path, binding):
        self.path = checked_path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.binding = binding
        self.file_identity = self._file_identity()
        self.lock_identity = self._file_identity(self.lock_path)
        with self._locked() as db:
            self._read(db)

    @classmethod
    def create(cls, path, binding):
        path = checked_path(path)
        # Validate before leaving a new file; never replace any existing ledger.
        encoded = binding.encoded()
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        # A separate inode avoids flock/fcntl interactions with SQLite on macOS.
        lock_path = path.with_name(path.name + ".lock")
        descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE cleanup (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "binding TEXT NOT NULL, status TEXT NOT NULL, last_epoch INTEGER NOT NULL)")
            db.execute("CREATE TABLE receipts (sequence INTEGER PRIMARY KEY, "
                       "epoch INTEGER NOT NULL, outcome TEXT NOT NULL)")
            db.execute("INSERT INTO cleanup VALUES(1,?,'watching',?)",
                       (encoded, binding.created_epoch))
            db.execute("PRAGMA user_version=1")
            db.commit()
        finally:
            db.close()
        return cls(path, binding)

    def _file_identity(self, path=None):
        info = checked_path(self.path if path is None else path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise CleanupDenied("private_regular_ledger_required")
        return info.st_dev, info.st_ino

    def _check_files(self):
        if (self._file_identity() != self.file_identity
                or self._file_identity(self.lock_path) != self.lock_identity):
            raise CleanupDenied("ledger_replaced")

    @contextmanager
    def _locked(self):
        self._check_files()
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
        db = None
        try:
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != self.lock_identity:
                raise CleanupDenied("ledger_replaced")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise CleanupDenied("reconciliation_busy") from error
            self._check_files()
            db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA synchronous=FULL")
            yield db
            self._check_files()
        finally:
            if db is not None:
                db.close()
            os.close(descriptor)

    def _read(self, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise CleanupDenied("unsupported_schema")
        rows = db.execute("SELECT * FROM cleanup").fetchall()
        if len(rows) != 1 or rows[0]["id"] != 1 or rows[0]["binding"] != self.binding.encoded():
            raise CleanupDenied("binding_mismatch")
        row = dict(rows[0])
        if (row["status"] not in ("watching", "pending_cleanup", "complete")
                or type(row["last_epoch"]) is not int
                or row["last_epoch"] < self.binding.created_epoch):
            raise CleanupDenied("invalid_state")
        receipts = [dict(r) for r in db.execute("SELECT * FROM receipts ORDER BY sequence")]
        if row["status"] == "complete" and (
            not receipts or receipts[-1]["outcome"] != "exact_get_absent"
        ):
            raise CleanupDenied("missing_absence_receipt")
        return {"binding": asdict(self.binding), "status": row["status"],
                "last_epoch": row["last_epoch"], "stop_epoch": self.binding.stop_epoch,
                "deadline_epoch": self.binding.deadline_epoch,
                "deadline_exceeded": row["last_epoch"] >= self.binding.deadline_epoch
                and row["status"] != "complete", "receipts": receipts}

    def snapshot(self):
        with self._locked() as db:
            return self._read(db)

    def _record(self, db, now, outcome, *, complete=False):
        self._check_files()
        db.execute("UPDATE cleanup SET status=?, last_epoch=? WHERE id=1",
                   ("complete" if complete else "pending_cleanup", now))
        db.execute("INSERT INTO receipts(epoch,outcome) VALUES(?,?)", (now, outcome))
        db.commit()

    def reconcile(self, provider: Provider, *, now: int, reason=None):
        """One tick from an independent clock, or early terminal-work cleanup.

        At most two exact lookups and one DELETE; all exceptions are sanitized.
        Crash/commit failure leaves pending, and next tick rechecks identity.
        No provider success status other than a separate GET 404 completes cleanup.
        """
        if type(now) is not int or now < self.binding.created_epoch:
            raise ValueError("Invalid independent clock")
        if reason not in (None, "work_complete", "work_failed"):
            raise ValueError("Invalid cleanup trigger")
        with self._locked() as db:
            state = self._read(db)
            if state["status"] == "complete":
                return state
            # Persist a clock watermark: a later clock rollback cannot revive work.
            now = max(now, state["last_epoch"])
            if state["status"] == "watching" and now < self.binding.stop_epoch and reason is None:
                db.execute("UPDATE cleanup SET last_epoch=? WHERE id=1", (now,))
                db.commit()
                return self._read(db)
            # Commit intent BEFORE any provider call. A dead controller cannot
            # lose pending cleanup merely because it failed before a response.
            self._record(db, now, "reconciliation_started")
            if (provider.provider, provider.account_id) != (
                self.binding.provider, self.binding.account_id
            ):
                self._record(db, now, "provider_scope_mismatch")
                return self._read(db)
            try:
                before = provider.lookup(self.binding.resource_id)
            except Exception:
                self._record(db, now, "lookup_error")
                return self._read(db)
            if _absent(before):
                self._record(db, now, "exact_get_absent", complete=True)
                return self._read(db)
            if not _owned(self.binding, before):
                self._record(db, now, "lookup_unverified_or_identity_mismatch")
                return self._read(db)
            # Durable intent also survives abrupt death during DELETE or its ack.
            self._record(db, now, "delete_requested")
            try:
                status = provider.delete(self.binding.resource_id)
                outcome = "delete_acknowledged" if type(status) is int and status in (
                    200, 202, 204
                ) else "delete_unconfirmed"
            except Exception:
                outcome = "delete_error"
            self._record(db, now, outcome)
            try:
                after = provider.lookup(self.binding.resource_id)
            except Exception:
                self._record(db, now, "verification_error")
                return self._read(db)
            absent = _absent(after)
            self._record(db, now, "exact_get_absent" if absent else "absence_unverified",
                         complete=absent)
            return self._read(db)
