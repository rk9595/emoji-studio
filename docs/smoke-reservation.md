# Single-allocation reservation — offline prototype

`src/emoji_studio/smoke_reservation.py` completes the local reservation component
for `amd-api-smoke-v1`. Tests use a synthetic account, approval fingerprint and
amounts; no real allowance, provider call, GPU, image publication or deployment was
created. The active smoke plan remains unauthorized. This component is outside the
active 23-file execution lock and the 38-file runtime build context.

An immutable `Reservation` pins the account, fresh allocation nonce, plan hash,
request hash, approval-evidence hash, integer USD-millionth allowance/reserve and
short validity window. Reserve must be positive and no greater than the supplied
allowance. Those inputs are trusted controller assertions, not proof of approval,
current prices or an enforced provider billing cap. The controller must validate
actual approval and pricing before ever supplying a live adapter. Synthetic test
amounts do not change the project's spending bounds.

`AllocationLedger.create` explicitly initializes a private SQLite file and separate
private lock file in an existing trusted directory. It refuses existing files.
Reopening requires the exact reservation. Missing/replaced files, links, permissive
modes and mismatched schemas fail closed. There is no reset, rebind or implicit
recreation. POSIX locking serializes calls across handles/processes without waiting.

## One create attempt, durable uncertainty

`run(provider, clock=...)` checks account/provider scope and validity, then commits
`outcome_unknown` and `create_intent_committed` **before** invoking `create` once.
A timeout, interruption, process death, malformed result or persistence failure
after the invocation cannot make the create attempt available again. Even a
successful binding or later verified deletion cannot grant a replacement attempt.
Exceptions from the adapter become fixed receipt codes rather than raw messages.

The returned candidate must match the pinned account, provider, campaign, nonce
and plan. Creation time must fall between attempt start and a fresh trusted clock
sample. The candidate is persisted before an exact-ID lookup verifies its name,
tags and creation time using the existing cleanup ownership rules. An allocation
acknowledgment alone cannot reach `bound`. Every snapshot explicitly leaves
`rendering_authorized` false.

`reconcile` performs at most one nonce discovery and one exact-resource lookup;
it cannot CREATE or DELETE. With no retained candidate, discovery must return
exactly one normalized matching binding. Empty, multiple, partial/untrusted or
failed discovery stays unresolved. A candidate already retained is pinned: recovery
looks up that exact ID rather than selecting another resource. Exact GET 404 here
also stays unresolved; it does not refund the attempt or reserve. Once bound,
subsequent reconciliation performs no provider calls.

The injected trusted UTC clock is resampled after provider operations. A persisted
watermark prevents an expired reservation from becoming usable after clock rollback.
Reconciliation remains possible after expiry so that late-discovered resources can
be passed to cleanup. The binding carries the existing 25-minute work cutoff and
30-minute cleanup deadline; discovering it late does not restart either deadline.
Adapter calls receive a ten-second timeout. A future adapter must enforce total
transport limits, authentication, complete discovery semantics, fixed-account
scope and zero write retries. This Python protocol cannot interrupt a hung adapter.

## Integration limits

This is a trusted local-disk prototype, not a deployed distributed controller or
financial accounting system. The guarantee is one create invocation **per ledger**;
creating another ledger or rolling back/copying the disk can bypass it. A future
single authoritative store must enforce campaign/approval/nonce uniqueness and
atomic budget reservation across all controllers. No money is actually held by
this module. `reserve_held_microusd` is conservative bookkeeping and never released
here; billing settlement and release require separate authoritative evidence.

Before live use, independently register the intent/nonce and expiry policy outside
the GPU, Mac and controller before CREATE. The external service must discover and
clean up ambiguous allocations after controller loss. Persist exact bindings and
acknowledged cleanup registration before rendering. A local `bound` state does not
prove that registration exists. Export tickets and verification receipts also need
durable storage outside the GPU, while cleanup runs independently of export success.
None of those live adapters/services are supplied by this module.

## Verification

27 new tests cover committed intent before invocation, overlapping handles, process
death during create, interruptions, persistence failures before/after create,
reopen/recovery, stale clocks, expired reconciliation, missing/multiple discovery
results, ownership mismatches, candidate pinning, invalid amounts, file loss/links,
and absence of retry after cleanup. A combined suite passed **187 tests and 245
subtests**, including cleanup/export/render guards, runtime checks and receipt
monitoring. Ruff and both existing input-lock checkers passed. Two existing
Starlette/httpx/anyio deprecation warnings remain; no dependency update was made.
See `reports/smoke-reservation-preparation.json` for source fingerprints and command.
