# Current state — 2026-11-05

## Corrected saved-adapter evaluation complete — no promotion

Campaign `amd-noto-eval-20261105e`, run41998689039, private source
`f973f98918eed2f26c6567cfe38b2866a018fc96`, completed successfully. The archive
contains the unchanged step-656 adapter and exactly24 PNGs at512x512. All25
payload hashes and sizes match the completed report. Results archive sha256 is
`1a72454f8e11db3a51e069f0c1d0628e79339aad6e8ecaf4d0e4a691c75821c1`.
GPU616116808 cleanup was confirmed by the controller at epoch1793869573.6 and
independently by the watchdog at epoch1793869581.5. New estimated cost$0.2199;
aggregate$1.0613 of the$10 reserve. These are runtime estimates, not invoices.
Campaign e is consumed; never dispatch or rerun it.

This was evaluation only: the saved step-656 adapter is unchanged, training steps
were zero, and the cap was24 images. The fixed path ran retained-package preflight,
installed the hash-locked v2 overlay, ran pip check, and only then validated the
adapter. The rebuilt 26,584,677-byte input archive was downloaded back and
verified at sha256
`6465c0d20db3db5999fedc9449c9be3bd4b6d7ca07426387454a933e1bcb837a`.
No training occurred.

AI review only: faces, firefighters, backpacks and bicycles are visually coherent.
The two high-five outputs resemble prayer/pressed hands rather than two people
meeting palms. Crossed-finger outputs are inconsistent or ambiguous, often
reading as a raised index. Pinky-promise outputs are mixed. With no matched
baseline in this run, do not claim improvement. The adapter is not promoted;
serving remains reviewed pilotstep25. User judgment and a new immutable plan are
required before another training direction or any promotion.

## Closed earlier attempts

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
also independently deleted after a dependency-check failure. At that point, no
training had completed on AMD. Both immutable claims are consumed and cannot be reset.

## Usage control and completed evaluation history

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

Evaluation release amd-noto-eval-20261101d is consumed. Run 41321034924,
source `51b989c0207d7b7d430c85c71b1808043154375d`, allocated GPU 614806003 at
epoch 1793546665.6 and deleted it at 1793546900.6. The independent watchdog
confirmed droplet 614806003 at epoch 1793546909.4. No images. The worker raised
`ModuleNotFoundError: No module named 'safetensors'` because evaluate mode
skipped the hashed overlay install. Estimated cost $0.1299. Aggregate with the
three earlier attempts is $0.8414 of the $10 reserve. Receipt
`reports/amd-noto-eval-campaign.json`. Do not dispatch campaigns b, c, or d.

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
