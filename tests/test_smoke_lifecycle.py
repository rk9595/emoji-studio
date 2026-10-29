import dataclasses
import hashlib
import json
import multiprocessing
import os
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.render_budget import RenderBudget
from emoji_studio.service import MockRenderer
from emoji_studio.smoke_cleanup import Binding, CleanupLedger, Lookup
from emoji_studio.smoke_export import REPOSITORY, Destination, digest
from emoji_studio.smoke_lifecycle import LifecycleDenied, Registration, SmokeLifecycle
from emoji_studio.smoke_reservation import AllocationLedger, Reservation
from emoji_studio.worker_queue import WorkerQueue

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / 'configs/amd-api-smoke-plan.json'
PLAN_HASH = hashlib.sha256(PLAN.read_bytes()).hexdigest()
SPEC = Reservation('mock-account', 'a'*32, PLAN_HASH, 'c'*64, 'd'*64, 3_000_000, 1_500_000, 1000, 1300)
BOUND = Binding('amd-devcloud', 'mock-account', 'a'*32, '12345', PLAN_HASH, 1000)


def present():
    return Lookup(200, {'id': BOUND.resource_id, 'name': BOUND.name,
                        'tags': list(BOUND.tags), 'created_epoch': BOUND.created_epoch})


class Provider:
    provider, account_id = 'amd-devcloud', 'mock-account'
    def create(self, reservation, *, timeout_seconds):
        return BOUND
    def lookup(self, resource_id, *, timeout_seconds=10):
        return present()
    def delete(self, resource_id):
        return 204


class AbsentProvider(Provider):
    def lookup(self, resource_id):
        return Lookup(404)


class FakeRegistrar:
    def __init__(self):
        self.receipt = None
        self.calls = []
    def register(self, binding, *, timeout_seconds):
        self.calls.append('register')
        assert timeout_seconds == 10
        self.receipt = Registration(digest(binding.encoded().encode()), binding.stop_epoch,
                                    binding.deadline_epoch, True, True)
    def lookup(self, binding, *, timeout_seconds):
        self.calls.append('lookup')
        assert timeout_seconds == 10
        return self.receipt


class Storage:
    def __init__(self, binding):
        self.objects = {}
        self.scope = Destination(REPOSITORY, binding.prefix, True)


class Writer:
    def __init__(self, storage):
        self.storage, self.calls = storage, []
    def destination(self, *, timeout_seconds):
        return self.storage.scope
    def put_if_absent(self, name, content, *, sha256, timeout_seconds):
        assert digest(content) == sha256 and timeout_seconds == 10
        self.calls.append(name)
        if name in self.storage.objects and self.storage.objects[name] != content:
            raise ValueError('conflict')
        self.storage.objects[name] = content


class Reader:
    def __init__(self, storage):
        self.storage, self.calls = storage, []
    def destination(self, *, timeout_seconds):
        return self.storage.scope
    def read(self, name, *, max_bytes, timeout_seconds):
        self.calls.append(name)
        return self.storage.objects[name]


def reopen(root, clock):
    allocation = AllocationLedger(root/'allocation', SPEC)
    cleanup = CleanupLedger(root/'cleanup', BOUND)
    budget = RenderBudget(root/'budget', allocation_id=BOUND.allocation_id, plan_sha256=PLAN_HASH)
    return SmokeLifecycle(root/'lifecycle', allocation, cleanup, budget, PLAN, clock=clock)


