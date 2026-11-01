# Current state — 2026-11-01

## Waiting for quota reset — both training GPUs deleted

Corrective run41273277371 stopped during boot at the85% usage cutoff. No worker,
training steps, adapters or images. GPU614682073 controller deletion confirmed;
independent read-only run41274185805 authenticated exact GET404 at epoch1793508215.
`reports/amd-coverage-second-attempt.json`. Private releaseamd-coverage-20261031b,
source0a960b92de7457a231ed348153b13b898d114db4. Claim consumed, gate failed-41273277371.
The local guard finished normally after requesting cleanup. No active task GPU.

Original watchdog failed with Exact resource ownership mismatch. Cause is not
established; do not claim a confirmed race or successful original watchdog. A
separate cloud reconciliation succeeded, sourcee3179cab15a132cb6e314cccbd1a7965bac769d9.
The watchdog now preserves strict ownership checks and keeps checking until its
bounded deadline after a refusal/error; a later exact404 can confirm deletion.
26 focused tests pass, including failure-to-retry and failure-receipt handling.

Second cost estimate$0.0693; first$0.1382; aggregate$0.2075 against SAME$2.25 reserve.
These are runtime estimates, not invoices. First run41203305217/GPU614520349 was
also independently deleted after a dependency-check failure. No training has yet
completed on AMD. Both immutable claims are consumed and cannot be reset.

## Usage control and next ready work

Queue waiting_usage. Latest primary61%, weekly88%; next-reset/not-before
1793857555. Future GPU allocation requires ALL windows below75%, reserving headroom
for handoff; the active-job stop remains85% or two missing signals. Supervisor
supports usage_start_threshold_percent75. It requires an awake Mac/app-server;
cloud cleanup is independent. No GPU may idle through reset.

After reset, check fresh quota. Before any further reviewed allocation, create a
new campaign/plan rather than reuse campaignb. Extend cumulative-cost verification
to both consumed attempts; campaignb uses its independent reconciliation receipt
because its original watchdog failed. Fresh exact404 checks and aggregate$2.25
ceiling remain required. Existing controller still names consumedb; do not dispatch.

The dependency correction remains prepared: v2 overlay changes packaging26.3→25.0
for provider langchain-core compatibility, preserving73 other pins. New pre-install
retained-package audit plus post-install pip check. Local trainer import/dependencies
passed; actual corrected provider install/GPU backward pass was not reached.
`reports/amd-training-corrective-preparation.json`, `docs/coverage-training-v1.md`.
Inputs under var/amd-training-live/corrective/ are retained, not a new authorization.
Public/private fixes are versioned; preserve old plans, receipts and input archives.

## Experiment and previously completed milestones

Two-step/eight-image finite-loss/reload smoke gates624-step Fluent coverage run.
Same base/data/captions/split; retain checkpoint500 and final624; at most49renders
including smoke. CPU coverage verification passed. Serving pilotstep25 unchanged.
Quality and gesture accuracy are not established; label AI review as AI.

Completed API: run41173826485, two images, allfour GPUs deleted, ~$0.7751 within its
separate$2 reserve. Completed comparison: run38352558272,144 images, allfour GPUs
deleted, ~$0.99 within separate$3. Never repeat/reset these consumed allocations.
Noto licensing, cutouts, durable-worker recovery and production budget remain
separate. GHCR remains deferred; no persistent hosting. Stage only intentional
files and preserve unrelated recovery changes.
