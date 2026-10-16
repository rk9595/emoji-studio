import hashlib
import io
import multiprocessing
import sqlite3
import tempfile
import unittest
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from emoji_studio.service import MockRenderer, make_sticker
from emoji_studio.worker_queue import Conflict, LeaseLost, WorkerQueue


def competing_claim(path, worker):
    lease = WorkerQueue(path, clock=lambda: 100).claim(worker)
    return lease.job_id if lease else None


class WorkerQueueTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "queue.sqlite3"
        self.now = 100.0
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.queue.enqueue("job", "alice", ["apple"], [7])
        self.outputs = {"00-7.png": b"fake-png", "00-7.webp": b"fake-webp"}

    @staticmethod
    def hashes(outputs):
        return {name: hashlib.sha256(value).hexdigest() for name, value in outputs.items()}

    def complete(self, lease, outputs=None):
        outputs = self.outputs if outputs is None else outputs
        return self.queue.complete(lease, outputs, self.hashes(outputs))

    def test_idempotent_admission_and_conflicts(self):
        self.assertEqual(self.queue.enqueue("job", "alice", ["apple"], [7]), "job")
        for owner, prompt, seed, attempts in (
            ("bob", "apple", 7, 3),
            ("alice", "pear", 7, 3),
            ("alice", "apple", 8, 3),
            ("alice", "apple", 7, 4),
        ):
            with self.assertRaises(Conflict):
                self.queue.enqueue("job", owner, [prompt], [seed], max_attempts=attempts)

    def test_database_created_private_and_empty_queue_returns_none(self):
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        empty = WorkerQueue(self.path.parent / "empty.sqlite3")
        self.assertIsNone(empty.claim("worker"))
        self.assertEqual(empty.recover(), 0)

    def test_pack_requires_every_seed_and_ignores_mutated_lease_payload(self):
        self.queue.enqueue("pack", "alice", ["a", "b"], [7, 7])
        self.complete(self.queue.claim("worker"))
        lease = self.queue.claim("worker")
        lease.payload["seeds"] = [99]
        with self.assertRaises(ValueError):
            self.complete(lease)
        outputs = {
            f"{index:02d}-7.{extension}": b"data"
            for index in range(2)
            for extension in ("png", "webp")
        }
        self.assertEqual(len(self.complete(lease, outputs)), 4)

    def test_completion_cannot_resurrect_recovered_expired_work(self):
        lease = self.queue.claim("worker", ttl=1)
        self.now += 1
        self.queue.recover()
        with self.assertRaises(LeaseLost):
            self.complete(lease)
        self.assertEqual(self.queue.get("job", "alice")["status"], "queued")

    def test_claim_exclusion_and_secret_not_in_public_state(self):
        lease = self.queue.claim("worker-a")
        self.queue.enqueue("job-2", "alice", ["pear"], [8])
        self.assertIsNone(self.queue.claim("worker-b"))
        self.assertNotIn(lease.token, repr(lease))
        self.assertNotIn(lease.token, str(self.queue.get("job", "alice")))
        self.assertIsNone(self.queue.get("job", "bob"))
        self.complete(lease)
        self.assertEqual(self.queue.claim("worker-b").job_id, "job-2")

    def test_independent_processes_cannot_claim_two_jobs(self):
        for index in range(3):
            self.queue.enqueue(f"job-{index}", "alice", ["pear"], [index])
        with ProcessPoolExecutor(
            max_workers=3, mp_context=multiprocessing.get_context("spawn")
        ) as pool:
            claims = list(
                pool.map(competing_claim, [self.path] * 6, [f"worker-{i}" for i in range(6)])
            )
        self.assertEqual(sum(claim is not None for claim in claims), 1)

    def test_heartbeat_extends_without_shortening_and_survives_restart(self):
        lease = self.queue.claim("worker-a", ttl=20)
        self.now = 110
        self.assertEqual(self.queue.heartbeat(lease, ttl=30), 140)
        self.assertEqual(self.queue.heartbeat(lease, ttl=1), 140)
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.now = 121
        self.assertEqual(self.queue.recover(), 0)
        self.assertIsNone(self.queue.claim("worker-b"))
        self.complete(lease)
        self.assertEqual(self.queue.get("job", "alice")["status"], "succeeded")

    def test_exact_expiry_rejects_heartbeat_failure_and_completion(self):
        lease = self.queue.claim("worker-a", ttl=10)
        self.now = 110
        for operation in (
            lambda: self.queue.heartbeat(lease),
            lambda: self.complete(lease),
            lambda: self.queue.fail(lease),
        ):
            with self.assertRaises(LeaseLost):
                operation()
        self.assertEqual(self.queue.recover(), 1)
        self.assertEqual(self.queue.get("job", "alice")["artifacts"], {})

    def test_late_results_cannot_overwrite_replacement_worker(self):
        old = self.queue.claim("worker-a", ttl=10)
        self.now = 110
        current = self.queue.claim("worker-b")
        self.assertEqual(current.attempt, 2)
        self.assertNotEqual(old.token, current.token)
        self.complete(current)
        with self.assertRaises(LeaseLost):
            self.complete(old)
        self.assertEqual(self.queue.artifact("job", "alice", "00-7.png"), b"fake-png")

    def test_bounded_expirations_eventually_fail(self):
        for attempt in range(1, 4):
            self.assertEqual(self.queue.claim("worker", ttl=1).attempt, attempt)
            self.now += 1
            self.assertEqual(self.queue.recover(), 1)
        self.assertEqual(self.queue.get("job", "alice")["status"], "failed")
        self.assertIsNone(self.queue.claim("worker"))

    def test_retryable_failure_invalidates_old_token(self):
        lease = self.queue.claim("worker")
        self.assertEqual(self.queue.fail(lease, retryable=True), "queued")
        with self.assertRaises(LeaseLost):
            self.complete(lease)
        for expected in ("queued", "failed"):
            self.assertEqual(self.queue.fail(self.queue.claim("worker"), retryable=True), expected)

    def test_nonretryable_failure_terminal_and_forged_lease_rejected(self):
        lease = self.queue.claim("worker")
        for forged in (
            replace(lease, token="wrong"),
            replace(lease, worker_id="other"),
            replace(lease, attempt=2),
        ):
            with self.assertRaises(LeaseLost):
                self.complete(forged)
        self.assertEqual(self.queue.fail(lease), "failed")
        self.assertIsNone(self.queue.claim("worker"))

    def test_duplicate_completion_survives_restart_but_cannot_change_content(self):
        lease = self.queue.claim("worker")
        manifest = self.complete(lease)
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.now = 10000
        self.assertEqual(self.complete(lease), manifest)
        changed = {**self.outputs, "00-7.png": b"different"}
        with self.assertRaises(Conflict):
            self.complete(lease, changed)
        self.assertIsNone(self.queue.artifact("job", "bob", "00-7.png"))
        self.assertIsNone(self.queue.artifact("job", "alice", "../queue.sqlite3"))

    def test_invalid_or_partial_pack_never_commits(self):
        lease = self.queue.claim("worker")
        for outputs in (
            {},
            {"00-7.png": b"x"},
            {"../bad.png": b"x", "00-7.webp": b"y"},
            {"00-8.png": b"x", "00-8.webp": b"y"},
            {**self.outputs, "extra": b"x"},
        ):
            with self.assertRaises(ValueError):
                self.complete(lease, outputs)
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.queue.complete(lease, self.outputs, dict.fromkeys(self.outputs, "incorrect"))
        with patch("emoji_studio.worker_queue.MAX_OUTPUT_BYTES", 1):
            with self.assertRaisesRegex(ValueError, "byte limit"):
                self.complete(lease)
        self.assertEqual(self.queue.get("job", "alice")["status"], "running")
        self.assertEqual(self.queue.get("job", "alice")["artifacts"], {})

    def test_interrupted_output_transaction_rolls_back_all_outputs_and_status(self):
        lease = self.queue.claim("worker")
        with sqlite3.connect(self.path) as connection:
            connection.execute("""CREATE TRIGGER interrupt_commit BEFORE INSERT ON artifacts
                WHEN NEW.name LIKE '%.webp' BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")
        with self.assertRaises(sqlite3.IntegrityError):
            self.complete(lease)
        self.queue = WorkerQueue(self.path, clock=lambda: self.now)
        self.assertEqual(self.queue.get("job", "alice")["artifacts"], {})
        self.assertEqual(self.queue.get("job", "alice")["status"], "running")
        with sqlite3.connect(self.path) as connection:
            connection.execute("DROP TRIGGER interrupt_commit")
        self.complete(lease)

    def test_corrupt_stored_bytes_fail_closed(self):
        self.complete(self.queue.claim("worker"))
        with sqlite3.connect(self.path) as connection:
            connection.execute(
                "UPDATE artifacts SET content=? WHERE name=?", (b"corrupt", "00-7.png")
            )
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.queue.artifact("job", "alice", "00-7.png")

    def test_simulated_renderer_full_pack_roundtrip(self):
        lease = self.queue.claim("simulated-worker")
        image, _ = MockRenderer().render(lease.payload["prompts"][0], lease.payload["seeds"][0])
        image = make_sticker(image)
        outputs = {}
        for extension in ("png", "webp"):
            buffer = io.BytesIO()
            image.save(buffer, format=extension.upper(), lossless=True)
            outputs[f"00-7.{extension}"] = buffer.getvalue()
        self.complete(lease, outputs)
        for name in outputs:
            content = self.queue.artifact("job", "alice", name)
            with Image.open(io.BytesIO(content)) as result:
                self.assertEqual(result.mode, "RGBA")
                self.assertEqual(result.size, (512, 512))
                self.assertEqual(result.getpixel((0, 0))[3], 0)

    def test_invalid_admission_clock_and_ttl(self):
        for prompts, seeds in (
            ([], []),
            ([" "], [1]),
            (["a"], [True]),
            (["a"], [-1]),
            (["a"], [2**32]),
            (["a"], []),
            (["a"] * 17, [1] * 17),
        ):
            with self.assertRaises(ValueError):
                self.queue.enqueue("invalid", "alice", prompts, seeds)
        with self.assertRaises(ValueError):
            self.queue.enqueue("../bad", "alice", ["a"], [0])
        for ttl in (0, -1, True, 1.5, 3601):
            with self.assertRaises(ValueError):
                self.queue.claim("worker", ttl=ttl)
        self.now = float("nan")
        with self.assertRaises(ValueError):
            self.queue.claim("worker")
