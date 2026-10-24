import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path
from threading import Event
from unittest.mock import Mock, patch

from emoji_studio.render_budget import BudgetDenied, RenderBudget

PLAN = "a" * 64
REQUEST = "b" * 64
IDENTITY = {"allocation_id": "offline-fixture", "plan_sha256": PLAN}


def race_call(arguments):
    path, number, duplicate = arguments
    budget = RenderBudget(path, **IDENTITY)
    call_id = "same-call" if duplicate else f"call-{number}"

    def render():
        (Path(path).parent / f"physical-{number}").write_text("one fake render")
        return number

    try:
        budget.run(call_id, REQUEST, render)
        return "succeeded"
    except BudgetDenied:
        return "denied"


def crash_after_consumption(path):
    budget = RenderBudget(path, **IDENTITY)

    def crash():
        (Path(path).parent / "physical-crash").write_text("entered fake render")
        os._exit(17)

    budget.run("crash", REQUEST, crash)


class RenderBudgetTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.path = self.root / "budget.sqlite3"
        self.budget = RenderBudget.create(self.path, **IDENTITY)

    def reopen(self):
        return RenderBudget(self.path, **IDENTITY)

    def test_commit_precedes_callback_and_third_call_never_invokes(self):
        def render():
            snapshot = self.reopen().snapshot()
            self.assertEqual(snapshot["consumed"], 1)
            self.assertEqual(snapshot["calls"][0]["state"], "reserved")
            self.assertTrue(snapshot["further_calls_blocked"])
            return "output"

        self.assertEqual(self.budget.run("first", REQUEST, render), "output")
        self.assertEqual(self.reopen().run("second", REQUEST, lambda: "two"), "two")
        callback = Mock()
        with self.assertRaisesRegex(BudgetDenied, "limit"):
            self.reopen().run("third", REQUEST, callback)
        callback.assert_not_called()
        self.assertEqual(self.reopen().snapshot()["consumed"], 2)

    def test_duplicate_call_is_never_replayed_or_refunded(self):
        self.budget.run("first", REQUEST, lambda: None)
        callback = Mock()
        for fingerprint in (REQUEST, "c" * 64):
            with self.subTest(fingerprint=fingerprint), self.assertRaisesRegex(BudgetDenied, "already"):
                self.reopen().run("first", fingerprint, callback)
        callback.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 1)

    def test_running_call_blocks_second_thread_without_consuming_capacity(self):
        started, release = Event(), Event()

        def render():
            started.set()
            if not release.wait(5):
                raise TimeoutError("test release")

        with ThreadPoolExecutor(max_workers=1) as pool:
            first = pool.submit(self.budget.run, "first", REQUEST, render)
            try:
                self.assertTrue(started.wait(3))
                callback = Mock()
                with self.assertRaisesRegex(BudgetDenied, "unresolved"):
                    self.reopen().run("second", REQUEST, callback)
                callback.assert_not_called()
                self.assertEqual(self.reopen().snapshot()["consumed"], 1)
            finally:
                release.set()
            first.result(timeout=3)
        self.reopen().run("second", REQUEST, lambda: None)

    def test_callback_failures_and_interruptions_halt_without_refund(self):
        for index, error in enumerate((RuntimeError("secret-detail"), KeyboardInterrupt(), SystemExit(7))):
            with self.subTest(error=type(error).__name__):
                path = self.root / f"failure-{index}.sqlite3"
                budget = RenderBudget.create(path, **IDENTITY)
                with self.assertRaises(type(error)):
                    budget.run("first", REQUEST, Mock(side_effect=error))
                reopened = RenderBudget(path, **IDENTITY)
                snapshot = reopened.snapshot()
                self.assertEqual(snapshot["consumed"], 1)
                self.assertEqual(snapshot["unused"], 1)
                self.assertEqual(snapshot["calls"][0]["state"], "failed")
                self.assertNotIn("secret-detail", str(snapshot))
                with self.assertRaisesRegex(BudgetDenied, "failed"):
                    reopened.run("second", REQUEST, lambda: self.fail("must not render"))

    def test_abrupt_process_death_keeps_reservation_and_blocks_restart(self):
        context = multiprocessing.get_context("spawn")
        process = context.Process(target=crash_after_consumption, args=(self.path,))
        process.start()
        try:
            process.join(10)
            self.assertEqual(process.exitcode, 17)
        finally:
            if process.is_alive():
                process.kill()
                process.join(3)
        self.assertTrue((self.root / "physical-crash").exists())
        snapshot = self.reopen().snapshot()
        self.assertEqual(snapshot["consumed"], 1)
        self.assertEqual(snapshot["calls"][0]["state"], "reserved")
        callback = Mock()
        with self.assertRaises(BudgetDenied):
            self.reopen().run("replacement", REQUEST, callback)
        callback.assert_not_called()

    def test_consumed_but_never_started_call_still_blocks(self):
        self.budget._reserve("first", REQUEST)
        callback = Mock()
        with self.assertRaises(BudgetDenied):
            self.reopen().run("first", REQUEST, callback)
        with self.assertRaises(BudgetDenied):
            self.reopen().run("second", REQUEST, callback)
        callback.assert_not_called()
        self.assertEqual(self.reopen().snapshot()["consumed"], 1)

    def test_process_race_never_exceeds_two_physical_invocations(self):
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            outcomes = list(pool.map(race_call, [(self.path, i, False) for i in range(12)]))
        count = len(list(self.root.glob("physical-*")))
        self.assertGreater(count, 0)
        self.assertLessEqual(count, 2)
        self.assertEqual(outcomes.count("succeeded"), count)
        self.assertEqual(self.reopen().snapshot()["consumed"], count)
        if count == 1:
            self.reopen().run("fill-second", REQUEST, lambda: None)
        with self.assertRaises(BudgetDenied):
            self.reopen().run("third", REQUEST, lambda: self.fail("must not render"))

    def test_duplicate_process_race_invokes_exactly_once(self):
        with ProcessPoolExecutor(max_workers=4, mp_context=multiprocessing.get_context("spawn")) as pool:
            outcomes = list(pool.map(race_call, [(self.path, i, True) for i in range(12)]))
        self.assertEqual(outcomes.count("succeeded"), 1)
        self.assertEqual(len(list(self.root.glob("physical-*"))), 1)
        self.assertEqual(self.reopen().snapshot()["consumed"], 1)

    def test_reservation_failure_rolls_back_without_invoking(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER reject_reserve BEFORE INSERT ON calls
                BEGIN SELECT RAISE(ABORT, 'injected failure'); END""")
        callback = Mock()
        with self.assertRaises(sqlite3.IntegrityError):
            self.budget.run("first", REQUEST, callback)
        callback.assert_not_called()
        self.assertEqual(self.reopen().snapshot()["consumed"], 0)
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TRIGGER reject_reserve")
        self.budget.run("first", REQUEST, lambda: None)

    def test_lost_commit_acknowledgement_never_invokes_or_refunds(self):
        connect = sqlite3.connect

        class LostAcknowledgement(sqlite3.Connection):
            def commit(self):
                super().commit()
                raise sqlite3.OperationalError("commit acknowledgement lost")

        def ambiguous_connection(*args, **kwargs):
            return connect(*args, **kwargs, factory=LostAcknowledgement)

        callback = Mock()
        with patch("emoji_studio.render_budget.sqlite3.connect", side_effect=ambiguous_connection):
            with self.assertRaises(sqlite3.OperationalError):
                self.budget.run("first", REQUEST, callback)
        callback.assert_not_called()
        snapshot = self.reopen().snapshot()
        self.assertEqual(snapshot["consumed"], 1)
        self.assertEqual(snapshot["calls"][0]["state"], "reserved")
        with self.assertRaises(BudgetDenied):
            self.reopen().run("second", REQUEST, callback)
        callback.assert_not_called()

    def test_completion_storage_failure_discards_result_and_blocks(self):
        callback = Mock(return_value="unpublished output")
        with patch.object(self.budget, "_finish", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaises(sqlite3.OperationalError):
                self.budget.run("first", REQUEST, callback)
        callback.assert_called_once()
        snapshot = self.reopen().snapshot()
        self.assertEqual(snapshot["consumed"], 1)
        self.assertEqual(snapshot["calls"][0]["state"], "reserved")
        with self.assertRaises(BudgetDenied):
            self.reopen().run("second", REQUEST, callback)
        callback.assert_called_once()

    def test_failure_recording_error_also_preserves_consumption(self):
        with patch.object(self.budget, "_finish", side_effect=sqlite3.OperationalError("disk full")):
            with self.assertRaisesRegex(RuntimeError, "render failed"):
                self.budget.run("first", REQUEST, Mock(side_effect=RuntimeError("render failed")))
        self.assertTrue(self.reopen().snapshot()["further_calls_blocked"])
        self.assertEqual(self.reopen().snapshot()["calls"][0]["state"], "reserved")

    def test_identity_or_campaign_changes_cannot_reset_budget(self):
        self.budget.run("first", REQUEST, lambda: None)
        for changed in ({"allocation_id": "different"}, {"plan_sha256": "d" * 64}):
            with self.subTest(changed=changed), self.assertRaises(BudgetDenied):
                RenderBudget(self.path, **{**IDENTITY, **changed})
        with self.assertRaises(ValueError):
            RenderBudget.create(self.root / "forbidden.sqlite3", campaign="amd-comparison-v1", **IDENTITY)
        self.assertFalse((self.root / "forbidden.sqlite3").exists())
        with self.assertRaises(FileExistsError):
            RenderBudget.create(self.path, **IDENTITY)
        self.assertEqual(self.reopen().snapshot()["consumed"], 1)

    def test_missing_empty_future_or_corrupt_database_never_initialized(self):
        missing = self.root / "missing.sqlite3"
        with self.assertRaises(FileNotFoundError):
            RenderBudget(missing, **IDENTITY)
        self.assertFalse(missing.exists())
        empty = self.root / "empty.sqlite3"
        empty.touch(mode=0o600)
        with self.assertRaises(BudgetDenied):
            RenderBudget(empty, **IDENTITY)
        self.assertEqual(empty.read_bytes(), b"")
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA user_version=99")
        with self.assertRaises(BudgetDenied):
            self.reopen()
        corrupt = self.root / "corrupt.sqlite3"
        corrupt.write_bytes(b"not a sqlite database")
        corrupt.chmod(0o600)
        with self.assertRaises(sqlite3.DatabaseError):
            RenderBudget(corrupt, **IDENTITY)

    def test_missing_policy_or_usage_rows_fail_closed(self):
        self.budget.run("first", REQUEST, lambda: None)
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM calls")
        with self.assertRaisesRegex(BudgetDenied, "accounting"):
            self.reopen()
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM budget")
        with self.assertRaisesRegex(BudgetDenied, "policy"):
            self.reopen()

    def test_symlink_hardlink_or_public_permissions_rejected(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        alias = self.root / "alias.sqlite3"
        alias.symlink_to(self.path)
        with self.assertRaises(BudgetDenied):
            RenderBudget(alias, **IDENTITY)
        alias.unlink()
        os.link(self.path, alias)
        with self.assertRaises(BudgetDenied):
            self.reopen()
        alias.unlink()
        self.path.chmod(0o644)
        with self.assertRaises(BudgetDenied):
            self.reopen()

    def test_deleted_or_replaced_ledger_is_not_recreated(self):
        self.path.rename(self.root / "old.sqlite3")
        callback = Mock()
        with self.assertRaises(FileNotFoundError):
            self.budget.run("first", REQUEST, callback)
        self.assertFalse(self.path.exists())
        RenderBudget.create(self.path, **IDENTITY)
        with self.assertRaisesRegex(BudgetDenied, "replaced"):
            self.budget.run("first", REQUEST, callback)
        callback.assert_not_called()

    def test_invalid_call_never_consumes(self):
        callback = Mock()
        for call_id, fingerprint in (("", REQUEST), ("has spaces", REQUEST), ("x", "bad")):
            with self.subTest(call_id=call_id), self.assertRaises(ValueError):
                self.budget.run(call_id, fingerprint, callback)
        with self.assertRaises(ValueError):
            self.budget.run("first", REQUEST, None)
        callback.assert_not_called()
        self.assertEqual(self.budget.snapshot()["consumed"], 0)
