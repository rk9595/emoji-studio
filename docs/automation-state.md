# Current state — 2026-10-31

## Active bounded AMD training — waiting on cloud

Private run41203305217 is in progress; GPU614520349 was last observed booting.
https://github.com/rk9595/emoji-studio-ops/actions/runs/41203305217
Source82b486c9ba73ee47332f4f8f0e1f14b6de9ed6a6,
releaseamd-coverage-20261031a. Queue `waiting_cloud`; do not poll with model turns.
Local usage guard PID70531 is watching; independent cloud watchdog registered.
Source gate closed as `running-41203305217`; no second dispatch/replacement.

Started12:56:40UTC (18:26:40IST), October31. Work cutoff13:51:40UTC,
self-expiry13:52:40UTC, maximum lifetime13:56:40UTC. Rate$1.99/hour,
new reserve$2.25, one allocation. Two-step finite-loss/checkpoint-reload smoke
must pass before624-step training; one smoke image+48 development images maximum.
No success or deletion has yet been established. `reports/amd-coverage-dispatch.json`.

When the exact cloud run finishes, download private training-state.json,
watchdog-result.json and training-results.tar.gz, verify hashes and independent
GPU deletion, then record the result and review image quality. On failure retain
phase logs/partial checkpoints and diagnose; never reset this consumed claim.

Read `docs/coverage-training-v1.md` and `configs/lora-coverage-v1.json`.
The old500-step run saw954/2493 images. New deterministic schedule covers all2493
in2496 draws/624 steps; step500 sees2000 distinct images. Keep checkpoint500 and
final624 for comparison. Same pinned base, Fluent v2 data, provisional captions,
split and basic hyperparameters. Historical trainers/adapters/exports unchanged.
This does not teach missing high-five/pinky-promise examples or guarantee quality.

Receipts: `reports/coverage-training-preparation.json` and
`reports/coverage-training-cpu-check.json`. All3148 export files hash-verified;
2493 decoded image/ID/caption associations checked. Real Torch2.10/Datasets5.0.1/
Accelerate1.15 CPU path preserved2496 draws and624 accumulation boundaries.
25 tests passed. Immutable bundle recreated identically. No AMD backward pass yet.
Local bundle `artifacts/trainers/coverage-v1/`, CPU env `var/coverage-validation/`.

Training overlay now pins74 packages, preserving inference versions except
fsspec2026.6.0 for Datasets compatibility. Full trainer imports and dependency
checks pass locally (Mac CPU, not Linux GPU). Eight-image/two-step smoke package
is frozen. New controller/worker implement private incremental checkpoint backups,
independent watchdog,55-minute work cutoff and56-minute instance expiry.
58 focused tests pass. Live plan: `ops/amd-training-live-plan.json`. Evaluate at most48 new images (12 development prompts ×2
seeds ×2 checkpoints); reuse verified historical baselines. This is development
comparison, not a sealed test. Preserve serving pilotstep25 until documented
quality review. Label AI review as AI; no human review has been claimed.

## Previously completed milestones and spending

Two real512px PNG/WebP emojis through authenticated API on one MI300X:
private run41173826485, sourcecbce1857e1b23f19fa9ee977f14d11cf2fc02b47,
releaseamd-api-smoke-20261030d. GPU614450630 independently deleted.
`reports/amd-api-live-result.json`, `reports/amd-api-gpu-output-receipt.json`.
Outputs: `artifacts/amd-api-milestone-20261031/api-results/`.
Successful cost estimate$0.166; allfour API attempts$0.7751 within$2reserve, all
deleted. API source gate closed as `completed-41173826485`; no allocation remains.
Original apple/smile retained. AI review: recognizable, smile has gray shadow patch.
No public endpoint or persistent hosting. Keep original outputs for matting work.

Consumed comparison:144 images, allfour GPUs deleted, ~$0.99 against separate$3
reserve; run38352558272/releaseamd-comparison-v1. Never repeat/reset claims.
AI review found all84 gesture outputs failed. `reports/amd-comparison-v1.md`.

## Automation and remaining production work

User requires GPU destruction before Codex usage limits. Keep detached local
85% usage stop (or two unavailable signals), independent cloud watchdog and
instance expiry for every future run. No GPU may idle through quota reset.
`docs/amd-usage-cleanup.md`. Local supervisor requires an awake Mac/app-server;
waiting_cloud resumes only when the exact cloud receipt finishes. Cleanup does
not depend on further model turns; usage guard requests deletion at85%.

Noto PNG license scope remains unresolved. New evidence: explicit OFL3D font
license plus OFL FAQ1.26 permits AI design tools producing non-font graphics.
Font-rendered data is a separate candidate route; no import/weight-license claim.
`reports/noto-3d-candidate-audit.json`. Keep Noto out of the coverage experiment.
Robust cutouts, real durable-worker recovery, capacity and recurring hosting budget
remain. `docs/production-next.md`. GHCR publication stays deferred/gate closed;
direct provider image already worked. Stage only intentional files; preserve
unrelated recovered worktree changes and the USB original.
