# Current state — 2026-10-31

## Waiting for usage headroom — no active GPU

Run41203305217/source82b486c9ba73ee47332f4f8f0e1f14b6de9ed6a6 failed
before the training worker started. Provider langchain-core0.3.83 requires
packaging>=23.2,<26; overlay installed26.3. Post-install pip check correctly stopped.
No training steps, checkpoints or generated images. Controller and independent
watchdog confirmed GPU614520349 deleted. Estimated cost$0.1382, not an invoice.
Private releaseamd-coverage-20261031a; gate closed as failed-41203305217.
Evidence: `reports/amd-coverage-first-attempt.json`; private downloaded logs and
receipts under `var/amd-training-live/evidence-41203305217/` and `latest/`.
The usage guard finished normally. Never reset this allocation claim.

Fresh usage check: primary91%, secondary77%, above85% cutoff. Queue waiting_usage,
not-before epoch1793468612. No GPU may launch or idle through quota reset. Supervisor
must recheck headroom after reset; local Mac/app-server must be awake to resume.

## Corrective candidate prepared, not dispatched

`configs/amd-training-overlay-linux-py312-v2.txt` changes only packaging26.3→25.0;
other73 pins unchanged. Local package check, full trainer import and65 focused
tests pass. `ops/amd_training_preflight.py` checks retained provider requirements
before installation; post-install pip check remains mandatory. This has not yet
been tested on the actual provider image/GPU. Receipt:
`reports/amd-training-corrective-preparation.json`.

New campaignamd-coverage-20261031b uses `ops/amd-training-corrective-plan.json`.
Controller requires prior controller/watchdog receipts and a fresh exact404, and
accounts for prior elapsed cost against the SAME$2.25 total reserve. At current
$1.99/hour ceiling, first cost+maximum new hour≈$2.1282. One new allocation,
55-minute work cutoff/56-minute expiry, independent watchdog and85% usage guard.
User's existing AMD-credit/continuation delegation covers this reviewed correction;
no automatic POST retry or reset of the old claim. No corrective GPU allocated.

Inputs: `var/amd-training-live/corrective/inputs.tar.gz`,3181 files,270449248bytes,
SHA2563936fdac5a815eeeb2dd21332fe4387fc887d7e8efd0f945d3bebe23e1820089.
Prepared private checkout `/tmp/emoji-api-smoke-ops-20261029` mirrors controller,
preflight, corrective plan and workflow. After reset: refresh plan expiry, verify
inputs/source, finish private publication/upload, arm exact source and dispatch
once only after a fresh usage check. Source gate is currently closed.

## Unchanged experiment and prior completed work

Two-step/eight-image finite-loss/reload smoke gates624-step Fluent coverage run.
Same pinned base/data/captions/split; keep checkpoint500 and final624. At most49
renders including smoke. All2493 training assets covered in2496 draws; CPU sampler
verified. `docs/coverage-training-v1.md`. Serving pilotstep25 remains unchanged.
Quality and gesture accuracy are not established; AI review must be labeled AI.

Completed API milestone: two images, run41173826485, allfour GPUs deleted,
$0.7751 estimated aggregate within separate$2 reserve. `reports/amd-api-live-result.json`.
Completed comparison:144 images, allfour GPUs deleted, ~$0.99 within separate$3;
run38352558272, `reports/amd-comparison-v1.md`. Neither may be repeated/reset.
Noto PNG licensing/font-route investigation, cutouts, durable-worker recovery and
hosting budget remain separate. GHCR deferred/gate closed. No persistent hosting.
Keep memory short and stage only intentional files; preserve unrelated recovery work.
