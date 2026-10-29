"""Offline single-allocation reservation; no live adapter or execution authority."""

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
from emoji_studio.smoke_cleanup import CAMPAIGN, Binding, Lookup, _owned

TIMEOUT_SECONDS = 10


class ReservationDenied(RuntimeError):
    pass


@dataclass(frozen=True)
class Reservation:
    """Trusted controller assertions, not proof of approval or a cloud spend cap.

    Amounts are integer USD millionths. A future controller must validate the
    referenced approval and reserve in a single external authoritative store.
    Test fixtures use synthetic approvals; the active smoke plan is unauthorized.
    """

    account_id: str
    allocation_id: str
    plan_sha256: str
    request_sha256: str
    approval_sha256: str
    allowance_microusd: int
    reserve_microusd: int
    created_epoch: int
    expires_epoch: int
    provider: str = "amd-devcloud"
    campaign: str = CAMPAIGN

    def __post_init__(self):
        if self.provider != "amd-devcloud" or self.campaign != CAMPAIGN:
            raise ValueError("Only the separate AMD API smoke is supported")
        identifier(self.account_id)
        for value in (self.plan_sha256, self.request_sha256, self.approval_sha256):
            checksum(value)
        if not isinstance(self.allocation_id, str) or not re.fullmatch(r"[0-9a-f]{32}", self.allocation_id):
            raise ValueError("Expected fresh allocation nonce")
        if any(type(value) is not int or not 0 < value < 2**63 for value in (
            self.allowance_microusd, self.reserve_microusd, self.created_epoch, self.expires_epoch
        )):
            raise ValueError("Expected positive bounded integer amounts and times")
        if self.reserve_microusd > self.allowance_microusd:
            raise ValueError("Reservation exceeds supplied allowance")
        if not 0 < self.expires_epoch - self.created_epoch <= 1800:
            raise ValueError("Reservation validity must be at most 30 minutes")

    def encoded(self):
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))


class Provider(Protocol):
    """Future authenticated, fixed-account adapter; ten-second calls, no POST retry.

    discover returns at most two normalized candidates for the precise nonce and
    plan (two already means ambiguous). It must not return a first match from an
    incomplete scan as unique. Misses never prove no resource exists. lookup must
    be an exact-ID authenticated read and normalize ownership fields for _owned.
    """

    provider: str
    account_id: str

    def create(self, reservation: Reservation, *, timeout_seconds: int) -> Binding: ...
    def discover(self, reservation: Reservation, *, timeout_seconds: int) -> tuple[Binding, ...]: ...
    def lookup(self, resource_id: str, *, timeout_seconds: int) -> Lookup: ...


