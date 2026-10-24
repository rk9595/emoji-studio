"""Local two-call smoke ledger. No GPU imports, provider calls or spend authority."""

import os
import re
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path

CAMPAIGN = "amd-api-smoke-v1"
LIMIT = 2
IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\Z")
HASH = re.compile(r"[0-9a-f]{64}\Z")


class BudgetDenied(RuntimeError):
    """The durable ledger cannot permit another invocation."""


def identifier(value):
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        raise ValueError("Invalid non-secret identifier")


def checksum(value):
    if not isinstance(value, str) or not HASH.fullmatch(value):
        raise ValueError("Expected SHA-256 fingerprint")


def checked_path(path):
    path = Path(os.path.abspath(path))
    if any(part.is_symlink() for part in (path, *path.parents)):
        raise BudgetDenied("symlink_path")
    return path


class RenderBudget:
    """Count guarded invocations, not API admissions; no resets or refunds.

    run() must wrap exactly one physical render. Trusted executor code must use
    this sole ledger for its allocation and must not retry inside the callback.
    This is not protection from an operator replacing the disk/database or code.
    """

    def __init__(self, path, *, allocation_id, plan_sha256, campaign=CAMPAIGN):
        identifier(allocation_id)
        checksum(plan_sha256)
        if campaign != CAMPAIGN:
            raise ValueError("Only the separate API smoke campaign is supported")
        self.path = checked_path(path)
        self.identity = (campaign, allocation_id, plan_sha256, LIMIT)
        self.file_identity = self._file_identity()
        with self._transaction() as connection:
            self._validated(connection)

    @classmethod
    def create(cls, path, *, allocation_id, plan_sha256, campaign=CAMPAIGN):
        """Explicit fresh initialization; refuses every existing path.

        Parent directory must exist and be private/trusted. Failure leaves the
        file for inspection, never deletes/recreates it or clears prior usage.
        Creation is not evidence of cloud or spending authorization.
        """
        identifier(allocation_id)
        checksum(plan_sha256)
        if campaign != CAMPAIGN:
            raise ValueError("Only the separate API smoke campaign is supported")
        path = checked_path(path)
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, isolation_level=None)
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("""CREATE TABLE budget (
                id INTEGER PRIMARY KEY CHECK(id=1), campaign TEXT NOT NULL,
                allocation_id TEXT NOT NULL, plan_sha256 TEXT NOT NULL,
                max_calls INTEGER NOT NULL CHECK(max_calls=2),
                used INTEGER NOT NULL CHECK(used BETWEEN 0 AND 2)
            )""")
            connection.execute("""CREATE TABLE calls (
                sequence INTEGER PRIMARY KEY CHECK(sequence BETWEEN 1 AND 2),
                call_id TEXT NOT NULL UNIQUE, request_sha256 TEXT NOT NULL,
                state TEXT NOT NULL CHECK(state IN ('reserved','succeeded','failed'))
            )""")
            connection.execute("INSERT INTO budget VALUES(1,?,?,?,?,0)",
                               (campaign, allocation_id, plan_sha256, LIMIT))
            connection.execute("PRAGMA user_version=1")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()
        return cls(path, allocation_id=allocation_id, plan_sha256=plan_sha256, campaign=campaign)

    def _file_identity(self):
        info = checked_path(self.path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise BudgetDenied("ledger_requires_private_regular_file")
        return info.st_dev, info.st_ino

    @contextmanager
    def _transaction(self):
        if self._file_identity() != self.file_identity:
            raise BudgetDenied("ledger_replaced")
        # rw never silently creates an empty ledger after loss or a bad path.
        connection = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True,
                                     timeout=5, isolation_level=None)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("BEGIN IMMEDIATE")
            if self._file_identity() != self.file_identity:
                raise BudgetDenied("ledger_replaced")
            yield connection
            if self._file_identity() != self.file_identity:
                raise BudgetDenied("ledger_replaced")
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _validated(self, connection):
        if connection.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise BudgetDenied("unsupported_ledger_schema")
        settings = connection.execute("SELECT * FROM budget").fetchall()
        if len(settings) != 1:
            raise BudgetDenied("missing_or_duplicate_policy")
        row = settings[0]
        if row["id"] != 1 or tuple(row[key] for key in (
            "campaign", "allocation_id", "plan_sha256", "max_calls",
        )) != self.identity:
            raise BudgetDenied("ledger_identity_mismatch")
        calls = connection.execute("SELECT * FROM calls ORDER BY sequence").fetchall()
        if row["used"] != len(calls) or not 0 <= row["used"] <= LIMIT:
            raise BudgetDenied("ledger_accounting_mismatch")
        if [call["sequence"] for call in calls] != list(range(1, len(calls) + 1)):
            raise BudgetDenied("ledger_sequence_mismatch")
        for call in calls:
            identifier(call["call_id"])
            checksum(call["request_sha256"])
            if call["state"] not in ("reserved", "succeeded", "failed"):
                raise BudgetDenied("ledger_state_mismatch")
        if any(call["state"] != "succeeded" for call in calls[:-1]):
            raise BudgetDenied("ledger_nonterminal_predecessor")
        return row["used"], calls

    def snapshot(self):
        with self._transaction() as connection:
            used, calls = self._validated(connection)
            stopped = any(call["state"] != "succeeded" for call in calls)
            return {"campaign": self.identity[0], "allocation_id": self.identity[1],
                    "plan_sha256": self.identity[2], "limit": LIMIT, "consumed": used,
                    "unused": LIMIT - used, "further_calls_blocked": stopped or used == LIMIT,
                    "calls": [dict(call) for call in calls]}

    def _reserve(self, call_id, request_sha256):
        with self._transaction() as connection:
            used, calls = self._validated(connection)
            if any(call["call_id"] == call_id for call in calls):
                raise BudgetDenied("call_already_consumed")
            if any(call["state"] != "succeeded" for call in calls):
                raise BudgetDenied("prior_call_unresolved_or_failed")
            if used == LIMIT:
                raise BudgetDenied("render_limit_reached")
            connection.execute("UPDATE budget SET used=used+1 WHERE id=1")
            connection.execute("INSERT INTO calls VALUES(?,?,?,'reserved')",
                               (used + 1, call_id, request_sha256))

    def _finish(self, call_id, request_sha256, state):
        with self._transaction() as connection:
            _, calls = self._validated(connection)
            if not calls or (calls[-1]["call_id"], calls[-1]["request_sha256"], calls[-1]["state"]) != (
                call_id, request_sha256, "reserved",
            ):
                raise BudgetDenied("reservation_changed")
            connection.execute("UPDATE calls SET state=? WHERE call_id=?", (state, call_id))

    def run(self, call_id, request_sha256, render):
        """Commit consumption, invoke once, then durably record returned success.

        Errors (including interruption) consume the call and stop further work.
        Abrupt death leaves 'reserved', also blocking all further calls. There is
        deliberately no TTL/reclaim/replay and no public reusable permit object.
        """
        identifier(call_id)
        checksum(request_sha256)
        if not callable(render):
            raise ValueError("A single-render callable is required")
        self._reserve(call_id, request_sha256)
        try:
            result = render()
        except BaseException:
            try:
                self._finish(call_id, request_sha256, "failed")
            except Exception:
                # An unrecorded failure leaves 'reserved', which also blocks.
                pass
            raise
        self._finish(call_id, request_sha256, "succeeded")
        return result
