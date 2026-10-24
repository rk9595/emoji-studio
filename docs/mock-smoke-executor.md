# Mock-only smoke executor — October 24, 2026

`emoji_studio.mock_smoke_executor.MockSmokeExecutor` connects the durable queue,
two-call `RenderBudget`, PNG/WebP validation and atomic job publication. It
constructs `MockRenderer` internally and accepts no renderer or provider factory.
The default API and `DurableWorker` are unchanged. A real AMD executor, runtime
verification, independent expiry/deletion and separately bounded allowance are
still prerequisites; this implementation cannot switch to live rendering.

## Dedicated execution path

The dedicated API must use `worker_enabled=False` and a persisted trial cap of
two. Pass its existing `app.state.store`, the same allocation's existing budget
ledger and the reviewed plan path to the executor. It checks the ledger's exact
plan hash and requires the prepared-only two-identical-apple-image proposal with
false execution authority and a null dollar allowance. A plan claiming execution
authority is rejected rather than enabling a real renderer. The complete source
inventory is checked separately by `scripts/check_amd_api_smoke_plan.py`.

`run_next()` performs one synchronous queue claim, without a polling/retry loop:

1. Check the ledger and reconcile previously consumed calls against published
   jobs. Missing/deleted/unpublished results or completed jobs without reservations
   stop new work. This reads trusted local queue metadata, not an ownerless HTTP API.
2. Claim one lease and require exactly the planned single prompt and seed. Packs
   and other requests fail before rendering. An empty queue consumes no budget.
3. Derive call ID `<durable-job-id>:0`. Lease tokens, worker IDs and attempt
   numbers are excluded, so reclaiming a lease cannot obtain a fresh call ID.
4. Fingerprint the exact prompt/seed, logical job/image position, actual mock
   implementation version, planned serving identity and complete serving-config
   checksum. Intended serving metadata is not a claim that the mock loaded it.
5. Inside `budget.run`, verify the live lease, render exactly once, validate and
   encode both exports, and atomically publish their hashes/metadata through the
   queue. Only then may the guard mark its reservation succeeded.

The publication step stays inside the reserved interval. If rendering succeeds
but job publication fails or loses its acknowledgement, the budget becomes
failed (or remains reserved after abrupt death) and blocks the remaining call.
A crash after publication but before budget completion likewise stops the smoke,
even if the completed job can be read. It does not erase valid outputs or retry.
On recoverable Python exceptions, job failure uses a generic message; exception
text is not stored. A stale lease cannot publish. An invalid request can fail its
job without reserving a render; it does not grant additional image quota.

The synchronous mock path uses a 60-second lease and checks it before rendering;
it does not renew throughout rendering. Expiry rejects publication and stops the
ledger. This is suitable for bounded disposable mock checks, not a GPU worker
that can load/render for minutes. Do not replace its internal mock constructor
with FLUX and assume the live deadline/cleanup requirements have been met.

Use one dedicated queue and ledger for an allocation. Disk rollback, replacing
either database, direct SQL edits or other workers bypassing this executor are
outside the trusted local boundary. The ledger and queue have separate commits;
the conservative response to disagreement is to stop, not to claim a distributed
transaction or exactly-once physical execution. Reconciliation verifies published
job identity/status; export content integrity remains the queue artifact check.

## Disposable verification

```sh
PYTHONPATH=src python3 -m emoji_studio.mock_smoke_executor
```

This accepts no endpoint/database/renderer options. With installed test-client
dependencies, it creates temporary queue/ledger files and ephemeral auth, admits
two separate requests through the in-process API, recreates the app/executor on
the same files, checks exports/replays/quota, and verifies a third invocation is
denied. It removes the temporary files and prints a sanitized receipt. It is
distinct from the real loopback HTTP smoke (`python -m emoji_studio.smoke_http`),
which is also refreshed as regression evidence.

Evidence: `reports/mock-smoke-executor.json` and `reports/local-http-smoke.json`.
The expanded prepared-only AMD plan now locks 23 files, including the guard,
executor, their tests and mock receipt. The checker verifies those receipt hashes
and still returns false execution authority; it never updates source hashes.
The original standalone guard receipt remains historical evidence, with its
then-current plan hash. No live ledger was migrated or recreated by this relock.

Eighteen executor tests cover API replay/reopen, stable IDs across lease reclaim,
model fingerprints, publication failures/lost acknowledgements, abrupt child
death during rendering and after publication, expired leases, missing/unguarded
publications, invalid requests and prevention of renderer injection. Together
with regressions and draft-integrity checks, 166 tests and 38 subtests passed.
No GPU, provider request or new spending was involved.
