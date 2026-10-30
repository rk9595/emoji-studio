# Current state — 2026-10-30

Read `ops/work-queue.json`. Preserve unrelated recovery changes; stage exact task
files only. The user authorized AMD credits for two API emojis October 29 and
continued October 30 after the reviewed corrective attempt was described.

## Waiting for user: third allocation proposal, no active GPU

The two-image milestone is **not complete**: both attempts stopped before
rendering. Both allocated GPUs were independently confirmed deleted. Total
estimated runtime usage **$0.3696**, against the unchanged **$2 aggregate reserve**.

Corrective run **41079063954**, source
`a9fe5c46b9884c9ca5dee1b79243ac715bdb4cbe`, finished failure:
https://github.com/rk9595/emoji-studio-ops/actions/runs/41079063954
Release `amd-api-smoke-20261029b`; GPU614256807 deleted at epoch1793373804.3265;
independent watchdog confirmed at1793373822.1779. Failure: readiness timeout.
Saved diagnostics: initial SSH connection refused, final rsync protocol mismatch.
No successful probe stdout was retained, so noisy provider shell output is a
hypothesis, not a confirmed explanation for readiness timeout.
`reports/amd-api-live-result.json` preserves evidence and hashes.

First run40883440921 / GPU613866182 failed on SSH checksum read after upload,
with no generation. Deleted and independently confirmed, ~$0.1256. See
`reports/amd-api-first-attempt-result.json`. Never reset either allocation claim.

Prepared correction frames SSH results with per-call markers, rejects missing
success frames, uses SFTP-based scp instead of rsync, and records private timeout/
framing diagnostics. 14 focused tests and 8 exact cloud-receipt tests pass. It is
not GPU-validated. `ops/amd-api-next-attempt-proposal.json` is prepared_only and
execution_authorized=false: one potential third MI300X, max30 minutes, two renders,
$1.99/hour ceiling, no automatic POST retry. Total estimated cost at maximum new
runtime would be ~$1.3646, within the same $2 reserve. It exceeds the previously
stated two-attempt plan, so wait for user continuation of this concrete proposal.
The private exact-source variable is closed: `consumed-41079063954`.

On approval, create a fresh campaign/source and preserve both old claims. Recheck
prior exact-resource absence and cumulative costs, current price/capacity; register
independent watchdog before allocation. Existing model revision/pilotstep25,
loopback authenticated API, physical render cap2 and private hash-verified export
remain. Custom GHCR publishing stays deferred. No training or persistent hosting.

## Production and data

Existing data is Microsoft Fluent 3D, not Google Noto. Noto candidate audit pins
99701e07d…: 4,007 512px PNG files / 4,006 Git blobs. README says images Apache2,
but linked root license is OFL1.1; no license in 3D/png. Resolve asset-specific
terms before commercial training. No new data import/training started.
`reports/noto-3d-candidate-audit.json`, `docs/production-next.md` record the evidence
and production milestones. Base FLUX.2 Klein4B license at pinned revision is
Apache2. Existing gesture-quality failures remain; do not promote a new adapter
without documented quality review. Persistent hosting needs recurring budget/access.

## Deferred/completed evidence

GHCR recovery40831493602 failed registry_copy (disk_capacity hint); exact storage
mechanism unknown. Reconciliation40878081034 returned package/tag404, not verified
absence. Publication gate closed; no retry. Reports preserve evidence. CPU run
40166592399 passed 103 in-image tests and dependency checks; no GPU implication.
The old prepared-only smoke plan/23-file lock remains intact; this new live route
uses a separate explicit plan. Offline lifecycle/reservation contracts remain in
`docs/smoke-lifecycle.md` and `docs/smoke-reservation.md`.

Consumed comparison: 144 images, four allocations all deleted, about $0.99 against
its separate $3 reserve. Never repeat/reset it. Private run38352558272/release
amd-comparison-v1; `reports/amd-comparison-v1.md`. AI review found all84 gesture
outputs failed; this is not human review. Serving stays pilot step25.

## Automation

LaunchAgent checks every15 minutes, respects usage resets and active turns, and
uses exact Actions receipts without model work while cloud jobs run. Mac must be
awake/app-server available for local continuation. GPU cleanup runs in the cloud
independently; do not promise uninterrupted model reasoning.
