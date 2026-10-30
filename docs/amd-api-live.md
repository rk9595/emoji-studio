# Two real API images on one AMD GPU

The user authorized this milestone October 29 and continued October 30. The
completed corrective campaign is `amd-api-smoke-20261029b`, separate from the
consumed comparison and the first API attempt. The prior offline plan
and its 23-file lock remain unchanged; this live plan explicitly chooses the
provider's ready-made ROCm image instead of waiting for custom GHCR publication.

Private execution: https://github.com/rk9595/emoji-studio-ops/actions/runs/41079063954
Source: `a9fe5c46b9884c9ca5dee1b79243ac715bdb4cbe`.
Private release: https://github.com/rk9595/emoji-studio-ops/releases/tag/amd-api-smoke-20261029b
Plan: `ops/amd-api-live-plan.json` (SHA-256
`210fe688fde3efecba99309ded2b0adf98b0c0a31524868971b783f320a9dd47`).

## Scope and acceptance

- One MI300X, rate checked against $1.99/hour, 30-minute maximum lifetime,
  $2 aggregate reserve including the first attempt (~$0.1256); corrective
  maximum runtime usage $0.995. No third allocation.
- Ready-made image 222743415, PyTorch 2.10/ROCm 7.2. Install the existing
  hash-pinned overlay with `--no-deps`; retain ROCm torch. This is not a claim of
  an immutable custom runtime or production deployment.
- Existing pinned FLUX.2 Klein base 4B and pilot step-25 adapter. Generate an
  apple and smiling face with the normal authenticated HTTP API, seeds 7/8.
- Loopback only. No public inference endpoint. API admission cap and durable
  render ledger both limit the test to two images. No API POST retries or worker
  restarts. The new wrapper leaves existing service defaults unchanged.
- Verify 512px RGBA PNG/WebP downloads through HTTP, transparency, corresponding
  pixels, hashes, authentication rejection and third-image rejection. Verify real
  renderer identity and both successful ledger entries. Back up privately and
  re-download the private archive to verify its hash.
- Confirm exact-resource authenticated 404 after deletion. The independent cloud
  watchdog must also confirm deletion before the milestone is accepted.

## Failure containment

The release's `allocation-intent.json` is created without overwrite before the
single provider POST. A repeated dispatch or ambiguous POST cannot obtain another
allocation. The exact-source gate and first workflow-attempt gate also block
replays. This relies on trusted repository operators preserving the claim.

The controller requires a separately running cloud watchdog registration before
allocation. The instance receives an absolute self-expiry timer for minute 26.
The controller stops work at minute 25; an independent on-instance timer stops
the ROCm container then, even if a model call is hung. The controller deletes in
`finally`; the separate watchdog also deletes overdue owned resources. Ownership
uses campaign name/tag, region, size and creation window. Known exact IDs do not
depend on a successful list request for cleanup. Provider/control-plane outages
can still delay deletion; no cloud mechanism can guarantee an outage-free hard
billing cap. Unconfirmed deletion remains pending, never success.

No AMD token enters the input archive, public code or reports. The GPU's root-only
expiry credential disappears with the instance. Logs/artifacts stay private.

## Validation

Fourteen focused tests cover two-call enforcement, deadline/late-call failures,
replay refusal, ownership, authenticated deletion checks, the no-overwrite claim,
and ambiguous POST reconciliation without a second allocation. The local real
HTTP mock test passed (`reports/amd-api-live-local-test.json`); it is explicitly
not GPU evidence. Eight cloud-receipt tests verify exact run/source/workflow
matching, including this private run. The supervisor reads the Actions receipt
without invoking model turns while it is still running.

Live acceptance outcome belongs in `reports/amd-api-live-result.json` once both
images and deletion receipts have been verified.

## Reviewed correction

First run40883440921 (source d80b1daf…) uploaded the input archive, then SSH
exit255 interrupted its checksum read. No generation started. GPU613866182 was
deleted and independently confirmed absent; estimated usage $0.1256. The exact
transport cause is unknown because stderr was not retained. See
`reports/amd-api-first-attempt-result.json` and the preserved first plan.

The correction reuses an SSH control connection and allows at most three
reconnects for explicitly read-only calls. Mutating launches and API POSTs remain
single-shot. Sanitized transport diagnostics stay in private artifacts. The
corrective preflight rechecks the first exact resource is absent, verifies both
cleanup receipts and checks combined prior/maximum new runtime against the same
$2 reserve. Both claims stay consumed; there is no automated third attempt.

## October 30 outcome: milestone incomplete

Run41079063954 timed out waiting for the ROCm image / expiry timer readiness
condition. No generation occurred. GPU614256807 was deleted; the independent
watchdog confirmed exact-resource absence. Total estimated usage across both
attempts is $0.3696. `reports/amd-api-live-result.json` retains the outcome.

The private diagnostics show an initial refused SSH connection and an rsync
protocol mismatch during final collection. No successful readiness stdout was
retained, so noisy shell startup output remains a hypothesis for that timeout.
The prepared correction frames SSH stdout with unique markers and copies fixed
result filenames via SFTP-based scp. Tests execute the real wrapper locally with
a provider-like banner and reject unframed output. Timeout/framing diagnostics
are now preserved. This correction is not GPU-validated.

Both allocation claims remain consumed and the exact-source gate is closed.
`ops/amd-api-next-attempt-proposal.json` describes a potential third attempt,
within the existing $2 aggregate reserve, requiring user continuation of that
concrete proposal. The queue is waiting_user; there is no automatic third launch.
