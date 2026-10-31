# Current state — 2026-10-31

Read `ops/work-queue.json`. Stage only task files; preserve unrelated recovery edits.
User delegated the two-real-emoji AMD API milestone and explicitly requested GPU
destruction before Codex limits. Broad AMD credits do not remove the concrete bounds.

## Active cloud run

Private Actions **41173826485**, source
`cbce1857e1b23f19fa9ee977f14d11cf2fc02b47`:
https://github.com/rk9595/emoji-studio-ops/actions/runs/41173826485
Release **amd-api-smoke-20261030d**. One new MI300X, max$1.99/hr,
provider startup up to15min inside25min work cutoff/30min total lifetime.
Same **$2 aggregate reserve**, including ~$0.6091 prior failed attempts.
Two physical renders, loopback authenticated API, private hash-verified export.
Serving model/revision/pilotstep25 and input archive unchanged. No POST retry.

Fresh October31 usage check was below85% after yesterday's reset wait. Local
usage guard is detached ordinary code, bound to this exact run/release; receipt:
`var/amd-api-live/usage-guard-41173826485.json`. At85% quota or two unavailable
signals it writes an immutable stop request; cloud controller/watchdog delete.
Independent minute26 self-expiry and separate cloud watchdog remain mandatory if
Mac/model disappears. No GPU may idle waiting for quota reset. See
`docs/amd-usage-cleanup.md`. Supervisor supports waiting_usage without model polling.

Next: use exact cloud receipt; validate real images, physical ledger, downloads,
and independent authenticated exact-resource404 before marking complete. No new
allocation while this run is active. The goal is not fulfilled by mock images.
17 controller tests +4 usage-policy +9 receipt/threshold +5 supervisor tests pass.

## Prior consumed API attempts — all deleted, zero images

- 40883440921 / GPU613866182: SSH255 after upload, ~$0.1256.
- 41079063954 / GPU614256807: readiness timeout, ~$0.244.
- 41087086776 / GPU614271639: provider initialization gate, ~$0.2395.
All independent cleanup receipts are retained. Third stdout explicitly said
"Please wait while we get your droplet ready"; increasing the startup allowance
is a bounded test, not a proven provider fix. Reports:
`reports/amd-api-first-attempt-result.json`, `reports/amd-api-live-result.json`
(second attempt), `reports/amd-api-third-attempt-result.json`.
Never reset these claims or the separately consumed AMD comparison.

## Production/data and deferred work

Current data is Microsoft Fluent3D. Noto candidate audit pins99701e07d… with4,007
512px PNGs/4,006 blobs; README says Apache2 but linked root license is OFL1.1.
Resolve PNG-specific terms before commercial training. No new training/import.
Base FLUX.2 Klein4B pinned revision has Apache2 license. See
`docs/production-next.md`, `reports/noto-3d-candidate-audit.json`.
Gesture-quality failures remain; adapter promotion needs documented review.
Persistent hosting needs recurring budget/access; no public endpoint yet.

Custom GHCR publication is deferred, gate closed after storage-copy failures.
CPU validation passed103 in-image tests; the old prepared-only smoke plan/23-file
lock is intact. The new direct-provider route has a separate explicit live plan.
Historical evidence is in the referenced reports; do not resume registry work now.

Consumed comparison:144 images/four allocations all deleted,~$0.99 against separate
$3 reserve. Never repeat/reset it. Private run38352558272/releaseamd-comparison-v1.
AI review found84 gesture outputs failed; do not claim human review. Pilotstep25 stays.

Local supervisor checks every15min; Mac/app-server must be awake. Cleanup runs
independently in the cloud. Do not promise uninterrupted model reasoning.
