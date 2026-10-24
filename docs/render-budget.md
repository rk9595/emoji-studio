# Two-render smoke guard — October 24, 2026

`emoji_studio.render_budget.RenderBudget` is an offline-tested component for the
proposed `amd-api-smoke-v1` executor. It permits at most two guarded render
invocations on one trusted local ledger, and stops all further calls after an
unresolved or failed attempt. It contains no GPU imports, provider clients or
spending authorization. The dedicated [mock executor](mock-smoke-executor.md) now
uses it; the default API/worker remain unchanged. The AMD draft remains
prepared-only and its live executor gate remains open.

## Ledger lifecycle

Explicit `RenderBudget.create(...)` creates a new SQLite file with mode 0600.
It refuses every existing path, requires an existing trusted private parent
directory, and leaves an unsuccessful initialization for inspection. There is
no implicit migration, reset, refund or deletion method. Normal construction
opens an existing ledger only; a missing file is an error, never a fresh budget.
Symlinks, hard links and group/world-accessible database files are rejected.

Each ledger binds the exact allocation ID and reviewed plan SHA-256 to campaign
`amd-api-smoke-v1` and a fixed limit of two. Reopening with changed identity fails.
Other campaigns, including the consumed `amd-comparison-v1`, are rejected.
This binding is a consistency check, not proof of allocation ownership, plan
validity, approved dollars or execution authority. The future executor must
establish those independently before creating any live ledger.

The schema stores only bounded non-secret call IDs, request fingerprints and
states, plus a consumed counter. Do not put prompts, credentials or exception
messages in IDs. A logical call ID must remain stable across reconnect/restart;
use a distinct ID for the second intended image, even when its prompt/seed match.
The request fingerprint should bind the exact prompt, seed and model identity.

## Invocation contract

`budget.run(call_id, request_sha256, render_callable)` performs:

1. Under `BEGIN IMMEDIATE`, validate identity, schema and accounting; reject an
   already-consumed ID, unresolved/failed predecessor or exhausted limit.
2. Increment consumption and insert `reserved` atomically. Commit with SQLite
   `synchronous=FULL` before entering the callback. No reusable permit is returned.
3. Invoke the callable once. It must contain exactly one physical render with no
   internal retry or other path around this ledger.
4. Record `succeeded` durably before returning its result. A thrown exception or
   interruption records `failed` when possible and is re-raised. No exception
   message is persisted. The executor must sanitize its own logs.

Both `reserved` and `failed` block *all* further calls, including a fresh ID while
capacity remains. There is no expiry or automatic recovery of a reservation.
A crash before callback entry still consumes the call. A crash during rendering
leaves `reserved`; reopening cannot replay it. A commit acknowledgement lost
after reservation also leaves consumption in place without invoking the callback.
If result-state recording fails, no result is returned and the reserved entry
continues to block. Storage failure while recording an exception likewise never
refunds the call. An executor encountering ambiguity must abort to cleanup.

`snapshot()` reports consumption, unused capacity, call states and whether further
calls are blocked. Unused capacity is not permission to continue a stopped run.
`succeeded` means the callable returned, not that image quality, publication or
private export succeeded. If a validation failure must halt this ledger, put that
validation in the callback after its one render. Publishing results remains the
executor's separate responsibility.

## Limits and integration requirements

SQLite serializes competing processes on one reliable local filesystem. The
object also detects file replacement during its lifetime. It does not protect
against an operator rewriting both policy and accounting, deleting/recreating or
rolling back the ledger, losing the disk, using another database, or bypassing
the wrapper. Never initialize a new ledger to resume an existing allocation.
The future controller must enforce one ledger per allocation and fail closed
when that ledger is lost. This is not a distributed accounting service or an
exactly-once physical execution claim.

The guard cannot kill a hung renderer, enforce allocation lifetime, stop billing,
validate ROCm, reserve dollars or delete a GPU. Independent provider expiry and
verified cleanup remain mandatory. A failed first render ends this smoke rather
than spending the remaining call on a replacement. No queue lease may reclaim a
render reservation, and no API idempotency replay may bypass consumption.

The dedicated executor must verify runtime/plan/serving locks, ownership,
authorization, deadline and private export destination, then wrap every physical
render with the single ledger. Its code and this guard must enter an explicitly
reviewed source lock before live use. The expanded 23-file AMD draft now locks
this guard and the mock executor. `reports/render-budget-preparation.json` is the
historical standalone component receipt; `reports/mock-smoke-executor.json`
records the new integration. Mock integration does not clear the live executor gate.

## Validation

Tests use disposable databases, fake callbacks and child processes, never GPUs.
They exercise concurrent/duplicate submissions, strict commit-before-call order,
restart and exhausted limits, abrupt process death, failed/interrupted callbacks,
rollback, ambiguous commit acknowledgement, result-recording failures, identity
changes, missing/corrupt schemas, ledger loss/replacement and file permissions.

```sh
PYTHONPATH=src python3 -m pytest -q tests/test_render_budget.py
```

No live ledger, provider request, GPU allocation, default API change or new
spending authority is created by this implementation.
