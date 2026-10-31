# Current state — 2026-10-31

## Next milestone: bounded Fluent coverage training

User asked to continue training toward production. Queue `ready`; no GPU allocated
and no new training started. Offline preparation is complete. Next implement the
AMD training environment and private lifecycle, then a finite-loss smoke and the
frozen training recipe under one allocation/60-minute/$2.25 proposed ceiling.
Use current availability/rate/usage checks; never reuse the completed API or
comparison claims. No repeated permission request for routine implementation.

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

Next run needs a pinned training overlay (inference overlay is insufficient), a
separate explicit smoke recipe, private checkpoint backups, independent watchdog
and instance expiry. Evaluate at most48 new images (12 development prompts ×2
seeds ×2 checkpoints); reuse verified historical baselines. This is development
comparison, not a sealed test. Preserve serving pilotstep25 until documented
quality review. Label AI review as AI; no human review has been claimed.

## Completed milestones and spending — no active GPU

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
queue ready allows continuation, not allocation without completing readiness.

Noto PNG license scope remains unresolved. New evidence: explicit OFL3D font
license plus OFL FAQ1.26 permits AI design tools producing non-font graphics.
Font-rendered data is a separate candidate route; no import/weight-license claim.
`reports/noto-3d-candidate-audit.json`. Keep Noto out of the coverage experiment.
Robust cutouts, real durable-worker recovery, capacity and recurring hosting budget
remain. `docs/production-next.md`. GHCR publication stays deferred/gate closed;
direct provider image already worked. Stage only intentional files; preserve
unrelated recovered worktree changes and the USB original.
