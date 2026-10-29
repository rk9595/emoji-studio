# Offline smoke lifecycle coordination

`src/emoji_studio/smoke_lifecycle.py` connects the reservation, cleanup, render
budget, mock worker and private-export contracts. It is an offline component with
no live provider adapter, GPU renderer, scheduler or deployment command. The active
23-file smoke lock and 38-file runtime context remain unchanged. The tests use
synthetic allocations/registration services and private in-memory export storage.

## Registration and rendering

A lifecycle journal can be created only for a bound allocation with matching
cleanup and render-budget identities. It pins that binding, the whole reservation,
plan hash and serving-configuration hash. The existing prepared-only plan reader
restricts execution to the established two-image mock proposal.

Cleanup registration is a one-shot operation. Its intent is committed before the
registrar is called. An acknowledgment is insufficient: a separate lookup must
return the exact binding fingerprint, minute-25 stop time, minute-30 deadline,
active status and independent-service assertion. A lost acknowledgment or process
death consumes registration; reopening uses read-only lookup, never another
registration invocation. These normalized assertions are trusted adapter input,
not proof that a real independent scheduler exists.

`run_next` uses only the existing `MockSmokeExecutor`, which constructs MockRenderer
internally. It checks registration, the bound allocation, cleanup watching state
and the work deadline before claiming work, again inside the committed render
budget callback, and after the callback. Clock samples use a persisted watermark.
Deadline crossing, registration revocation or cleanup starting during a mock render
prevents recording that call as successfully completed and halts further work.
The render ledger still consumes the invocation; no replacement call is granted.
The underlying job may already have published bytes before the post-callback guard
fails; those bytes are not evidence of accepted lifecycle success.

Checks are not an atomic cloud fence or a hard kill mechanism: cleanup can begin
between a check and a callback, and Python cannot preempt a hung renderer/adapter.
Production needs a separately enforced worker deadline and independent expiry
service. The current coordinator cannot select a real renderer.

## Durable export and independent cleanup

After both guarded mock calls succeed, `stage_export` reads the selected surviving
publications through the existing owner-scoped queue APIs, checks stable call/request
identity and artifact hashes, and builds a sanitized bundle. It accepts both images
or one surviving original index. It cannot label arbitrary caller-provided bytes
as the worker's output. The canonical export ticket is committed before returning
the bundle. This permanently ends rendering and pins one manifest; another manifest
cannot replace it.

`upload` requires that exact saved ticket and commits upload intent before the
first storage call. At most one upload invocation is permitted per lifecycle.
Partial upload, timeout or lost acknowledgment never triggers a re-upload.
`verify_download` accepts a separate read-only interface and needs only the saved
ticket after restart. It downloads and verifies the manifest/artifacts through the
existing export verifier and saves the verification receipt. A new failed
verification clears previous success. Interface separation is not proof of remote
cache independence; that remains a requirement on a future authenticated adapter.

The lifecycle journal has its own lock. Cleanup uses its separate ledger and can
be invoked without acquiring the lifecycle lock, including while render or upload
is blocked, the controller has crashed, or export verification failed. Tests verify
cleanup progresses during a blocked upload and during a mock render. No successful
export is required before an independent caller can request cleanup. This module
does not itself schedule or guarantee that caller runs.

`offline_complete` requires two successful guarded calls, a registration receipt,
verified export and independently verified resource absence. It always leaves
`smoke_accepted` and `gpu_validated` false. A deletion acknowledgment, upload
acknowledgment or successful mock run alone cannot complete the lifecycle.

## Storage and deployment limits

Private SQLite and a separate POSIX lock file use explicit exclusive creation,
exact immutable identities and synchronous commits. Missing files, symlinks,
hardlinks, permissive modes, replacement inodes and schema mismatches fail closed.
No reset or implicit recreation exists. This is trusted local-disk persistence,
not a distributed transaction or protection against deliberate disk rollback.
Separate ledgers on one host do not establish durability outside that host/GPU.

Before live use, register the intent/nonce with an independent expiry service
before allocation, persist exact-resource registration before rendering, implement
authoritative global reservations and private external ticket/receipt storage,
enforce adapter timeouts and worker deadlines, and test controller loss end to end.
The runtime still needs verified private retention/fresh pull. Source integration
and a separately bounded GPU allowance are still required; no paid authority was
introduced by this component.

Validation: 28 lifecycle tests; combined **215 tests/252 subtests** passed, with two
existing dependency deprecation warnings. Ruff and both existing input-lock checks
passed. Coverage includes process death during registration, lost acknowledgments,
commit failures before side effects, owner isolation, corrupted artifacts, clock
rollback, deadline crossing, restart-only download verification, and independent
cleanup during blocked work. See `reports/smoke-lifecycle-preparation.json`.
