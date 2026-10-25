import dataclasses
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.smoke_cleanup import Binding, CleanupDenied, CleanupLedger, Lookup

BINDING = Binding("amd-devcloud", "mock-account", "a" * 32, "12345", "b" * 64, 1000)


def present(binding=BINDING):
    return Lookup(200, {"id": binding.resource_id, "name": binding.name,
                        "tags": list(binding.tags), "created_epoch": binding.created_epoch})


class FakeProvider:
    provider = "amd-devcloud"
    account_id = "mock-account"

    def __init__(self, responses=None, delete_status=204):
        self.responses = iter(responses if responses is not None else [present(), Lookup(404)])
        self.delete_status = delete_status
        self.calls = []

    def lookup(self, resource_id):
        self.calls.append(("GET", resource_id))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response

    def delete(self, resource_id):
        self.calls.append(("DELETE", resource_id))
        if isinstance(self.delete_status, BaseException):
            raise self.delete_status
        return self.delete_status


def crash_during_delete(path):
    class CrashProvider(FakeProvider):
        def delete(self, resource_id):
            os._exit(17)

    CleanupLedger(path, BINDING).reconcile(CrashProvider(), now=2500)


class CleanupTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name).resolve() / "cleanup.sqlite"
        self.ledger = CleanupLedger.create(self.path, BINDING)

    def test_deadline_starts_cleanup_at_25_minutes_without_worker_signal(self):
        provider = FakeProvider()
        state = self.ledger.reconcile(provider, now=2499)
        self.assertEqual(state["status"], "watching")
        self.assertEqual(provider.calls, [])
        state = self.ledger.reconcile(provider, now=2500)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(provider.calls, [("GET", "12345"), ("DELETE", "12345"), ("GET", "12345")])
        self.assertEqual(state["receipts"][-1]["outcome"], "exact_get_absent")

    def test_terminal_work_cleans_up_early_and_does_not_need_export(self):
        for reason in ("work_complete", "work_failed"):
            with self.subTest(reason=reason):
                path = self.path.with_name(reason)
                state = CleanupLedger.create(path, BINDING).reconcile(
                    FakeProvider(), now=1001, reason=reason)
                self.assertEqual(state["status"], "complete")

    def test_acknowledgement_is_not_absence_and_reopen_retains_pending(self):
        state = self.ledger.reconcile(FakeProvider([present(), present()]), now=2500)
        self.assertEqual(state["status"], "pending_cleanup")
        self.assertFalse(state["deadline_exceeded"])
        reopened = CleanupLedger(self.path, BINDING)
        provider = FakeProvider([Lookup(404)])
        state = reopened.reconcile(provider, now=2600)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(provider.calls, [("GET", "12345")])

    def test_mismatched_scope_never_queries_or_deletes(self):
        for attribute in ("provider", "account_id"):
            with self.subTest(attribute=attribute):
                provider = FakeProvider()
                setattr(provider, attribute, "unrelated")
                state = self.ledger.reconcile(provider, now=2500)
                self.assertEqual(state["status"], "pending_cleanup")
                self.assertEqual(provider.calls, [])

    def test_each_ownership_field_is_required(self):
        changes = [{"id": "54321"}, {"id": 12345}, {"name": "amd-comparison-v1"},
                   {"created_epoch": 999}, {"created_epoch": 1000.0},
                   {"tags": []}, {"tags": " ".join(BINDING.tags)}, {"tags": [None]}]
        changes.extend({"tags": [tag for tag in BINDING.tags if tag != missing]}
                       for missing in BINDING.tags)
        for change in changes:
            with self.subTest(change=change):
                provider = FakeProvider([Lookup(200, {**present().resource, **change})])
                state = self.ledger.reconcile(provider, now=2500)
                self.assertEqual(state["status"], "pending_cleanup")
                self.assertEqual(provider.calls, [("GET", "12345")])

    def test_invalid_lookup_never_means_absence_or_deletion(self):
        for response in (Lookup(401), Lookup(403), Lookup(429), Lookup(500), Lookup(302),
                         Lookup(200), Lookup(404, {}), Lookup("404"), None, {},
                         TimeoutError("secret-provider-detail")):
            with self.subTest(response=response):
                provider = FakeProvider([response])
                state = self.ledger.reconcile(provider, now=2500)
                self.assertEqual(state["status"], "pending_cleanup")
                self.assertEqual(provider.calls, [("GET", "12345")])
                self.assertNotIn("secret-provider-detail", str(state))

    def test_delete_error_or_404_still_requires_separate_absence_lookup(self):
        for status in (404, 403, 500, None, TimeoutError("secret")):
            with self.subTest(status=status):
                provider = FakeProvider([present(), Lookup(503)], status)
                state = self.ledger.reconcile(provider, now=2500)
                self.assertEqual(state["status"], "pending_cleanup")
                self.assertEqual(len(provider.calls), 3)
                self.assertNotIn("secret", str(state))

    def test_lost_delete_ack_can_complete_with_verified_absence(self):
        state = self.ledger.reconcile(FakeProvider(delete_status=TimeoutError()), now=2500)
        self.assertEqual(state["status"], "complete")
        self.assertIn("delete_error", [r["outcome"] for r in state["receipts"]])

    def test_verification_failure_remains_pending_past_hard_deadline(self):
        state = self.ledger.reconcile(FakeProvider([present(), TimeoutError()]), now=2800)
        self.assertEqual(state["status"], "pending_cleanup")
        self.assertTrue(state["deadline_exceeded"])

    def test_pending_cleanup_survives_clock_rollback(self):
        self.ledger.reconcile(FakeProvider([Lookup(500)]), now=2800)
        state = self.ledger.reconcile(FakeProvider([Lookup(500)]), now=1500)
        self.assertEqual(state["last_epoch"], 2800)
        self.assertTrue(state["deadline_exceeded"])
        self.assertEqual(state["status"], "pending_cleanup")

    def test_complete_is_terminal_without_more_provider_calls(self):
        self.ledger.reconcile(FakeProvider(), now=2500)
        provider = FakeProvider()
        state = self.ledger.reconcile(provider, now=2900)
        self.assertEqual(state["status"], "complete")
        self.assertEqual(provider.calls, [])

    def test_retry_rechecks_identity_instead_of_replaying_delete(self):
        self.ledger.reconcile(FakeProvider([present(), present()]), now=2500)
        changed = Lookup(200, {**present().resource, "tags": ["unrelated"]})
        provider = FakeProvider([changed])
        state = CleanupLedger(self.path, BINDING).reconcile(provider, now=2801)
        self.assertEqual(state["status"], "pending_cleanup")
        self.assertTrue(state["deadline_exceeded"])
        self.assertEqual(provider.calls, [("GET", "12345")])

    def test_interruption_is_not_swallowed_and_preserves_pending(self):
        with self.assertRaises(KeyboardInterrupt):
            self.ledger.reconcile(FakeProvider(delete_status=KeyboardInterrupt()), now=2500)
        state = CleanupLedger(self.path, BINDING).snapshot()
        self.assertEqual(state["status"], "pending_cleanup")
        self.assertEqual(state["receipts"][-1]["outcome"], "delete_requested")

    def test_pending_is_durable_before_lookup_and_delete(self):
        ledger = self.ledger

        class InspectProvider(FakeProvider):
            def lookup(self, resource_id):
                with sqlite3.connect(ledger.path) as db:
                    status = db.execute("SELECT status FROM cleanup").fetchone()[0]
                self_status.append(status)
                return super().lookup(resource_id)

            def delete(self, resource_id):
                with sqlite3.connect(ledger.path) as db:
                    outcome = db.execute("SELECT outcome FROM receipts ORDER BY sequence DESC").fetchone()[0]
                self_status.append(outcome)
                return super().delete(resource_id)

        self_status = []
        ledger.reconcile(InspectProvider(), now=2500)
        self.assertEqual(self_status, ["pending_cleanup", "delete_requested", "pending_cleanup"])

    def test_abrupt_controller_death_recovers_by_exact_id(self):
        process = multiprocessing.get_context("spawn").Process(
            target=crash_during_delete, args=(str(self.path),))
        process.start()
        process.join(timeout=10)
        if process.is_alive():
            process.kill()
            process.join()
            self.fail("child did not exit")
        self.assertEqual(process.exitcode, 17)
        reopened = CleanupLedger(self.path, BINDING)
        state = reopened.snapshot()
        self.assertEqual(state["status"], "pending_cleanup")
        self.assertEqual(state["receipts"][-1]["outcome"], "delete_requested")
        provider = FakeProvider([Lookup(404)])
        self.assertEqual(reopened.reconcile(provider, now=2600)["status"], "complete")
        self.assertEqual(provider.calls, [("GET", "12345")])

    def test_overlap_cannot_start_second_reconciliation(self):
        with self.ledger._locked():
            provider = FakeProvider()
            with self.assertRaisesRegex(CleanupDenied, "busy"):
                self.ledger.reconcile(provider, now=2500)
            self.assertEqual(provider.calls, [])

    def test_failed_initial_persistence_prevents_provider_calls(self):
        provider = FakeProvider()
        with patch.object(self.ledger, "_record", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                self.ledger.reconcile(provider, now=2500)
        self.assertEqual(provider.calls, [])

    def test_absence_receipt_write_failure_cannot_report_complete(self):
        record = self.ledger._record

        def fail_absence(*args, **kwargs):
            if kwargs.get("complete"):
                raise OSError("disk full")
            record(*args, **kwargs)

        with patch.object(self.ledger, "_record", side_effect=fail_absence):
            with self.assertRaises(OSError):
                self.ledger.reconcile(FakeProvider(), now=2500)
        self.assertEqual(CleanupLedger(self.path, BINDING).snapshot()["status"], "pending_cleanup")

    def test_missing_replaced_or_public_ledger_is_rejected(self):
        os.chmod(self.path, 0o644)
        with self.assertRaises(CleanupDenied):
            self.ledger.snapshot()
        os.chmod(self.path, 0o600)
        self.path.rename(self.path.with_suffix(".old"))
        with self.assertRaises(FileNotFoundError):
            self.ledger.snapshot()
        replacement = self.path.with_name("replacement")
        CleanupLedger.create(replacement, BINDING)
        replacement.rename(self.path)
        with self.assertRaisesRegex(CleanupDenied, "replaced"):
            self.ledger.snapshot()

    def test_missing_lock_is_not_recreated(self):
        self.ledger.lock_path.unlink()
        with self.assertRaises(FileNotFoundError):
            CleanupLedger(self.path, BINDING)
        self.assertFalse(self.ledger.lock_path.exists())

    def test_links_are_rejected(self):
        alias = self.path.with_name("alias")
        alias.symlink_to(self.path)
        with self.assertRaises(RuntimeError):
            CleanupLedger(alias, BINDING)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaisesRegex(CleanupDenied, "private_regular"):
            self.ledger.snapshot()

    def test_no_reset_rebind_or_comparison_campaign(self):
        with self.assertRaises(FileExistsError):
            CleanupLedger.create(self.path, BINDING)
        for field, value in (("resource_id", "6789"), ("allocation_id", "c" * 32),
                             ("plan_sha256", "d" * 64), ("account_id", "other"),
                             ("created_epoch", 2000)):
            with self.subTest(field=field), self.assertRaisesRegex(CleanupDenied, "binding"):
                CleanupLedger(self.path, dataclasses.replace(BINDING, **{field: value}))
        with self.assertRaises(ValueError):
            dataclasses.replace(BINDING, campaign="amd-comparison-v1")

    def test_corrupt_completion_or_schema_is_rejected(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE cleanup SET status='complete'")
        with self.assertRaisesRegex(CleanupDenied, "absence_receipt"):
            self.ledger.snapshot()
        with sqlite3.connect(self.path) as db:
            db.execute("PRAGMA user_version=2")
        with self.assertRaisesRegex(CleanupDenied, "schema"):
            self.ledger.snapshot()

    def test_invalid_identifiers_and_time_are_rejected(self):
        for field, value in (("provider", "other"), ("allocation_id", "../x"),
                             ("resource_id", "01"), ("resource_id", "1/2"),
                             ("plan_sha256", "invalid"), ("created_epoch", True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                dataclasses.replace(BINDING, **{field: value})
        for now in (True, 999, float("nan")):
            with self.subTest(now=now), self.assertRaises(ValueError):
                self.ledger.reconcile(FakeProvider(), now=now)


if __name__ == "__main__":
    unittest.main()
