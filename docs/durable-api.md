# Opt-in durable API — October 16, 2026

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

This integration uses queue schema **3** for request/result metadata, timestamps
and feedback. Opening a schema-2 or older database fails rather than silently
migrating it. Retain any old database and plan an explicit migration; all tests
here created disposable databases, so no existing user data was converted.

The API uses the queue's atomic admission method directly. Per-user limits come
from the authenticated user's policy, never the request body. The trial cap is
persisted; changing it in a new process does not reset it. Retried worker attempts
do not consume another reservation. HTTP POST retries are different: there is
**no HTTP idempotency-key contract yet**; `X-Request-ID` is correlation only, so
resubmitting a POST creates another logical job and consumes usage.

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
feedback, daily/trial quotas and deletion without refunding usage. It prints a
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

October 23 evidence: `reports/local-http-smoke.json`; 104 focused tests passed,
with two existing test-client deprecation warnings. The next step is preparation
of a checksum-locked AMD plan, followed only with separate bounded authorization
by an actual AMD smoke. Do not reuse the completed comparison allocation or the
NVIDIA/Vast-specific service test unchanged.
