# Current state — 2026-10-30

Read `ops/work-queue.json`. Preserve unrelated recovery changes; stage exact task
files only. The user authorized AMD credits for two API emojis October 29 and
continued October 30 after the reviewed corrective attempt was described.

## Active third API attempt — user approved

Private Actions **41087086776**, source32e1d704cdf60dae8300119cf3e635111ff525e8:
https://github.com/rk9595/emoji-studio-ops/actions/runs/41087086776
Release `amd-api-smoke-20261030c`; GPU614271639, started epoch1793376498.4049,
outer deletion deadline1793378298.4049. User explicitly approved the prepared third
attempt and required GPU destruction before model usage limits. One new MI300X,
max30min/$1.99hr, two renders, same $2 aggregate reserve (prior usage ~$0.3696).
No reset/repeat of older claims or comparison. No automatic allocation POST retry.

The framing/SFTP correction also starts an SSH master separately without captured
pipes, so a background master cannot keep probe pipes open. 16 focused transport/
cleanup tests, 4 usage-policy tests and 8 exact cloud-receipt tests pass. Source
archive is unchanged and hash-verified; serving remains pinned pilotstep25.

Usage guard runs locally as ordinary detached code, bound to this run/release.
Reads `account/rateLimits/read` every30sec. At85% usage (either window), or two
unavailable readings, it writes one private bound `stop-request.json`. Both cloud
controller and independent watchdog honor it. Initial usage check reported adequate headroom. Local receipt: `var/amd-api-live/usage-guard-41087086776.json`.
If the Mac/session disappears, independent cloud expiry still deletes at minute26;
worker cutoff is minute25, outer deletion deadline minute30. Do not promise perfect
prediction of usage limits or outage-free provider deletion. No GPU should be left
running merely to wait for Codex limits to reset.

Next: use exact cloud receipt; verify real API images, hashes and independent
exact-resource404 before completion. Early stop does not mean success. Never mark
complete with only mock outputs or pending cleanup. Keep memory concise.

## Earlier attempts (consumed and deleted)

Run40883440921/GPU613866182: SSH255 on checksum read after upload, no generation,
~$0.1256. `reports/amd-api-first-attempt-result.json`.
Run41079063954/GPU614256807: readiness timeout, no generation, ~$0.244; independent
cleanup confirmed. `reports/amd-api-live-result.json` currently records this older
failure. Private diagnostics had initial connection refusal and rsync protocol
mismatch; noisy shell and background pipe behavior were hypotheses, not confirmed
provider root causes. Both old exact-source gates are consumed.

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
