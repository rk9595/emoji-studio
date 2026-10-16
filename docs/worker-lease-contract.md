# Offline worker contract v2 — October 16, 2026

Implemented in `src/emoji_studio/worker_queue.py`, tested in
`tests/test_worker_queue.py`. This is a standalone, local control-plane building
block. The current FastAPI/GenerationWorker path is unchanged and does not use it.
No remote endpoints, database services or GPUs are provisioned.

## State and authority

```text
queued --claim--> running --complete--> succeeded
                    |
                    +--retryable failure/expiry--> queued (attempts remain)
                    +--permanent failure/limit---> failed
```

`enqueue` atomically admits a logical job and reserves image usage in the same
SQLite transaction. It accepts the job ID, owner, prompts/seeds and a trusted
control-plane daily limit (1–1,000 images, default 1,000). The global lifetime
trial cap is persisted on first database creation (default 100); reopening with
a different explicit cap fails rather than silently changing policy.

An immutable usage ledger counts admitted images, including queued, failed and
retried jobs. Daily limits use UTC calendar days; the global trial count never
resets on a day boundary. Existing alpha semantics are preserved: failures do
not refund usage, and retries do not charge again. Concurrent processes cannot
oversubscribe either limit. Clock rollback before the latest admission fails
closed for new admissions and usage reads. An identical repeated admission is
acknowledged even if limits have since been exhausted/lowered; changed content
under the same ID fails. Rejected packs reserve nothing, including partial packs.

`usage` returns daily and trial counts/remaining values and the daily reset epoch.
`QuotaExceeded` distinguishes daily and trial rejection for a future API adapter.
Only trusted code supplies policy values; never accept limits from a request body.
The upcoming API integration must use this atomic admission method directly,
not separately check a file-backed counter and then enqueue.

`delete` removes only the caller-owned terminal job and its output blobs, in one
transaction. Queued/running jobs cannot be deleted. Minimal ledger metadata
(owner, job ID, image count, admission epoch, payload hash and attempt limit)
survives, without prompts, output bytes or lease tokens. The retained ID prevents
deleted requests from being replayed as free work. Deletion is logical, not
secure erasure of SQLite pages or backups; no deletion of existing user data or
background retention has been performed during implementation.

New databases use schema version 2. Legacy/unversioned databases with tables,
future schema versions, missing policy/ledger structures and broken references
fail closed. There is no automatic migration or accounting backfill. Keep old
databases intact and design an explicit migration before using their jobs.
The schema ties active job records to their usage reservation with a foreign key.
No money is reserved by this image ledger; dispatcher spend accounting is separate.

`claim` recovers expired work and returns an opaque token, attempt number and
expiry. A database constraint permits only one running job across all connections
and processes. Each reclaimed attempt gets a new token. `heartbeat` extends a
live lease without shortening it. At the exact expiry instant, heartbeat,
completion and worker-reported failure are rejected; old workers cannot revive
or overwrite a newer attempt. Failure diagnostics must be bounded and non-secret.

The queue uses the control plane's epoch clock, not worker-supplied timestamps.
It assumes a reliable host clock. TTL is 1–3,600 seconds, default 60; attempts are
bounded at admission (default three). Heartbeats do not impose a total-runtime
deadline: provider cost/time limits remain a separate dispatcher obligation.

## Output commit and replay

A completed pack must contain exactly one PNG and one WebP for every admitted
seed/index. Supplied byte hashes must match; total payload is capped at 64 MiB.
Outputs and succeeded state commit in one SQLite transaction. A failed insert
rolls back every output and the status change. A lost completion response can be
retried with the same token and identical bytes after restart, even if its former
lease time has elapsed. Changed outputs are rejected, never overwritten.

Output blobs are deliberately stored inside this local database to make the
initial atomicity boundary testable without a new external service. A future
object-store adapter must upload immutable content, verify it, and atomically
publish its manifest before acknowledging completion. Unreferenced uploads need
garbage collection; do not claim a multi-system transaction without implementing it.

Owner-scoped `get` and `artifact` calls hide another owner's job/output. Public
state and lease reprs do not expose fencing tokens. Artifact reads recheck hashes.
New databases use owner-only permissions. Existing database permissions and private
directory access remain the operator's responsibility.

## Guarantees and explicit limits

- Process restarts preserve active leases, attempts and committed outputs.
- Expired leases are recovered on explicit reconciliation or the next claim.
  No background reconciliation service is installed by this module.
- Execution can repeat after interruption; this is **not exactly-once rendering**.
  Fencing provides one accepted completion for a logical job.
- Lease expiry does not kill a GPU process or stop billing. The dispatcher must
  terminate/reconcile the old resource before allocating a replacement if the
  physical one-GPU limit is to hold.
- SQLite serialization is for one durable host filesystem, not a shared network
  filesystem or replicated multi-host database. Disk loss still needs backups.
- Trusted control-plane methods accept worker results. Before remote exposure,
  add worker authentication, request size limits, image decoding/metadata checks,
  model/adapter identity checks and a controlled transport. Hash integrity alone
  does not prove that a blob is a valid image or the intended generation.
- Automatic retention, financial reservations, migrations and API wiring are
  not implemented here. Keep the existing service until integration tests pass.

Tests simulate renderer exports, separate-process claim races, restarts,
heartbeat renewal, exact expiry, retries, stale/forged authority, duplicate and
conflicting completion, output corruption and mid-transaction failure. Admission
tests also cover competing daily/trial requests, simultaneous duplicate requests,
UTC rollover, clock regression, persistence after deletion and transactional rollback.
