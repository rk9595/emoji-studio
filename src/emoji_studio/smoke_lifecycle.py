"""Offline mock lifecycle coordination. No live adapter, scheduler or GPU entry point."""

import fcntl
import json
import os
import sqlite3
import stat
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from types import SimpleNamespace
from typing import Protocol

from emoji_studio.mock_smoke_executor import MockSmokeExecutor, read_plan
from emoji_studio.render_budget import checked_path
from emoji_studio.smoke_cleanup import Binding
from emoji_studio.smoke_export import (
    ExportBinding,
    Ticket,
    canonical,
    digest,
    export_ticket,
    prepare_export,
    upload_export,
    verify_export,
)


class LifecycleDenied(RuntimeError):
    pass


def require(condition, code):
    if not condition:
        raise LifecycleDenied(code)


@dataclass(frozen=True)
class Registration:
    """Normalized trusted-service assertion, not proof a scheduler is deployed."""
    binding_sha256: str
    stop_epoch: int
    deadline_epoch: int
    active: bool
    independent: bool


class Registrar(Protocol):
    def register(self, binding: Binding, *, timeout_seconds: int) -> None: ...
    def lookup(self, binding: Binding, *, timeout_seconds: int) -> Registration: ...


class SmokeLifecycle:
    """One local receipt journal, separate from independently callable cleanup.

    Requires an already bound reservation and matching cleanup/render ledgers.
    Registration and upload are consumed before their side effects; restart uses
    read-only reconciliation, never a second registration/upload invocation.
    Only the existing MockSmokeExecutor can be run through this coordinator.
    """

    def __init__(self, path, allocation, cleanup, budget, plan_path, *, clock):
        self.path = checked_path(path)
        self.lock_path = self.path.with_name(self.path.name + '.lock')
        self.allocation, self.cleanup, self.budget = allocation, cleanup, budget
        self.clock, self.plan_path = clock, plan_path
        allocation_state = allocation.snapshot()
        require(allocation_state['status'] == 'bound', 'allocation_not_bound')
        self.binding = Binding(**allocation_state['candidate'])
        require(cleanup.binding == self.binding, 'cleanup_binding_mismatch')
        usage = budget.snapshot()
        require((usage['allocation_id'], usage['plan_sha256']) == (
            self.binding.allocation_id, self.binding.plan_sha256), 'render_binding_mismatch')
        plan = read_plan(plan_path, self.binding.plan_sha256)
        self.export_binding = ExportBinding(self.binding.allocation_id, self.binding.plan_sha256,
                                            plan['source_sha256']['configs/serving.json'])
        self.identity = canonical({'binding': asdict(self.binding),
                                   'reservation': allocation_state['reservation'],
                                   'export_binding': asdict(self.export_binding)}).decode()
        self.file_identity = self._file_identity(self.path)
        self.lock_identity = self._file_identity(self.lock_path)
        with self._locked() as db:
            self._read(db)

    @classmethod
    def create(cls, path, allocation, cleanup, budget, plan_path, *, clock):
        # Validate dependencies before creating files, using no network operations.
        state = allocation.snapshot()
        require(state['status'] == 'bound', 'allocation_not_bound')
        binding = Binding(**state['candidate'])
        require(cleanup.binding == binding, 'cleanup_binding_mismatch')
        usage = budget.snapshot()
        require((usage['allocation_id'], usage['plan_sha256']) == (
            binding.allocation_id, binding.plan_sha256), 'render_binding_mismatch')
        plan = read_plan(plan_path, binding.plan_sha256)
        identity = canonical({'binding': asdict(binding), 'reservation': state['reservation'],
                              'export_binding': asdict(ExportBinding(binding.allocation_id,
                                  binding.plan_sha256, plan['source_sha256']['configs/serving.json']))}).decode()
        path = checked_path(path)
        for target in (path, path.with_name(path.name + '.lock')):
            fd = os.open(checked_path(target), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
        db = sqlite3.connect(path.as_uri() + '?mode=rw', uri=True)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE lifecycle (id INTEGER PRIMARY KEY CHECK(id=1), '
                       'identity TEXT NOT NULL, state TEXT NOT NULL)')
            db.execute('INSERT INTO lifecycle VALUES(1,?,?)', (identity, canonical({
                'last_epoch': binding.created_epoch, 'registration_attempted': False,
                'registration': None, 'halted': False, 'ticket': None,
                'upload_attempted': False, 'export_receipt': None, 'events': [],
            }).decode()))
            db.execute('PRAGMA user_version=1')
            db.commit()
        finally:
            db.close()
        return cls(path, allocation, cleanup, budget, plan_path, clock=clock)

    @staticmethod
    def _file_identity(path):
        info = checked_path(path).stat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1
                and not stat.S_IMODE(info.st_mode) & 0o077, 'private_regular_ledger_required')
        return info.st_dev, info.st_ino

    def _check_files(self):
        require(self._file_identity(self.path) == self.file_identity
                and self._file_identity(self.lock_path) == self.lock_identity, 'ledger_replaced')

    @contextmanager
    def _locked(self):
        self._check_files()
        fd = os.open(self.lock_path, os.O_RDWR | os.O_NOFOLLOW)
        db = None
        try:
            info = os.fstat(fd)
            require((info.st_dev, info.st_ino) == self.lock_identity, 'ledger_replaced')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise LifecycleDenied('lifecycle_busy') from None
            self._check_files()
            db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True)
            db.execute('PRAGMA synchronous=FULL')
            yield db
            self._check_files()
        finally:
            if db is not None:
                db.close()
            os.close(fd)

    def _valid_registration(self, receipt):
        return type(receipt) is Registration and (
            receipt.binding_sha256 == digest(self.binding.encoded().encode())
            and type(receipt.stop_epoch) is int and receipt.stop_epoch == self.binding.stop_epoch
            and type(receipt.deadline_epoch) is int and receipt.deadline_epoch == self.binding.deadline_epoch
            and receipt.active is True and receipt.independent is True
        )

    def _read(self, db):
        require(db.execute('PRAGMA user_version').fetchone()[0] == 1, 'unsupported_schema')
        rows = db.execute('SELECT id,identity,state FROM lifecycle').fetchall()
        require(len(rows) == 1 and rows[0][:2] == (1, self.identity), 'lifecycle_identity_mismatch')
        try:
            state = json.loads(rows[0][2])
            require(set(state) == {'last_epoch', 'registration_attempted', 'registration', 'halted',
                                  'ticket', 'upload_attempted', 'export_receipt', 'events'}, 'invalid_state')
            require(type(state['last_epoch']) is int and state['last_epoch'] >= self.binding.created_epoch
                    and all(type(state[k]) is bool for k in ('registration_attempted', 'halted', 'upload_attempted'))
                    and type(state['events']) is list, 'invalid_state')
            if state['registration'] is not None:
                require(state['registration_attempted'] and self._valid_registration(
                    Registration(**state['registration'])), 'invalid_registration')
            if state['ticket'] is not None:
                ticket = self._ticket(state)
                require(state['halted'] and ticket.binding == self.export_binding, 'invalid_ticket')
            if state['upload_attempted']:
                require(state['ticket'] is not None, 'upload_without_ticket')
            if state['export_receipt'] is not None:
                receipt = state['export_receipt']
                require(state['upload_attempted'] and receipt['status'] == 'export_verified'
                        and receipt['binding'] == asdict(self.export_binding)
                        and receipt['manifest_sha256'] == self._ticket(state).manifest_sha256
                        and receipt['renderer'] == 'MockRenderer', 'invalid_export_receipt')
            return state
        except LifecycleDenied:
            raise
        except Exception:
            raise LifecycleDenied('invalid_state') from None

    def _save(self, db, state, event):
        self._check_files()
        state['events'].append({'epoch': state['last_epoch'], 'event': event})
        db.execute('UPDATE lifecycle SET state=? WHERE id=1', (canonical(state).decode(),))
        db.commit()

    def _time(self, state):
        now = self.clock()
        require(type(now) is int and self.binding.created_epoch <= now < 2**63, 'invalid_clock')
        state['last_epoch'] = max(now, state['last_epoch'])
        return state['last_epoch']

    def _registration_read(self, registrar):
        try:
            receipt = registrar.lookup(self.binding, timeout_seconds=10)
        except Exception:
            return None
        return receipt if self._valid_registration(receipt) else None

    def register_cleanup(self, registrar: Registrar):
        with self._locked() as db:
            state = self._read(db)
            self._time(state)
            require(not state['registration_attempted'], 'registration_attempt_consumed')
            state['registration_attempted'] = True
            self._save(db, state, 'registration_intent')
            try:
                registrar.register(self.binding, timeout_seconds=10)
            except Exception:
                self._save(db, state, 'registration_ack_unknown')
            receipt = self._registration_read(registrar)
            self._time(state)
            if receipt is not None:
                state['registration'] = asdict(receipt)
            self._save(db, state, 'registration_verified' if receipt else 'registration_unverified')
            return state

    def reconcile_registration(self, registrar: Registrar):
        with self._locked() as db:
            state = self._read(db)
            require(state['registration_attempted'], 'no_registration_attempt')
            receipt = self._registration_read(registrar)
            self._time(state)
            state['registration'] = asdict(receipt) if receipt else None
            self._save(db, state, 'registration_verified' if receipt else 'registration_unverified')
            return state

    def _gate(self, db, state, registrar):
        now = self._time(state)
        require(not state['halted'], 'work_halted')
        allocation = self.allocation.snapshot()
        require(allocation['status'] == 'bound' and allocation['candidate'] == asdict(self.binding),
                'allocation_not_bound')
        if now >= self.binding.stop_epoch:
            state['halted'] = True
            self._save(db, state, 'work_deadline')
            raise LifecycleDenied('work_deadline')
        require(state['registration'] is not None, 'cleanup_registration_required')
        receipt = self._registration_read(registrar)
        now = self._time(state)
        cleanup = self.cleanup.snapshot()
        if receipt is None or now >= self.binding.stop_epoch or cleanup['status'] != 'watching':
            state['halted'] = True
            self._save(db, state, 'work_gate_closed')
            raise LifecycleDenied('work_gate_closed')
        self._save(db, state, 'work_gate_checked')

    def run_next(self, store, registrar: Registrar):
        """Mock renderer only; check before claim, inside budget, and after callback."""
        with self._locked() as db:
            state = self._read(db)
            self._gate(db, state, registrar)
            lifecycle = self
            class GuardedBudget:
                def snapshot(self):
                    return lifecycle.budget.snapshot()

                def run(self, call_id, request_sha256, callback):
                    def guarded():
                        lifecycle._gate(db, state, registrar)
                        result = callback()
                        lifecycle._gate(db, state, registrar)
                        return result
                    return lifecycle.budget.run(call_id, request_sha256, guarded)
            try:
                return MockSmokeExecutor(store, GuardedBudget(), self.plan_path).run_next()
            except BaseException as error:
                state['halted'] = True
                self._save(db, state, 'mock_work_failed')
                if isinstance(error, Exception):
                    raise LifecycleDenied('mock_work_failed') from None
                raise

    @staticmethod
    def _ticket(state):
        value = state['ticket']
        return Ticket(ExportBinding(**value['binding']), value['manifest_sha256'])

    def stage_export(self, store, owner_id, *, indices=(0, 1)):
        """Build only from owned, successful mock publications; retain pin first."""
        require(type(indices) is tuple and indices in ((0,), (1,), (0, 1))
                and all(type(i) is int for i in indices), 'invalid_export_indices')
        with self._locked() as db:
            state = self._read(db)
            usage = self.budget.snapshot()
            require(usage['consumed'] == 2 and all(c['state'] == 'succeeded' for c in usage['calls']),
                    'two_successful_mock_calls_required')
            require(not state['halted'] or state['ticket'] is not None, 'work_halted')
            executor = MockSmokeExecutor(store, self.budget, self.plan_path)
            images = {}
            for index in indices:
                call = usage['calls'][index]
                job_id, separator, number = call['call_id'].rpartition(':')
                require(separator and number == '0', 'invalid_render_identity')
                job = store.get(job_id, owner_id)
                require(job is not None and job['status'] == 'succeeded', 'owned_publication_required')
                require(executor.call_identity(SimpleNamespace(job_id=job_id, payload=job['payload'])) ==
                        (call['call_id'], call['request_sha256']), 'publication_identity_mismatch')
                pair = {}
                for extension in ('png', 'webp'):
                    name = f'00-7.{extension}'
                    artifact = store.artifact(job_id, owner_id, name)
                    require(artifact is not None, 'published_artifact_missing')
                    content = artifact
                    require(digest(content) == job['artifacts'].get(name), 'published_artifact_corrupt')
                    pair[extension] = content
                images[index] = pair
            bundle = prepare_export(self.export_binding, images, renderer='MockRenderer')
            ticket = export_ticket(bundle)
            encoded = asdict(ticket)
            require(state['ticket'] in (None, encoded), 'export_ticket_already_pinned')
            state['halted'], state['ticket'] = True, encoded
            self._time(state)
            self._save(db, state, 'export_ticket_retained')
            return bundle

    def upload(self, bundle, writer):
        ticket = export_ticket(bundle)
        with self._locked() as db:
            state = self._read(db)
            require(state['ticket'] is not None and ticket == self._ticket(state), 'retained_ticket_required')
            require(not state['upload_attempted'], 'upload_attempt_consumed')
            state['upload_attempted'] = True
            self._save(db, state, 'upload_intent')
            try:
                upload_export(bundle, writer)
            except Exception:
                self._save(db, state, 'upload_ack_unknown')
                return state
            self._save(db, state, 'upload_acknowledged')
            return state

    def verify_download(self, reader):
        # Distinct read-only interface supports restart with no writer/bundle.
        require(not hasattr(reader, 'put_if_absent'), 'read_only_download_client_required')
        with self._locked() as db:
            state = self._read(db)
            require(state['ticket'] is not None and state['upload_attempted'], 'upload_intent_required')
            # Clear old evidence before a fresh read; failed revalidation is not success.
            state['export_receipt'] = None
            self._save(db, state, 'download_verification_started')
            try:
                receipt = verify_export(self._ticket(state), reader)
                require(receipt['renderer'] == 'MockRenderer', 'mock_export_required')
            except Exception:
                self._save(db, state, 'download_unverified')
                return state
            state['export_receipt'] = receipt
            self._save(db, state, 'download_verified')
            return state

    def snapshot(self):
        with self._locked() as db:
            state = self._read(db)
            cleanup = self.cleanup.snapshot()
            usage = self.budget.snapshot()
            complete = (state['export_receipt'] is not None and cleanup['status'] == 'complete'
                        and state['registration'] is not None and usage['consumed'] == 2
                        and all(c['state'] == 'succeeded' for c in usage['calls']))
            return {**state, 'cleanup_status': cleanup['status'], 'render_calls': usage['consumed'],
                    'offline_complete': complete, 'gpu_validated': False, 'smoke_accepted': False}
