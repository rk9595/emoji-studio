import dataclasses
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.smoke_cleanup import Binding, CleanupLedger, Lookup
from emoji_studio.smoke_reservation import AllocationLedger, Reservation, ReservationDenied

SPEC = Reservation('mock-account', 'a'*32, 'b'*64, 'c'*64, 'd'*64,
                   3_000_000, 1_500_000, 1000, 1300)
BINDING = Binding('amd-devcloud', 'mock-account', 'a'*32, '12345', 'b'*64, 1000)


def present(binding=BINDING):
    return Lookup(200, {'id': binding.resource_id, 'name': binding.name,
                        'tags': list(binding.tags), 'created_epoch': binding.created_epoch})


class FakeProvider:
    provider = 'amd-devcloud'
    account_id = 'mock-account'

    def __init__(self, candidate=BINDING, discovered=(BINDING,), lookup=None):
        self.candidate, self.discovered = candidate, discovered
        self.response = present() if lookup is None else lookup
        self.calls = []

    def create(self, reservation, *, timeout_seconds):
        self.calls.append(('CREATE', reservation, timeout_seconds))
        if isinstance(self.candidate, BaseException):
            raise self.candidate
        return self.candidate

    def discover(self, reservation, *, timeout_seconds):
        self.calls.append(('DISCOVER', reservation, timeout_seconds))
        if isinstance(self.discovered, BaseException):
            raise self.discovered
        return self.discovered

    def lookup(self, resource_id, *, timeout_seconds):
        self.calls.append(('GET', resource_id, timeout_seconds))
        if isinstance(self.response, BaseException):
            raise self.response
        return self.response


def crash_create(path):
    class CrashProvider(FakeProvider):
        def create(self, reservation, *, timeout_seconds):
            os._exit(17)
    AllocationLedger(path, SPEC).run(CrashProvider(), clock=lambda: 1000)


class ReservationTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name).resolve() / 'reservation.sqlite'
        self.ledger = AllocationLedger.create(self.path, SPEC)

    def run_provider(self, provider, now=1000):
        return self.ledger.run(provider, clock=lambda: now)

    def unknown(self):
        self.run_provider(FakeProvider(candidate=TimeoutError('secret')))

    def test_reservation_is_private_and_does_not_authorize_rendering(self):
        state = self.ledger.snapshot()
        self.assertEqual(state['status'], 'reserved')
        self.assertFalse(state['attempt_consumed'])
        self.assertEqual(state['reserve_held_microusd'], 1_500_000)
        self.assertFalse(state['rendering_authorized'])
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.ledger.lock_path.stat().st_mode & 0o777, 0o600)

    def test_success_requires_exact_identity_and_consumes_only_attempt(self):
        provider = FakeProvider()
        state = self.run_provider(provider)
        self.assertEqual(state['status'], 'bound')
        self.assertEqual([c[0] for c in provider.calls], ['CREATE', 'GET'])
        self.assertTrue(all(c[2] == 10 for c in provider.calls))
        reopened = AllocationLedger(self.path, SPEC)
        with self.assertRaisesRegex(ReservationDenied, 'consumed'):
            reopened.run(provider, clock=lambda: 1100)
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(reopened.reconcile(provider, clock=lambda: 10000)['status'], 'bound')
        self.assertEqual(len(provider.calls), 2)

    def test_commit_precedes_provider_call_and_other_handles_cannot_overlap(self):
        outer = self
        class Provider(FakeProvider):
            def create(self, reservation, *, timeout_seconds):
                with sqlite3.connect(outer.path) as db:
                    status, epoch = db.execute('SELECT status,attempt_epoch FROM allocation').fetchone()
                    outer.assertEqual((status, epoch), ('outcome_unknown', 1000))
                with outer.assertRaisesRegex(ReservationDenied, 'busy'):
                    AllocationLedger(outer.path, SPEC)
                return super().create(reservation, timeout_seconds=timeout_seconds)
        self.run_provider(Provider())

    def test_no_call_when_intent_persistence_fails(self):
        provider = FakeProvider()
        with patch.object(self.ledger, '_record', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.run_provider(provider)
        self.assertEqual(provider.calls, [])
        self.assertFalse(self.ledger.snapshot()['attempt_consumed'])

    def test_existing_second_handle_cannot_create_concurrently_or_after_success(self):
        other = AllocationLedger(self.path, SPEC)
        outer = self
        second_provider = FakeProvider()
        class Provider(FakeProvider):
            def create(self, reservation, *, timeout_seconds):
                with outer.assertRaisesRegex(ReservationDenied, 'busy'):
                    other.run(second_provider, clock=lambda: 1000)
                return super().create(reservation, timeout_seconds=timeout_seconds)
        self.run_provider(Provider())
        with self.assertRaisesRegex(ReservationDenied, 'consumed'):
            other.run(second_provider, clock=lambda: 1100)
        self.assertEqual(second_provider.calls, [])

    def test_lost_candidate_commit_keeps_consumption_and_requires_reconciliation(self):
        record = self.ledger._record
        def fail_candidate(db, now, outcome):
            if outcome == 'candidate_retained':
                raise OSError('disk full')
            return record(db, now, outcome)
        provider = FakeProvider()
        with patch.object(self.ledger, '_record', side_effect=fail_candidate), self.assertRaises(OSError):
            self.run_provider(provider)
        reopened = AllocationLedger(self.path, SPEC)
        self.assertTrue(reopened.snapshot()['attempt_consumed'])
        self.assertIsNone(reopened.snapshot()['candidate'])
        with self.assertRaisesRegex(ReservationDenied, 'consumed'):
            reopened.run(provider, clock=lambda: 1100)
        self.assertEqual([c[0] for c in provider.calls], ['CREATE'])
        self.assertEqual(reopened.reconcile(provider, clock=lambda: 1100)['status'], 'bound')

    def test_uncertain_creation_never_refunds_and_can_reconcile_exact_resource(self):
        self.unknown()
        state = self.ledger.snapshot()
        self.assertEqual(state['status'], 'outcome_unknown')
        self.assertNotIn('secret', str(state))
        provider = FakeProvider()
        state = AllocationLedger(self.path, SPEC).reconcile(provider, clock=lambda: 1100)
        self.assertEqual(state['status'], 'bound')
        self.assertEqual([c[0] for c in provider.calls], ['DISCOVER', 'GET'])
        self.assertEqual(state['reserve_held_microusd'], SPEC.reserve_microusd)

    def test_process_death_during_create_leaves_consumed_intent(self):
        child = multiprocessing.get_context('spawn').Process(target=crash_create, args=(str(self.path),))
        child.start()
        child.join(15)
        if child.is_alive():
            child.kill()
            child.join()
            self.fail('crash test child did not terminate')
        self.assertEqual(child.exitcode, 17)
        reopened = AllocationLedger(self.path, SPEC)
        self.assertEqual(reopened.snapshot()['status'], 'outcome_unknown')
        provider = FakeProvider()
        with self.assertRaisesRegex(ReservationDenied, 'consumed'):
            reopened.run(provider, clock=lambda: 1100)
        self.assertEqual(provider.calls, [])
        self.assertEqual(reopened.reconcile(provider, clock=lambda: 1100)['status'], 'bound')

    def test_interrupt_still_consumes_attempt(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_provider(FakeProvider(candidate=KeyboardInterrupt()))
        self.assertTrue(self.ledger.snapshot()['attempt_consumed'])

    def test_ambiguous_missing_or_failed_discovery_never_creates_replacement(self):
        self.unknown()
        for result in ((), (BINDING, BINDING), [BINDING], None, TimeoutError('secret')):
            with self.subTest(result=type(result).__name__):
                provider = FakeProvider(discovered=result)
                state = self.ledger.reconcile(provider, clock=lambda: 5000)
                self.assertEqual(state['status'], 'outcome_unknown')
                self.assertEqual([c[0] for c in provider.calls], ['DISCOVER'])
                self.assertNotIn('secret', str(state))
                with self.assertRaisesRegex(ReservationDenied, 'consumed'):
                    self.run_provider(provider)

    def test_candidate_persisted_before_lookup_and_reused_without_discovery(self):
        provider = FakeProvider(lookup=TimeoutError('private-url'))
        state = self.run_provider(provider)
        self.assertEqual(state['candidate']['resource_id'], '12345')
        self.assertEqual(state['status'], 'outcome_unknown')
        self.assertNotIn('private-url', str(state))
        provider = FakeProvider(discovered=(dataclasses.replace(BINDING, resource_id='6789'),))
        state = self.ledger.reconcile(provider, clock=lambda: 1100)
        self.assertEqual(state['status'], 'bound')
        self.assertEqual([c[0] for c in provider.calls], ['GET'])

    def test_create_ack_or_exact_404_never_means_binding_or_refund(self):
        for response in (Lookup(404), Lookup(403), Lookup(500), Lookup(302), Lookup(200, {})):
            path = self.path.with_name(f'bad-{response.status}')
            ledger = AllocationLedger.create(path, SPEC)
            provider = FakeProvider(lookup=response)
            state = ledger.run(provider, clock=lambda: 1000)
            self.assertEqual(state['status'], 'outcome_unknown')
            self.assertTrue(state['attempt_consumed'])
            self.assertFalse(state['rendering_authorized'])

    def test_wrong_candidate_binding_is_rejected(self):
        changes = ({'account_id':'other'}, {'allocation_id':'f'*32}, {'plan_sha256':'e'*64},
                   {'created_epoch':999}, {'created_epoch':1001})
        for i, change in enumerate(changes):
            with self.subTest(change=change):
                ledger = AllocationLedger.create(self.path.with_name(f'candidate-{i}'), SPEC)
                provider = FakeProvider(candidate=dataclasses.replace(BINDING, **change))
                state = ledger.run(provider, clock=lambda: 1000)
                self.assertIsNone(state['candidate'])
                self.assertEqual(state['status'], 'outcome_unknown')
                self.assertEqual([c[0] for c in provider.calls], ['CREATE'])

    def test_provider_scope_is_checked_before_any_call_or_consumption(self):
        for field in ('provider', 'account_id'):
            provider = FakeProvider()
            setattr(provider, field, 'other')
            with self.assertRaisesRegex(ReservationDenied, 'scope'):
                self.run_provider(provider)
            self.assertEqual(provider.calls, [])
            self.assertFalse(self.ledger.snapshot()['attempt_consumed'])

    def test_exact_resource_name_tags_and_time_are_required(self):
        for i, change in enumerate(({'name':'wrong'}, {'id':'6789'}, {'tags':[]}, {'created_epoch':999})):
            ledger = AllocationLedger.create(self.path.with_name(f'exact-{i}'), SPEC)
            provider = FakeProvider(lookup=Lookup(200, {**present().resource, **change}))
            self.assertEqual(ledger.run(provider, clock=lambda: 1000)['status'], 'outcome_unknown')

    def test_expiry_watermark_cannot_be_rolled_back(self):
        provider = FakeProvider()
        for now in (1300, 1000):
            with self.assertRaisesRegex(ReservationDenied, 'expired'):
                self.run_provider(provider, now)
        self.assertEqual(provider.calls, [])
        self.assertEqual(self.ledger.snapshot()['last_epoch'], 1300)

    def test_clock_is_resampled_after_create_before_accepting_creation_time(self):
        binding = dataclasses.replace(BINDING, created_epoch=1002)
        provider = FakeProvider(candidate=binding, lookup=present(binding))
        times = iter([1000, 1003, 1004, 1005])
        state = self.ledger.run(provider, clock=lambda: next(times))
        self.assertEqual(state['status'], 'bound')
        self.assertEqual(state['last_epoch'], 1005)

    def test_clock_failure_after_create_leaves_unknown_without_replay(self):
        times = iter([1000])
        with self.assertRaises(StopIteration):
            self.ledger.run(FakeProvider(), clock=lambda: next(times))
        self.assertEqual(self.ledger.snapshot()['status'], 'outcome_unknown')

    def test_invalid_clock_values_never_call_create(self):
        for now in (True, 999, 1000.0, 2**63):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.run_provider(FakeProvider(), now)
        self.assertFalse(self.ledger.snapshot()['attempt_consumed'])

    def test_expired_reconciliation_can_still_recover_for_cleanup(self):
        self.unknown()
        state = self.ledger.reconcile(FakeProvider(), clock=lambda: 5000)
        binding = Binding(**state['candidate'])
        cleanup = CleanupLedger.create(self.path.with_name('cleanup.sqlite'), binding)
        class AbsentProvider:
            provider, account_id = 'amd-devcloud', 'mock-account'
            def lookup(self, resource_id):
                return Lookup(404)
        self.assertEqual(cleanup.reconcile(AbsentProvider(), now=5000)['status'], 'complete')
        with self.assertRaisesRegex(ReservationDenied, 'consumed'):
            self.run_provider(FakeProvider(), 5000)
        self.assertEqual(self.ledger.snapshot()['reserve_held_microusd'], SPEC.reserve_microusd)

    def test_reconcile_before_attempt_is_not_a_create_path(self):
        provider = FakeProvider()
        with self.assertRaisesRegex(ReservationDenied, 'no_attempt'):
            self.ledger.reconcile(provider, clock=lambda: 1000)
        self.assertEqual(provider.calls, [])

    def test_reopen_requires_exact_reservation_no_reset_or_rebind(self):
        with self.assertRaises(FileExistsError):
            AllocationLedger.create(self.path, SPEC)
        for change in ({'allocation_id':'f'*32}, {'reserve_microusd':1}, {'approval_sha256':'e'*64},
                       {'request_sha256':'e'*64}, {'expires_epoch':1400}):
            with self.subTest(change=change), self.assertRaisesRegex(ReservationDenied, 'mismatch'):
                AllocationLedger(self.path, dataclasses.replace(SPEC, **change))

    def test_invalid_policy_and_comparison_are_rejected(self):
        for change in ({'campaign':'amd-comparison-v1'}, {'allocation_id':'old'}, {'provider':'other'},
                       {'reserve_microusd':True}, {'reserve_microusd':0}, {'reserve_microusd':3_000_001},
                       {'allowance_microusd':1.0}, {'expires_epoch':2801}, {'expires_epoch':1000},
                       {'approval_sha256':'invalid'}, {'request_sha256':'invalid'}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                dataclasses.replace(SPEC, **change)

    def test_missing_lock_or_ledger_never_recreated(self):
        self.ledger.lock_path.unlink()
        with self.assertRaises(FileNotFoundError):
            AllocationLedger(self.path, SPEC)
        self.assertFalse(self.ledger.lock_path.exists())
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            AllocationLedger(self.path, SPEC)
        self.assertFalse(self.path.exists())

    def test_links_and_nonprivate_files_rejected(self):
        alias = self.path.with_name('alias')
        alias.symlink_to(self.path)
        with self.assertRaises(RuntimeError):
            AllocationLedger(alias, SPEC)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaisesRegex(ReservationDenied, 'private_regular'):
            self.ledger.snapshot()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaisesRegex(ReservationDenied, 'private_regular'):
            self.ledger.snapshot()

    def test_replaced_ledger_rejected_by_existing_handle(self):
        replacement = self.path.with_name('replacement')
        AllocationLedger.create(replacement, SPEC)
        replacement.replace(self.path)
        with self.assertRaisesRegex(ReservationDenied, 'replaced'):
            self.ledger.snapshot()

    def test_malformed_state_and_false_binding_fail_closed(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE allocation SET status='bound'")
        with self.assertRaises(ReservationDenied):
            self.ledger.snapshot()
        with sqlite3.connect(self.path) as db:
            db.execute('PRAGMA user_version=2')
        with self.assertRaisesRegex(ReservationDenied, 'schema'):
            self.ledger.snapshot()


if __name__ == '__main__':
    unittest.main()
