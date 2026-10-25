# Smoke expiry and cleanup contract — offline prototype

`src/emoji_studio/smoke_cleanup.py` implements a durable, independently callable
reconciliation step for **amd-api-smoke-v1**. It has no network adapter, scheduler,
provisioning command, credentials or deployment entry point. Tests use synthetic
resource IDs and mocked responses. This completes the offline contract component;
it does **not** close the independent cloud reaper gate in the active smoke plan.
The completed comparison and its existing workflows are untouched.

## Identity and deadlines

One immutable binding records provider, account, a fresh 32-hex allocation nonce,
exact numeric resource ID, plan SHA-256 and provider creation time in integer UTC
seconds. Campaign must equal the new smoke ID. The expected name contains the
campaign and nonce; required tags contain campaign, nonce and plan fingerprint.
The normalized exact lookup must match ID, name, creation time and all required
tags before DELETE. An account/provider mismatch prevents all requests.

Creation time fixes both deadlines; callers cannot extend them: cleanup starts at
minute 25, leaving five minutes inside the proposed 30-minute lifetime. A trusted
independent clock drives `reconcile(now=...)`. Terminal work can trigger earlier
cleanup with `work_complete` or `work_failed`; export success is not required.
The stored clock watermark never decreases. Once cleanup starts, a later clock
rollback cannot return the allocation to the watching state.

The binding is cleanup scope, not spending authorization or a financial reserve.
Its account identifier and provider response must come from a trusted future
adapter. No function accepts a list of resources or deletes by name/tag alone.

## Durable state and provider evidence

`CleanupLedger.create(path, binding)` explicitly creates a private SQLite ledger
and a separate private `.lock` file in an existing trusted directory. Reopening
requires both files and the identical binding. Creation refuses an existing file;
there is no reset, rebind, replacement allocation or implicit repair. Inode checks,
private modes, and symlink/hardlink rejection detect common accidental replacement.
POSIX locking serializes reconciliation; overlapping calls fail without waiting.
The separate lock avoids interactions with SQLite's own locks on macOS.

Each tick uses at most two exact lookups and one DELETE, with no sleep/retry loop:

1. Commit `pending_cleanup` and a sanitized start receipt before contacting the
   provider. Failures to persist prevent further calls.
2. Look up the exact bound ID. A verified absence completes cleanup immediately.
   An error, malformed response or identity mismatch leaves cleanup pending.
3. For a matching resource, commit delete intent, request deletion, and record
   only a generic acknowledgment/error classification.
4. Independently look up the exact ID again, even after a timeout or failed DELETE.
   Only that lookup's authenticated, authoritative 404 can produce `complete`.
   A successful DELETE response is never enough.

Interrupted calls remain pending. A later tick repeats the ownership check before
any further DELETE; it never blindly replays the previous request. Once complete,
later ticks make no provider calls. At/past the hard deadline, unverified cleanup
remains `pending_cleanup` with `deadline_exceeded: true`; it must be escalated,
not marked complete or used to release a budget reservation. `complete` here
means **resource absence**, not successful exports or overall smoke acceptance.

The `Provider` protocol uses internal `Lookup(status, resource)` values, not raw
AMD response JSON. Its future adapter must authenticate the expected account,
disable redirects and automatic write retries, apply finite request timeouts,
normalize timestamps exactly, and return 404 only from the exact-resource GET.
Authorization errors, list misses, transport failures and DELETE 404s cannot be
normalized to absence. No raw error bodies, headers or credentials enter receipts.
Receipt epochs are reconciliation clock samples, not provider billing timestamps.

## Before live use

The ledger is a local trusted-disk prototype, not a distributed cloud controller.
It does not protect against disk rollback, malicious state edits, ID reuse by a
provider, or a failed host/disk. Tests cover process death, not power-loss recovery.
A provider must guarantee immutable resource IDs across the lookup/delete window;
otherwise an atomic conditional-delete mechanism is required.

Before any separately authorized allocation, implement and verify:

- A bounded allocation reservation with a nonce persisted before POST; ambiguous
  allocation results require reconciliation without a replacement POST. This
  module starts after an exact resource has been bound and does not solve that gap.
- Durable external registration and scheduling independent of the GPU, Mac and
  Codex. A copied SQLite file on competing hosts is insufficient. The service must
  survive controller loss, share authoritative state, and retain pending cleanup
  until verified absence. The comparison's hourly watchdog cannot establish this
  smoke's five-minute cleanup window.
- Adapter contract tests against current provider documentation, scoped deletion
  authority, bounded network timeouts, scheduler latency/failure alerts and a
  tested expiry trigger. Rendering must remain disabled until registration is
  acknowledged; the live worker must enforce its work deadline separately.
- Private durable receipts and verified exports, explicit integration with the
  reservation/controller, and a reviewed expansion of the source lock. This new
  prototype is deliberately outside the active 23-file execution lock for now.

No hard wall-clock deletion guarantee follows from a scheduler or HTTP timeout.
Outages must surface as unresolved cleanup; no additional GPU may replace it.

## Verification

`tests/test_smoke_cleanup.py` exercises expiry boundaries, early terminal cleanup,
scope/identity mismatches, malformed responses, delete acknowledgments/timeouts,
post-delete verification failures, deadline escalation, clock rollback, overlapping
calls, storage failures, process death during DELETE, reopen/recovery, missing files,
links and immutable bindings. Run with the project's test environment:

```sh
PYTHONPATH=.venv/lib/python3.12/site-packages:src python3 -m pytest -q tests/test_smoke_cleanup.py
```

Retained historical cleanup evidence remains in `reports/amd-comparison-v1.md`:
four old allocations deleted, 144 images verified. That evidence does not authorize
a new allocation or establish that this new contract has been deployed.
