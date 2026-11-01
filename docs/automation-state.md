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

## Usage control and current evaluation

On 2026-11-01 the user said the usage limit was Codex's and to keep building in
Cursor. The Codex supervisor stays on waiting_usage so it does not start a turn.
Do not arm the Codex usage guard. Independent watchdog and on-instance expiry
still apply.

Campaign amd-noto-fluent-20261101c is consumed. Run 41282477874 finished the
656-step train: 2,624 finite losses in 565 seconds. Adapter
step-656.safetensors, sha256
`8dc022f06b20e73a0c5cbaa935730225f54f6e191e3ef3a2a89e33d8ff0102f9`, is on release
amd-noto-fluent-20261101c. Its evaluation failed because step-500.safetensors
was not retained. GPU 614708454 cleanup confirmed by the controller and by
watchdog-result.json. Estimated cost $0.504, aggregate $0.7115 of the $10
reserve. No promotion.

The user authorized a separate evaluation of that saved adapter. Release
amd-noto-eval-20261101d, private source
`51b989c0207d7b7d430c85c71b1808043154375d`, workflow run 41321034924, both jobs
in progress. Plan `ops/amd-noto-eval-plan.json`. Input
`var/amd-training-live/eval-inputs.tar.gz`, 26493030 bytes, sha256
`cdc6039af41c4b40906e0c40082118d488ec4a6c02f8a8b8bbfa9b554e51996b`. Twelve
development prompts, two seeds, 24 images, step-656 only, no training. Lifetime
at most 2400 seconds, work cutoff 2100, self-expiry 2160, rate at most
$1.99/hour, same $10 reserve. Do not claim the 24 images or GPU deletion until
this run's receipts exist. Do not dispatch consumed campaigns b or c.

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
