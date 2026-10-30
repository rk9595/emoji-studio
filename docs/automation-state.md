# Current state — 2026-10-30

Read `ops/work-queue.json`. Preserve unrelated recovery changes; stage exact task
files only. The user authorized AMD credits for two API emojis October 29 and
continued October 30 after the reviewed corrective attempt was described.

## Active: two-image API acceptance on AMD

Private Actions run **41079063954**, source
`a9fe5c46b9884c9ca5dee1b79243ac715bdb4cbe`:
https://github.com/rk9595/emoji-studio-ops/actions/runs/41079063954
Release `amd-api-smoke-20261029b`; GPU **614256807**, started epoch
1793373362.9918551. Work cutoff +1500 sec; self-expiry +1560; deletion deadline
+1800 sec. Exact source/workflow receipt monitoring is implemented and tested.

One corrective allocation; one concurrent MI300X, $1.99/hour ceiling, two physical
renders, 30-minute lifetime including cleanup. **$2 aggregate reserve** includes
the first attempt's $0.1256. No third allocation or automatic POST retry. Each
release has an immutable allocation-intent claim; never reset either claim.

The first run **40883440921** failed before generation: SSH exit255 reading the
uploaded input checksum. Both controller and independent watchdog confirmed GPU
613866182 deleted. `reports/amd-api-first-attempt-result.json`; exact root cause
unknown because first transport stderr was not retained. Correction reuses SSH
connections, allows bounded read-only reconnects, and retains private sanitized
transport diagnostics. Allocation, generation and worker launch remain non-retryable.

Direct provider image 222743415 has ROCm7.2/PyTorch2.10; hash-pinned no-deps overlay.
Custom GHCR publication is deferred. Existing model revision and pilot step25 stay
unchanged. API binds loopback only, authenticated, admission cap2 and durable
physical render cap2. Separate cloud watchdog, absolute on-instance expiry and
container-stop timer protect cleanup. Private export is downloaded/hash-verified.
See `docs/amd-api-live.md`, `ops/amd-api-live-plan.json`.

12 failure-boundary tests and 8 exact cloud-receipt tests pass. A local real-HTTP
mock passed; it is not GPU evidence. Read the terminal cloud receipt, download
real outputs, verify hashes and independent exact-resource 404 before marking
complete. No token-consuming GPU polling. If the corrective attempt fails, retain
diagnostics, ensure deletion and mark waiting_user for any additional allocation.

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
