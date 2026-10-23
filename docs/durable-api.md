# Opt-in durable API — October 23, 2026

Local integration is implemented in `emoji_studio.durable_api.create_app` and
`emoji_studio.durable_worker.DurableWorker`. The default `emoji_studio.api`
factory/entry point is unchanged. No service was published, GPU allocated or
existing job database migrated. Validation used temporary databases and mock
rendering through FastAPI's test client and a real loopback HTTP server, not a
live AMD worker.

## Explicit opt-in

The new factory requires a database path and an explicitly selected renderer:

```python
import os
from emoji_studio.durable_api import create_app
from emoji_studio.service import MockRenderer

app = create_app(
    "var/durable-alpha/jobs.sqlite3",  # new database, not the old jobs directory
    renderer=MockRenderer(),          # deterministic local test images only
    api_key=os.environ["EMOJI_STUDIO_API_KEY"],
    trial_image_cap=100,
)
```

If running a local HTTP server, bind it to `127.0.0.1`, not a public interface.
For isolated alpha users, pass `AccessPolicy.from_file(...)` as `access_policy`
instead of sharing the single admin key. Do not put real tokens in source files.
The factory does not provision or select GPU infrastructure. Passing a real
renderer is not a substitute for a bounded, separately authorized GPU smoke.

`worker_enabled=False` admits and persists queued jobs without processing them.
Restarting with a worker enabled recovers the backlog. Existing live leases are
respected; expired attempts can be reclaimed without charging image usage again.

## API compatibility covered locally

- Existing generation/feedback request models, request IDs and bearer auth.
- Submission, owner-isolated history/status, PNG/WebP downloads and admin metrics.
- Single, variation and pack requests with deterministic seeds.
- Atomic per-user daily and global trial quotas, including concurrent requests.
- Persistent result metadata and timestamps, feedback and terminal deletion.
- Seven-day configurable terminal-content retention without deleting active work
  or refunding retained usage. Feedback is deleted with its job.
- Background lease renewal during rendering, idle model unload and graceful
  worker shutdown. Graceful shutdown waits for an in-flight render; it does not
  forcibly cancel a hung renderer. A hard process crash relies on lease expiry.

The local renderer adapter validates input image dimensions and basic metrics,
postprocesses a 512px RGBA sticker, encodes PNG/WebP, and decodes the exports to
check format, dimensions and transparency before committing the complete pack.
Result metadata and bytes commit atomically. A failed second render does not
publish the first image. Core queue hash checks remain independent of these
adapter-level image checks; they do not judge visual quality.

Renderer exception messages are not exposed to users; only a bounded exception
type and generic failure message are saved. Storage failures return a generic
503 response. Retention failures are retried on the next configured interval;
health reports degraded while the worker/retention adapter records an error.

## Persistence and intentional limits

This integration uses queue schema **4**, adding an owner-scoped idempotency
mapping to request/result metadata, timestamps and feedback. Opening a schema-3 or older database fails rather than silently
migrating it. Retain any old database and plan an explicit migration; all tests
here created disposable databases, so no existing user data was converted.

The API uses the queue's atomic admission method directly. Per-user limits come
from the authenticated user's policy, never the request body. The trial cap is
persisted; changing it in a new process does not reset it. Retried worker attempts
do not consume another reservation. HTTP retries can now use the optional
`Idempotency-Key` contract below. Without a key, each POST creates another job;
`X-Request-ID` remains correlation only.

## Optional HTTP idempotency

Send exactly one `Idempotency-Key` header with 1–128 ASCII letters, digits or
`. _ : -` (no spaces). Invalid/duplicate headers return 422 without admission.
Use a fresh, opaque random key per intended logical job; persist it before the
first POST and reuse it with the same request after a lost response. A key is
not a credential: every retry still requires current bearer authorization.

Keys are scoped to the authenticated user ID, independent of token rotation.
The same user/key and normalized request returns 202 with the **current original
job**, including its first seeds and body `request_id`, even when running,
completed, failed, or image quotas are exhausted. The response `X-Request-ID`
describes this HTTP attempt. This is not a cached byte-for-byte response.
Concurrent requests and restarts share one SQLite admission/usage transaction.
Admission deduplication is not exactly-once physical rendering after a worker crash.