class AllocationLedger:
    """At most one create invocation per immutable local ledger, even after death.

    A committed unknown outcome consumes the sole attempt permanently. Discovery
    and exact reads can bind that attempt; they can never create a replacement.
    No reset, refund, allocation lease expiry or release operation exists.
    """

    def __init__(self, path, reservation):
        if type(reservation) is not Reservation:
            raise ValueError("Expected reservation")
        self.path = checked_path(path)
        self.lock_path = self.path.with_name(self.path.name + ".lock")
        self.reservation = reservation
        self.file_identity = self._identity(self.path)
        self.lock_identity = self._identity(self.lock_path)
        with self._locked() as db:
            self._read(db)

    @classmethod
    def create(cls, path, reservation):
        if type(reservation) is not Reservation:
            raise ValueError("Expected reservation")
        path = checked_path(path)
        for target in (path, path.with_name(path.name + ".lock")):
            descriptor = os.open(checked_path(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        db = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True)
        try:
            db.execute("PRAGMA synchronous=FULL")
            db.execute("CREATE TABLE allocation (id INTEGER PRIMARY KEY CHECK(id=1), "
                       "reservation TEXT NOT NULL, status TEXT NOT NULL, "
                       "last_epoch INTEGER NOT NULL, attempt_epoch INTEGER, candidate TEXT)")
            db.execute("CREATE TABLE receipts (sequence INTEGER PRIMARY KEY, "
                       "epoch INTEGER NOT NULL, outcome TEXT NOT NULL)")
            db.execute("INSERT INTO allocation VALUES(1,?,'reserved',?,NULL,NULL)",
                       (reservation.encoded(), reservation.created_epoch))
            db.execute("PRAGMA user_version=1")
            db.commit()
        finally:
            db.close()
        return cls(path, reservation)

    @staticmethod
    def _identity(path):
        info = checked_path(path).stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or stat.S_IMODE(info.st_mode) & 0o077:
            raise ReservationDenied("private_regular_ledger_required")
        return info.st_dev, info.st_ino

    def _check_files(self):
        if (self._identity(self.path) != self.file_identity
                or self._identity(self.lock_path) != self.lock_identity):
            raise ReservationDenied("ledger_replaced")

    @contextmanager
    def _locked(self):
        self._check_files()
        descriptor = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
        db = None
        try:
            info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != self.lock_identity:
                raise ReservationDenied("ledger_replaced")
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ReservationDenied("reservation_busy") from None
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

    def _matches(self, candidate, attempt_epoch, now):
        r = self.reservation
        return type(candidate) is Binding and (
            candidate.provider, candidate.account_id, candidate.campaign,
            candidate.allocation_id, candidate.plan_sha256
        ) == (r.provider, r.account_id, r.campaign, r.allocation_id, r.plan_sha256) and (
            attempt_epoch <= candidate.created_epoch <= now
        )

    def _read(self, db):
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            raise ReservationDenied("unsupported_schema")
        rows = db.execute("SELECT * FROM allocation").fetchall()
        if len(rows) != 1 or rows[0]["id"] != 1 or rows[0]["reservation"] != self.reservation.encoded():
            raise ReservationDenied("reservation_mismatch")
        row = dict(rows[0])
        if (row['status'] not in ('reserved', 'outcome_unknown', 'bound')
                or type(row['last_epoch']) is not int or row['last_epoch'] < self.reservation.created_epoch):
            raise ReservationDenied('invalid_state')
        consumed = row['status'] != 'reserved'
        attempt = row['attempt_epoch']
        if (consumed and (type(attempt) is not int or not self.reservation.created_epoch <= attempt
                         < self.reservation.expires_epoch or attempt > row['last_epoch'])) or (
            not consumed and (attempt is not None or row['candidate'] is not None)
        ):
            raise ReservationDenied('invalid_attempt')
        candidate = None
        if row['candidate'] is not None:
            try:
                candidate = Binding(**json.loads(row['candidate']))
                if not self._matches(candidate, attempt, row['last_epoch']):
                    raise ValueError()
            except Exception:
                raise ReservationDenied('invalid_candidate') from None
        receipts = [dict(r) for r in db.execute('SELECT * FROM receipts ORDER BY sequence')]
        if consumed and not any(r['outcome'] == 'create_intent_committed' for r in receipts):
            raise ReservationDenied('missing_intent')
        if row['status'] == 'bound' and (candidate is None or not receipts
                                       or receipts[-1]['outcome'] != 'exact_identity_verified'):
            raise ReservationDenied('missing_identity_receipt')
        return {'reservation': asdict(self.reservation), 'status': row['status'],
                'attempt_consumed': consumed, 'attempt_epoch': attempt,
                'last_epoch': row['last_epoch'], 'candidate': asdict(candidate) if candidate else None,
                'reserve_held_microusd': self.reservation.reserve_microusd,
                'rendering_authorized': False, 'receipts': receipts}

    def snapshot(self):
        with self._locked() as db:
            return self._read(db)

    def _record(self, db, now, outcome):
        self._check_files()
        db.execute('UPDATE allocation SET last_epoch=? WHERE id=1', (now,))
        db.execute('INSERT INTO receipts(epoch,outcome) VALUES(?,?)', (now, outcome))
        db.commit()

    def _clock(self, db, now):
        if type(now) is not int or not self.reservation.created_epoch <= now < 2**63:
            raise ValueError('Invalid controller clock')
        state = self._read(db)
        return state, max(now, state['last_epoch'])

    def _scope(self, provider):
        if (provider.provider, provider.account_id) != (self.reservation.provider, self.reservation.account_id):
            raise ReservationDenied('provider_scope_mismatch')

    def _verify(self, db, provider, clock):
        _, now = self._clock(db, clock())
        state = self._read(db)
        candidate = Binding(**state['candidate'])
        try:
            result = provider.lookup(candidate.resource_id, timeout_seconds=TIMEOUT_SECONDS)
        except Exception:
            self._record(db, now, 'exact_lookup_error')
            return self._read(db)
        _, now = self._clock(db, clock())
        if _owned(candidate, result):
            db.execute("UPDATE allocation SET status='bound' WHERE id=1")
            self._record(db, now, 'exact_identity_verified')
        else:
            self._record(db, now, 'exact_identity_unverified')
        return self._read(db)

    def _candidate(self, db, candidate, now):
        state = self._read(db)
        if not self._matches(candidate, state['attempt_epoch'], now):
            self._record(db, now, 'candidate_unverified')
            return False
        db.execute('UPDATE allocation SET candidate=? WHERE id=1', (candidate.encoded(),))
        self._record(db, now, 'candidate_retained')
        return True

    def run(self, provider: Provider, *, clock):
        """Consume once before CREATE. No success, failure or restart refunds it."""
        self._scope(provider)
        with self._locked() as db:
            state, now = self._clock(db, clock())
            if state['status'] != 'reserved':
                raise ReservationDenied('allocation_attempt_consumed')
            if now >= self.reservation.expires_epoch:
                self._record(db, now, 'reservation_expired')
                raise ReservationDenied('reservation_expired')
            db.execute("UPDATE allocation SET status='outcome_unknown', attempt_epoch=? WHERE id=1", (now,))
            self._record(db, now, 'create_intent_committed')
            # If the process dies here, outcome_unknown is already durable.
            try:
                candidate = provider.create(self.reservation, timeout_seconds=TIMEOUT_SECONDS)
            except Exception:
                self._record(db, now, 'create_error')
                return self._read(db)
            _, now = self._clock(db, clock())
            if self._candidate(db, candidate, now):
                return self._verify(db, provider, clock)
            return self._read(db)

    def reconcile(self, provider: Provider, *, clock):
        """At most one discovery + one exact GET; never CREATE or DELETE."""
        self._scope(provider)
        with self._locked() as db:
            state, now = self._clock(db, clock())
            if state['status'] == 'bound':
                return state
            if state['status'] == 'reserved':
                raise ReservationDenied('no_attempt_to_reconcile')
            self._record(db, now, 'reconciliation_started')
            if state['candidate'] is None:
                try:
                    candidates = provider.discover(self.reservation, timeout_seconds=TIMEOUT_SECONDS)
                except Exception:
                    self._record(db, now, 'discovery_error')
                    return self._read(db)
                _, now = self._clock(db, clock())
                if type(candidates) is not tuple or len(candidates) != 1:
                    self._record(db, now, 'discovery_not_unique')
                    return self._read(db)
                if not self._candidate(db, candidates[0], now):
                    return self._read(db)
            return self._verify(db, provider, clock)