def die_registration(root):
    class Registrar(FakeRegistrar):
        def register(self, binding, *, timeout_seconds):
            os._exit(31)
    reopen(Path(root), lambda: 1000).register_cleanup(Registrar())


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.now = 1000
        self.clock = lambda: self.now
        self.allocation = AllocationLedger.create(self.root/'allocation', SPEC)
        self.allocation.run(Provider(), clock=self.clock)
        self.cleanup = CleanupLedger.create(self.root/'cleanup', BOUND)
        self.budget = RenderBudget.create(self.root/'budget', allocation_id=BOUND.allocation_id,
                                         plan_sha256=PLAN_HASH)
        self.life = SmokeLifecycle.create(self.root/'lifecycle', self.allocation, self.cleanup,
                                          self.budget, PLAN, clock=self.clock)
        self.store = WorkerQueue(self.root/'jobs', clock=self.clock, trial_image_cap=2)
        self.registrar = FakeRegistrar()
        self.storage = Storage(self.life.export_binding)
        self.writer, self.reader = Writer(self.storage), Reader(self.storage)

    def enqueue(self, name):
        self.store.enqueue(name, 'alice', ['a cheerful red apple sticker'], [7])

    def rendered(self):
        self.life.register_cleanup(self.registrar)
        for name in ('first', 'second'):
            self.enqueue(name)
            self.assertEqual(self.life.run_next(self.store, self.registrar), name)

    def staged(self):
        self.rendered()
        return self.life.stage_export(self.store, 'alice')

    def test_end_to_end_mock_receipts_require_export_and_verified_cleanup(self):
        bundle = self.staged()
        state = self.life.upload(bundle, self.writer)
        self.assertIsNone(state['export_receipt'])
        self.assertEqual(self.writer.calls[-1], 'manifest.json')
        self.life = reopen(self.root, self.clock)
        self.assertEqual(self.life.verify_download(self.reader)['export_receipt']['status'], 'export_verified')
        self.assertFalse(self.life.snapshot()['offline_complete'])
        self.cleanup.reconcile(AbsentProvider(), now=1001, reason='work_complete')
        state = self.life.snapshot()
        self.assertTrue(state['offline_complete'])
        self.assertEqual(state['render_calls'], 2)
        self.assertFalse(state['smoke_accepted'])
        self.assertFalse(state['gpu_validated'])

    def test_missing_registration_blocks_before_render_or_budget_consumption(self):
        self.enqueue('first')
        with patch.object(MockRenderer, 'render') as render:
            with self.assertRaisesRegex(LifecycleDenied, 'registration_required'):
                self.life.run_next(self.store, self.registrar)
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_registration_ack_without_fresh_lookup_is_insufficient(self):
        class Registrar(FakeRegistrar):
            def lookup(self, *args, **kwargs):
                return None
        registrar = Registrar()
        self.assertIsNone(self.life.register_cleanup(registrar)['registration'])
        with self.assertRaisesRegex(LifecycleDenied, 'consumed'):
            self.life.register_cleanup(registrar)
        self.assertEqual(registrar.calls.count('register'), 1)

    def test_lost_registration_ack_recovers_only_by_read_after_reopen(self):
        class Registrar(FakeRegistrar):
            def register(self, *args, **kwargs):
                super().register(*args, **kwargs)
                raise TimeoutError('private-url')
            def lookup(self, *args, **kwargs):
                raise TimeoutError('private-url')
        registrar = Registrar()
        state = self.life.register_cleanup(registrar)
        self.assertIsNone(state['registration'])
        self.assertNotIn('private-url', str(state))
        self.registrar.receipt = registrar.receipt
        life = reopen(self.root, self.clock)
        self.assertIsNotNone(life.reconcile_registration(self.registrar)['registration'])
        self.assertEqual(self.registrar.calls, ['lookup'])

    def test_registration_process_death_preserves_consumed_intent(self):
        child = multiprocessing.get_context('spawn').Process(target=die_registration, args=(str(self.root),))
        child.start()
        child.join(15)
        if child.is_alive():
            child.kill()
            child.join()
            self.fail('child failed to terminate')
        self.assertEqual(child.exitcode, 31)
        life = reopen(self.root, self.clock)
        self.assertTrue(life.snapshot()['registration_attempted'])
        with self.assertRaisesRegex(LifecycleDenied, 'consumed'):
            life.register_cleanup(self.registrar)
        self.assertEqual(self.registrar.calls, [])

    def test_each_registration_field_must_match(self):
        self.life.register_cleanup(self.registrar)
        original = self.registrar.receipt
        for change in ({'binding_sha256':'e'*64}, {'stop_epoch':2501}, {'deadline_epoch':2801},
                       {'active':False}, {'active':1}, {'independent':False}, {'stop_epoch':2500.0}):
            with self.subTest(change=change):
                self.registrar.receipt = dataclasses.replace(original, **change)
                self.assertIsNone(self.life.reconcile_registration(self.registrar)['registration'])

    def test_revoked_registration_stops_new_work_and_remains_halted(self):
        self.life.register_cleanup(self.registrar)
        original = self.registrar.receipt
        self.registrar.receipt = dataclasses.replace(original, active=False)
        self.enqueue('first')
        with self.assertRaisesRegex(LifecycleDenied, 'gate_closed'):
            self.life.run_next(self.store, self.registrar)
        self.registrar.receipt = original
        with self.assertRaisesRegex(LifecycleDenied, 'halted'):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_deadline_watermark_survives_clock_rollback(self):
        self.life.register_cleanup(self.registrar)
        self.now = BOUND.stop_epoch
        with self.assertRaisesRegex(LifecycleDenied, 'deadline'):
            self.life.run_next(self.store, self.registrar)
        self.now = 1000
        with self.assertRaisesRegex(LifecycleDenied, 'halted'):
            reopen(self.root, self.clock).run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_cleanup_pending_or_complete_blocks_render(self):
        self.life.register_cleanup(self.registrar)
        self.cleanup.reconcile(Provider(), now=1001, reason='work_failed')
        self.enqueue('first')
        with self.assertRaisesRegex(LifecycleDenied, 'gate_closed'):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_deadline_crossed_during_registration_read_consumes_no_render(self):
        self.life.register_cleanup(self.registrar)
        lookup = self.registrar.lookup
        def late(*args, **kwargs):
            self.now = BOUND.stop_epoch
            return lookup(*args, **kwargs)
        self.enqueue('first')
        with patch.object(self.registrar, 'lookup', side_effect=late), self.assertRaises(LifecycleDenied):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_deadline_crossed_inside_mock_render_blocks_success_and_next_call(self):
        self.life.register_cleanup(self.registrar)
        self.enqueue('first')
        render = MockRenderer.render
        outer = self
        def late(renderer, *args, **kwargs):
            result = render(renderer, *args, **kwargs)
            outer.now = BOUND.stop_epoch
            return result
        with patch.object(MockRenderer, 'render', late), self.assertRaises(LifecycleDenied):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 1)
        self.assertEqual(self.budget.snapshot()['calls'][0]['state'], 'failed')
        self.assertFalse(self.life.snapshot()['offline_complete'])

    def test_cleanup_can_run_during_mock_render_without_lifecycle_lock(self):
        self.life.register_cleanup(self.registrar)
        self.enqueue('first')
        render = MockRenderer.render
        outer = self
        def cleaned(renderer, *args, **kwargs):
            outer.cleanup.reconcile(AbsentProvider(), now=1001, reason='work_failed')
            return render(renderer, *args, **kwargs)
        with patch.object(MockRenderer, 'render', cleaned), self.assertRaises(LifecycleDenied):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.cleanup.snapshot()['status'], 'complete')
        self.assertEqual(self.budget.snapshot()['calls'][0]['state'], 'failed')

    def test_ticket_and_upload_intent_are_durable_before_first_write(self):
        bundle = self.staged()
        outer = self
        class CheckingWriter(Writer):
            def put_if_absent(self, *args, **kwargs):
                with sqlite3.connect(outer.life.path) as db:
                    state = json.loads(db.execute('SELECT state FROM lifecycle').fetchone()[0])
                outer.assertTrue(state['upload_attempted'])
                outer.assertEqual(state['ticket']['manifest_sha256'], digest(bundle.manifest))
                return super().put_if_absent(*args, **kwargs)
        self.life.upload(bundle, CheckingWriter(self.storage))

    def test_ticket_persistence_failure_leaves_no_upload_or_render_replay(self):
        self.rendered()
        with patch.object(self.life, '_save', side_effect=OSError('disk full')), self.assertRaises(OSError):
            self.life.stage_export(self.store, 'alice')
        self.assertIsNone(self.life.snapshot()['ticket'])
        self.assertEqual(self.writer.calls, [])
        self.assertEqual(self.budget.snapshot()['consumed'], 2)

    def test_lost_upload_ack_is_read_only_recoverable_and_not_reuploaded(self):
        bundle = self.staged()
        class LostWriter(Writer):
            def put_if_absent(self, *args, **kwargs):
                super().put_if_absent(*args, **kwargs)
                if args[0] == 'manifest.json':
                    raise TimeoutError('secret')
        writer = LostWriter(self.storage)
        state = self.life.upload(bundle, writer)
        self.assertIsNone(state['export_receipt'])
        self.assertNotIn('secret', str(state))
        life = reopen(self.root, self.clock)
        with self.assertRaisesRegex(LifecycleDenied, 'consumed'):
            life.upload(bundle, writer)
        self.assertEqual(len(writer.calls), 5)
        self.assertIsNotNone(life.verify_download(self.reader)['export_receipt'])

    def test_partial_upload_blocks_completion_but_cleanup_continues(self):
        bundle = self.staged()
        class PartialWriter(Writer):
            def put_if_absent(self, *args, **kwargs):
                super().put_if_absent(*args, **kwargs)
                raise TimeoutError('secret')
        self.life.upload(bundle, PartialWriter(self.storage))
        self.cleanup.reconcile(AbsentProvider(), now=1001, reason='work_failed')
        self.assertIsNone(self.life.verify_download(self.reader)['export_receipt'])
        state = self.life.snapshot()
        self.assertEqual(state['cleanup_status'], 'complete')
        self.assertFalse(state['offline_complete'])

    def test_blocked_upload_does_not_block_independent_cleanup(self):
        bundle = self.staged()
        entered, release = threading.Event(), threading.Event()
        errors = []
        class BlockingWriter(Writer):
            def put_if_absent(self, *args, **kwargs):
                entered.set()
                if not release.wait(5):
                    raise TimeoutError('test deadline')
                return super().put_if_absent(*args, **kwargs)
        def upload():
            try:
                self.life.upload(bundle, BlockingWriter(self.storage))
            except BaseException as error:
                errors.append(error)
        thread = threading.Thread(target=upload)
        thread.start()
        try:
            self.assertTrue(entered.wait(5))
            self.assertEqual(self.cleanup.reconcile(AbsentProvider(), now=1001,
                                                   reason='work_failed')['status'], 'complete')
        finally:
            release.set()
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])

    def test_ticket_is_pinned_and_work_cannot_resume_after_staging(self):
        self.staged()
        with self.assertRaisesRegex(LifecycleDenied, 'pinned'):
            self.life.stage_export(self.store, 'alice', indices=(1,))
        with self.assertRaisesRegex(LifecycleDenied, 'halted'):
            self.life.run_next(self.store, self.registrar)
        self.assertEqual(self.budget.snapshot()['consumed'], 2)

    def test_staging_requires_two_calls_and_correct_owner(self):
        with self.assertRaisesRegex(LifecycleDenied, 'two_successful'):
            self.life.stage_export(self.store, 'alice')
        self.rendered()
        with self.assertRaisesRegex(LifecycleDenied, 'owned_publication'):
            self.life.stage_export(self.store, 'mallory')
        self.assertIsNone(self.life.snapshot()['ticket'])
        bundle = self.life.stage_export(self.store, 'alice', indices=(1,))
        self.assertEqual(len(bundle.artifacts), 2)

    def test_modified_publication_bytes_fail_before_ticket(self):
        self.rendered()
        with sqlite3.connect(self.store.path) as db:
            db.execute("UPDATE artifacts SET content=? WHERE job_id='first'", (b'corrupt',))
        with self.assertRaises(ValueError):
            self.life.stage_export(self.store, 'alice')
        self.assertIsNone(self.life.snapshot()['ticket'])

    def test_reverification_failure_clears_old_export_success(self):
        bundle = self.staged()
        self.life.upload(bundle, self.writer)
        self.assertIsNotNone(self.life.verify_download(self.reader)['export_receipt'])
        self.storage.objects['manifest.json'] = b'corrupt'
        self.assertIsNone(self.life.verify_download(self.reader)['export_receipt'])

    def test_write_capable_reader_is_rejected(self):
        with self.assertRaisesRegex(LifecycleDenied, 'read_only'):
            self.life.verify_download(self.writer)

    def test_binding_mismatches_no_reset_missing_or_replaced_files_fail_closed(self):
        with self.assertRaises(FileExistsError):
            SmokeLifecycle.create(self.life.path, self.allocation, self.cleanup, self.budget, PLAN,
                                  clock=self.clock)
        wrong = CleanupLedger.create(self.root/'other-cleanup', dataclasses.replace(BOUND, resource_id='6789'))
        with self.assertRaisesRegex(LifecycleDenied, 'cleanup_binding'):
            SmokeLifecycle(self.life.path, self.allocation, wrong, self.budget, PLAN, clock=self.clock)
        self.life.lock_path.unlink()
        with self.assertRaises(FileNotFoundError):
            reopen(self.root, self.clock)
        self.assertFalse(self.life.lock_path.exists())

    def test_schema_and_identity_corruption_fail_closed(self):
        with sqlite3.connect(self.life.path) as db:
            db.execute("UPDATE lifecycle SET identity='other'")
        with self.assertRaisesRegex(LifecycleDenied, 'identity'):
            self.life.snapshot()
        with sqlite3.connect(self.life.path) as db:
            db.execute('PRAGMA user_version=2')
        with self.assertRaisesRegex(LifecycleDenied, 'schema'):
            self.life.snapshot()

    def test_registration_and_upload_persistence_failures_prevent_side_effects(self):
        with patch.object(self.life, '_save', side_effect=OSError('disk full')), self.assertRaises(OSError):
            self.life.register_cleanup(self.registrar)
        self.assertEqual(self.registrar.calls, [])
        self.assertFalse(self.life.snapshot()['registration_attempted'])
        bundle = self.staged()
        with patch.object(self.life, '_save', side_effect=OSError('disk full')), self.assertRaises(OSError):
            self.life.upload(bundle, self.writer)
        self.assertEqual(self.writer.calls, [])
        self.assertFalse(self.life.snapshot()['upload_attempted'])

    def test_changed_allocation_state_blocks_before_render(self):
        self.life.register_cleanup(self.registrar)
        self.enqueue('first')
        with sqlite3.connect(self.allocation.path) as db:
            db.execute("UPDATE allocation SET status='outcome_unknown'")
        with patch.object(MockRenderer, 'render') as render:
            with self.assertRaisesRegex(LifecycleDenied, 'allocation_not_bound'):
                self.life.run_next(self.store, self.registrar)
            render.assert_not_called()
        self.assertEqual(self.budget.snapshot()['consumed'], 0)

    def test_nonprivate_or_linked_receipt_files_are_rejected(self):
        self.life.path.chmod(0o644)
        with self.assertRaisesRegex(LifecycleDenied, 'private_regular'):
            self.life.snapshot()
        self.life.path.chmod(0o600)
        alias = self.root/'alias'
        alias.symlink_to(self.life.path)
        with self.assertRaises(RuntimeError):
            SmokeLifecycle(alias, self.allocation, self.cleanup, self.budget, PLAN, clock=self.clock)
        alias.unlink()
        os.link(self.life.path, alias)
        with self.assertRaisesRegex(LifecycleDenied, 'private_regular'):
            self.life.snapshot()

    def test_mismatched_render_budget_is_not_accepted(self):
        budget = RenderBudget.create(self.root/'other-budget', allocation_id='b'*32, plan_sha256=PLAN_HASH)
        with self.assertRaisesRegex(LifecycleDenied, 'render_binding'):
            SmokeLifecycle(self.life.path, self.allocation, self.cleanup, budget, PLAN, clock=self.clock)


if __name__ == '__main__':
    unittest.main()