Request identity is the ordered expanded, trimmed prompt list and requested
base seed (integer or null), under fingerprint version 1. Equivalent single/pack
forms and omitted/explicit defaults match; ignored extra request fields do not
change identity. Omitted/null seeds reuse the first admitted random seed pack.
Changing to an explicit seed conflicts, even if it happens to equal that pack's
first seed. Changing prompt order, content, count or seed under a used key returns
409. Use a new key to intentionally create another job, including after a failure.

Job deletion/retention preserves a minimal key/request SHA-256 mapping with the
usage tombstone. Reusing that key returns 409 and never recreates deleted content.
Keys have no automatic expiry within this database. Raw keys are not persisted
or included in public job responses; hashes are not encryption or a place for
secrets. Durable state loss still needs backups.

Request rate limits apply to replays and conflicts; 429 with `Retry-After` can
delay a retry, without creating work. Validation/auth/rate/quota rejection and
rolled-back admissions do not reserve a key. After ambiguous 503/disconnection,
retry the same key/body; never switch keys to bypass uncertainty. The Studio UI
and default API are unchanged and do not automatically opt into this contract.

Usage and results survive process restart, not disk loss. Metrics and request-rate
windows remain process-local and reset on restart. Multi-process admission races
are tested at the database level, but this is not authorization to run a GPU fleet
or a horizontally scaled API. Use one API/local-worker process for the next smoke.

Not yet provided: monetary reservations, a provider dispatcher, remote worker
authentication/transport, enforced GPU deletion from this API, HTTPS/public
hosting, backup/restore operations, durable rate limiting, or a live AMD API smoke.
One valid lease does not guarantee one physical GPU after a worker loses contact.
Keep the existing reviewed serving adapter and cloud spending gates unchanged.

## Validation

`tests/test_durable_api.py` covers the local HTTP contract, competing requests,
queued/crashed-worker recovery, heartbeat renewal, stale-worker fencing, quota
persistence, feedback/deletion/retention, deterministic exports, partial-pack
failure, corruption rejection and degraded health. Core tests additionally cover
independent-process claims/admissions and transaction rollback.

```sh
PYTHONPATH=src python -m pytest -q tests/test_durable_api.py \
  tests/test_worker_queue.py tests/test_worker_admission.py
```

Use the project's installed test dependencies. The real-socket smoke is now:

```sh
PYTHONPATH=src python -m emoji_studio.smoke_http
```

This POSIX-only runner binds an inherited socket exclusively to `127.0.0.1` on an
ephemeral port; it accepts no external endpoint or production database option.
It starts three separate API processes against one temporary database, admitting
two deterministic mock images. It checks auth/admin and owner isolation, queued
recovery, completed metadata/history/export persistence, PNG/WebP transparency,
feedback, daily/trial quotas, keyed replay across restart/full quotas, key
conflicts and deletion without refunding usage or reusing a key. It prints a
sanitized JSON receipt including source hashes, and removes the temporary data.
Ephemeral tokens remain in parent memory; only hashes travel through child stdin.
HTTP requests use neither proxies nor redirects and reject non-local paths.

The runner has a 45-second operation deadline, 2-second maximum request timeout
and bounded terminate/kill cleanup (up to six additional seconds per child).
Each child has an independent 60-second process-exit watchdog, including if its
parent is interrupted. This is a local mock safeguard, not provider/GPU cost
enforcement. No GPU libraries or real renderers are selected by this runner.
Failure logs contain only the exception type; tests check startup/check failure
cleanup, path safety, redirect rejection and deadline handling.

October 23 refreshed evidence: `reports/local-http-smoke.json`; 118 focused tests passed,
with two existing test-client deprecation warnings. The checksum-locked draft AMD
plan is now prepared: `docs/amd-api-smoke-plan.md`. Its checker verifies source
integrity only; it cannot authorize execution. AMD runtime, dedicated executor,
independent cleanup and a new bounded allowance remain prerequisites. Do not reuse
the completed comparison allocation or the NVIDIA/Vast-specific service test unchanged.
