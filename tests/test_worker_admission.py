import hashlib
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from emoji_studio.worker_queue import Conflict, QuotaExceeded, WorkerQueue


def admit_in_process(arguments):
    path, job_id, owner, limit = arguments
    queue = WorkerQueue(path, clock=lambda: 100)
    try:
        queue.enqueue(job_id, owner, ["apple"], [7], daily_image_quota=limit)
        return "admitted"
    except QuotaExceeded as error:
        return error.scope


def keyed_admit_in_process(arguments):
    path, index, request_hash = arguments
    queue = WorkerQueue(path, clock=lambda: 100)
    try:
        return queue.enqueue(f"candidate-{index}", "alice", ["apple"], [index],
                             daily_image_quota=1, idempotency=("a" * 64, request_hash))
    except Conflict:
        return "conflict"


class AdmissionTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "queue.sqlite3"
        self.now = 100.0
        self.queue = WorkerQueue(self.path, clock=lambda: self.now, trial_image_cap=4)

    def enqueue(self, job="job", owner="alice", count=1, limit=2):
        return self.queue.enqueue(
            job, owner, ["apple"] * count, [7] * count, daily_image_quota=limit
        )

    def usage(self, owner="alice", limit=2):
        return self.queue.usage(owner, daily_image_quota=limit)

    def counts(self):
        with sqlite3.connect(self.path) as connection:
            return tuple(
                connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in ("jobs", "usage_ledger", "artifacts")
            )

    def complete(self):
        lease = self.queue.claim("worker")
        outputs = {
            f"{index:02d}-{seed}.{extension}": b"test-data"
            for index, seed in enumerate(lease.payload["seeds"])
            for extension in ("png", "webp")
        }
        self.queue.complete(
            lease,
            outputs,
            {name: hashlib.sha256(value).hexdigest() for name, value in outputs.items()},
        )
        return lease

    def test_daily_limit_and_pack_rejection_are_atomic(self):
        self.enqueue(count=2)
        with self.assertRaises(QuotaExceeded) as rejected:
            self.enqueue("over-limit")
        self.assertEqual(rejected.exception.scope, "daily")
        self.assertEqual(rejected.exception.resets_at, 86400)
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.usage()["daily"]["used"], 2)
        self.assertIsNone(self.queue.get("over-limit", "alice"))

    def test_oversized_first_pack_does_not_consume_partial_usage(self):
        with self.assertRaises(QuotaExceeded):
            self.enqueue(count=3)
        self.assertEqual(self.counts(), (0, 0, 0))
        self.assertEqual(self.usage()["trial"]["used"], 0)

    def test_trial_limit_is_global_across_owners(self):
        self.enqueue("alice-job", count=2)
        self.enqueue("bob-job", "bob", count=2)
        with self.assertRaises(QuotaExceeded) as rejected:
            self.enqueue("carol-job", "carol")
        self.assertEqual(rejected.exception.scope, "trial")
        self.assertIsNone(rejected.exception.resets_at)
        self.assertEqual(self.usage("carol")["daily"]["used"], 0)
        self.assertEqual(self.usage("carol")["trial"]["used"], 4)

    def test_idempotency_does_not_recharge_at_exhausted_or_lowered_limits(self):
        self.enqueue(count=2)
        self.assertEqual(self.enqueue(count=2, limit=1), "job")
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.usage(limit=1)["daily"]["remaining"], 0)
        with self.assertRaises(Conflict):
            self.enqueue(count=1)

    def test_retry_and_terminal_failure_keep_one_reservation(self):
        self.enqueue()
        for _ in range(3):
            self.queue.fail(self.queue.claim("worker"), retryable=True)
        self.assertEqual(self.queue.get("job", "alice")["status"], "failed")
        self.assertEqual(self.usage()["trial"]["used"], 1)
        self.assertEqual(self.usage()["daily"]["used"], 1)

    def test_expiry_and_restart_keep_one_reservation(self):
        self.enqueue()
        self.queue.claim("worker", ttl=1)
        self.now += 1
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.queue.recover()
        self.complete()
        self.assertEqual(self.usage()["daily"]["used"], 1)
        self.assertEqual(self.counts(), (1, 1, 2))

    def test_delete_content_keeps_usage_and_prevents_id_reuse(self):
        self.enqueue(count=2)
        lease = self.complete()
        self.assertFalse(self.queue.delete("job", "bob"))
        self.assertTrue(self.queue.delete("job", "alice"))
        self.assertFalse(self.queue.delete("job", "alice"))
        self.assertEqual(self.counts(), (0, 1, 0))
        self.assertIsNone(self.queue.get("job", "alice"))
        self.assertIsNone(self.queue.artifact("job", "alice", "00-7.png"))
        self.assertEqual(self.usage()["daily"]["used"], 2)
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.assertEqual(self.usage()["trial"]["used"], 2)
        with self.assertRaisesRegex(Conflict, "Deleted"):
            self.enqueue(count=2)
        with self.assertRaises(QuotaExceeded):
            self.enqueue("new-id")
        self.assertNotIn(lease.token, repr(self.usage()))
        with sqlite3.connect(self.path) as connection:
            ledger = connection.execute("SELECT * FROM usage_ledger").fetchone()
        self.assertNotIn("apple", repr(ledger))

    def test_delete_failed_job_does_not_refund(self):
        self.enqueue()
        self.queue.fail(self.queue.claim("worker"))
        self.assertTrue(self.queue.delete("job", "alice"))
        self.assertEqual(self.usage()["trial"]["used"], 1)

    def test_cannot_delete_queued_or_running_work(self):
        self.enqueue()
        with self.assertRaises(Conflict):
            self.queue.delete("job", "alice")
        self.queue.claim("worker")
        with self.assertRaises(Conflict):
            self.queue.delete("job", "alice")
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_utc_day_boundary_resets_daily_but_not_trial(self):
        self.now = 86399.9
        self.enqueue(count=2)
        self.now = 86400
        self.assertEqual(self.usage()["daily"]["used"], 0)
        self.assertEqual(self.usage()["daily"]["resets_at"], 172800)
        self.enqueue("next-day", count=2)
        self.assertEqual(self.usage()["trial"]["used"], 4)
        self.now = 172800
        with self.assertRaises(QuotaExceeded) as rejected:
            self.enqueue("third-day")
        self.assertEqual(rejected.exception.scope, "trial")

    def test_clock_regression_fails_closed_for_new_admission(self):
        self.enqueue()
        self.now -= 1
        with self.assertRaisesRegex(ValueError, "clock"):
            self.enqueue("new")
        with self.assertRaisesRegex(ValueError, "clock"):
            self.usage()
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_job_insert_failure_rolls_back_ledger(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER interrupt_admission BEFORE INSERT ON jobs
                BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.enqueue()
        self.assertEqual(self.counts(), (0, 0, 0))
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TRIGGER interrupt_admission")
        self.enqueue()
        self.assertEqual(self.usage()["daily"]["used"], 1)

    def test_delete_failure_rolls_back_outputs_and_job(self):
        self.enqueue()
        self.complete()
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER interrupt_delete BEFORE DELETE ON jobs
                BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.queue.delete("job", "alice")
        self.assertEqual(self.counts(), (1, 1, 2))

    def process_admissions(self, jobs):
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            return list(pool.map(admit_in_process, [(self.path, *job) for job in jobs]))

    def test_concurrent_daily_admissions_never_oversubscribe(self):
        results = self.process_admissions([(f"job-{i}", "alice", 2) for i in range(8)])
        self.assertEqual(results.count("admitted"), 2)
        self.assertEqual(results.count("daily"), 6)
        self.assertEqual(self.usage()["daily"]["used"], 2)

    def test_concurrent_trial_admissions_never_oversubscribe(self):
        results = self.process_admissions([(f"job-{i}", f"owner-{i}", 2) for i in range(8)])
        self.assertEqual(results.count("admitted"), 4)
        self.assertEqual(results.count("trial"), 4)
        self.assertEqual(self.usage()["trial"]["used"], 4)

    def test_concurrent_identical_admissions_charge_once(self):
        results = self.process_admissions([("job", "alice", 2)] * 8)
        self.assertEqual(results.count("admitted"), 8)
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_persisted_trial_policy_cannot_be_silently_reconfigured(self):
        with self.assertRaises(Conflict):
            WorkerQueue(self.path, trial_image_cap=100)
        reopened = WorkerQueue(self.path)
        self.assertEqual(reopened.usage("alice")["trial"]["limit"], 4)
        self.assertEqual(
            WorkerQueue(self.path, trial_image_cap=4).usage("alice")["trial"]["limit"], 4
        )

    def test_missing_policy_or_ledger_and_future_schema_fail_closed(self):
        for corruption in (
            "DELETE FROM queue_settings",
            "DROP TABLE usage_ledger",
            "DROP TABLE idempotency",
            "PRAGMA user_version=99",
        ):
            path = self.path.parent / (hashlib.sha256(corruption.encode()).hexdigest() + ".sqlite3")
            WorkerQueue(path)
            with sqlite3.connect(path) as connection:
                connection.execute(corruption)
            with self.assertRaises(ValueError):
                WorkerQueue(path)

    def test_schema_three_is_refused_without_changing_existing_data(self):
        self.enqueue()
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TABLE idempotency")
            connection.execute("PRAGMA user_version=3")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(ValueError, "schema"):
            WorkerQueue(self.path)
        self.assertEqual(self.path.read_bytes(), before)

    def test_keyed_process_race_preserves_first_seed_and_single_charge(self):
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            ids = list(pool.map(keyed_admit_in_process,
                                [(self.path, i, "b" * 64) for i in range(8)]))
        self.assertEqual(len(set(ids)), 1)
        winner = int(ids[0].split("-")[1])
        self.assertEqual(self.queue.get(ids[0], "alice")["payload"]["seeds"], [winner])
        self.assertEqual(self.counts(), (1, 1, 0))
        self.assertEqual(self.usage()["trial"]["used"], 1)

    def test_keyed_conflicting_process_race_has_one_winner(self):
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("spawn"),
        ) as pool:
            results = list(pool.map(keyed_admit_in_process,
                                    [(self.path, i, f"{i:064x}") for i in range(8)]))
        self.assertEqual(results.count("conflict"), 7)
        self.assertEqual(self.counts(), (1, 1, 0))

    def test_key_insert_failure_rolls_back_admission_and_can_retry(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER interrupt_key BEFORE INSERT ON idempotency
                BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.queue.enqueue("job", "alice", ["apple"], [7],
                               idempotency=("a" * 64, "b" * 64))
        self.assertEqual(self.counts(), (0, 0, 0))
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM idempotency").fetchone()[0], 0)
            connection.execute("DROP TRIGGER interrupt_key")
        self.assertEqual(self.queue.enqueue("job", "alice", ["apple"], [7],
                                            idempotency=("a" * 64, "b" * 64)), "job")

    def test_retention_preserves_key_tombstone(self):
        self.queue.enqueue("job", "alice", ["apple"], [7], idempotency=("a" * 64, "b" * 64))
        self.complete()
        self.assertEqual(self.queue.delete_expired(101), ["job"])
        reopened = WorkerQueue(self.path)
        with self.assertRaisesRegex(Conflict, "deleted"):
            reopened.enqueue("retry", "alice", ["apple"], [9],
                             idempotency=("a" * 64, "b" * 64))
        self.assertEqual(self.counts(), (0, 1, 0))

    def test_rejected_quota_does_not_consume_key(self):
        with self.assertRaises(QuotaExceeded):
            self.queue.enqueue("job", "alice", ["apple"] * 2, [7, 8], daily_image_quota=1,
                               idempotency=("a" * 64, "b" * 64))
        self.assertEqual(self.queue.enqueue("job", "alice", ["apple"], [7],
                                            idempotency=("a" * 64, "c" * 64)), "job")

    def test_nonempty_legacy_queue_is_not_silently_migrated(self):
        self.enqueue()
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TABLE usage_ledger")
            connection.execute("DROP TABLE queue_settings")
            connection.execute("PRAGMA user_version=0")
        with self.assertRaisesRegex(ValueError, "explicit.*migration"):
            WorkerQueue(self.path)
        with sqlite3.connect(self.path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(connection.execute("PRAGMA user_version").fetchone()[0], 0)

    def test_even_empty_legacy_schema_requires_explicit_migration(self):
        with sqlite3.connect(self.path) as connection:
            connection.execute("PRAGMA user_version=0")
        with self.assertRaisesRegex(ValueError, "explicit.*migration"):
            WorkerQueue(self.path)

    def test_invalid_limits_do_not_create_jobs_or_usage(self):
        for value in (0, -1, True, 1.5, 1001):
            with self.assertRaises(ValueError):
                self.enqueue(limit=value)
        self.assertEqual(self.counts(), (0, 0, 0))
        for value in (0, True, 100001):
            with self.assertRaises(ValueError):
                WorkerQueue(self.path, trial_image_cap=value)

    def test_database_rejects_job_without_usage_reservation(self):
        with self.assertRaises(sqlite3.IntegrityError), self.queue._transaction() as connection:
            connection.execute("""INSERT INTO jobs
                (id,owner,payload,status,max_attempts,created,updated)
                VALUES ('unaccounted','alice','{}','queued',3,100,100)""")
        self.assertEqual(self.counts(), (0, 0, 0))

    def test_missing_usage_row_is_detected_on_reopen(self):
        self.enqueue()
        # Simulate out-of-band corruption with SQLite FK enforcement disabled.
        with sqlite3.connect(self.path) as connection:
            connection.execute("DELETE FROM usage_ledger")
        with self.assertRaisesRegex(ValueError, "Inconsistent"):
            WorkerQueue(self.path)
