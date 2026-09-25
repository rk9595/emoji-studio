# Emoji Studio continuation handoff

Updated 2026-09-25.

## Latest continuation

Additional preparation, September 25:

- Implemented the four-image Qwen candidate trial in
  `configs/high-five-teacher-pilot.json`, `scripts/sample_interaction_teacher.py`,
  `scripts/remote_teacher_pilot.py` and `scripts/vast_teacher_pilot.py`.
- Fixed a real shared-watchdog defect: expired deadlines previously still depended
  on a successful billing lookup. Added deadline-first cleanup, stale-credit
  handling, heartbeat evidence and regression tests. This does not establish the
  entire cause of the old late cleanup or guarantee billing caps during outages.
- Trial launcher checks guard liveness, reserves three minutes and $0.15 for cleanup,
  snapshots only committed images, and verifies checksums/dimensions before import.
- All 102 tests and Ruff pass; the actual minimal upload archive was inspected.
- No Qwen weights downloaded, no candidates sampled, no training, no GPU allocation.
  A fresh API check showed zero instances and unchanged $6.1884668369 credit.
- User approved $1.50 total, <=$0.70/hour, one GPU, 60 minutes (“yes continue”).
  The hash-bound authorization is saved locally under `artifacts/vast-teacher-pilot/`.
  The launcher was invoked and stopped before allocation: no matching offer.
  Authorization is unconsumed, subject to its local expiry; the old alpha budget
  remains closed. No GPU rental, Qwen output, or training occurred.
- A broader read-only search found otherwise qualifying advertised offers around
  $0.75837/hour and $0.77778/hour. No budget/filter was relaxed. Continuing requires
  availability under $0.70/hour or approval to raise only the hourly ceiling to
  $0.80 while retaining the $1.50 total / one-GPU / 60-minute limits. The launcher
  and validation tests must be updated if that revised ceiling is approved.
- Details and exact commands: `reports/high-five-teacher-preparation.md`.

- Completed 32 matched base/style high-five/control renders on the existing GPU;
  verified every downloaded PNG. No new training steps.
- Preliminary AI review found no clear high-five pass in either condition; human
  review is pending. Step-25 seed-29 raised-hand control has six digits.
- Local gallery: `runs/high-five-baseline-v1/review.html`. Public report:
  `reports/high-five-baseline.md`, with four actual generated evidence images.
- Added `scripts/evaluate_interactions.py`, `scripts/build_interaction_review.py`,
  `scripts/prepare_interactions.py` and an interaction-specific data readiness check.
- `configs/high-five-curation.json` contains four reviewed MIT controls and two
  imagegen candidates (one rejected, one pending). Zero positive high-five examples
  are accepted. Both synthetic candidates share one pose lineage. Do not train on
  them or assume their training permissions/model version are known.
- The pinned Fluent folded-hands metadata includes high-five search keywords;
  captions must describe the actual gesture instead of copying those aliases.
- All 89 local tests and Ruff passed during this continuation.
- Existing instance 52434441 was destroyed by its guard. A September 25 v1 API
  query verified zero instances. Do not reuse the stale session record or budget.
- Whole manual-session observed credit change: $3.5573242985 against the intended
  $3 cap. Guard destruction was recorded 59.50 minutes late; the cause is not fully
  established. Investigate guard reliability before another unattended rental.
- Previous manual-test `var/` was backed up privately under
  `artifacts/vast-alpha-session/emoji-alpha-ddefe55507/saved-var`; the stale current
  pointer was archived as `current.closed.json`. Do not publish private history.
- Next: obtain an approved source of positive examples; an Apache-2.0 Qwen teacher
  is a proposed candidate, not tested. Curate positives, satisfy pose-disjoint data
  checks, then prepare a separate interaction adapter and a newly bounded GPU run.

The sections below describe earlier milestones and historical session details.

## Completed

- `rk9595/emoji-studio` is public and MIT licensed: https://github.com/rk9595/emoji-studio
- MIT license commit: `f917397`.
- Deterministic dataset pipeline: 16 training images and 4 validation images, captions, provenance, checksums, and reproducible exports.
- FLUX.2 Klein 4B LoRA post-training completed for 100 steps; adapters retained at steps 25, 50, 75, and 100.
- Blind checkpoint review selected step 25 for serving.
- Single-GPU inference service implemented with authentication, quotas, deterministic seeds, queueing, polling, feedback, deletion, retention, and transparent PNG/WebP export.
- Real service load test completed: 18 jobs, 6.73 images/minute, 35.93s p95, approximately 16.98 GiB sampled peak VRAM.
- High-five benchmark and plan added in `benchmarks/high-five-v1.json` and `docs/high-five-plan.md`.
- Blog published on `rk9595/my-website` in `posts/what-a-small-image-lora-taught-us.md`, linked from the homepage. Commit: `152ae14`.
- Website production build passed. Website repository remains private.

## Current product truth

The LoRA learns cohesive emoji-like style and simple centered objects. It does not reliably add new interaction semantics. The manual prompt `hi5 emoji` produced a generic smiley, which is expected from the object-focused training data. Do not claim dependable high-five generation, editing, meme typography, or production-grade universal stickers yet.

## Current testing session

A temporary private localhost GPU session was active for manual testing. It is ordinary-instance fallback infrastructure, not a live serverless deployment. The serverless bundle was rejected because the compressed package exceeded Vast's 5 MB code-store limit, largely due to the adapter. Stop any remaining session with:

```bash
uv run python scripts/vast_alpha_session.py stop
```

Never store or repeat the alpha token in documentation.

## Next milestone

1. Let the user test simple-object prompts manually using deterministic seeds and one or more variations.
2. Review the exported human-feedback JSON and summarize usefulness by prompt/checkpoint if new data exists.
3. Curate or commission licensed high-five positives; do not relabel waving, folded hands, clapping, or handshake examples as high-five.
4. Freeze a pose/composition-disjoint high-five evaluation set and measure the base/prompt-only ceiling before another training run.
5. Compare a targeted interaction adapter against the current style adapter and an image-conditioned/control pipeline.
6. Build meme generation later with normal HTML/Canvas typography, not diffusion-rendered lettering.

## Useful files

- `reports/quality-pilot.md`
- `reports/private-alpha-readiness.md`
- `docs/blog/what-a-small-image-lora-taught-us.md`
- `docs/high-five-plan.md`
- `docs/prompt-guide.md`
- `src/emoji_studio/service.py`
- `src/emoji_studio/api.py`
- `src/emoji_studio/studio.html`

## Important cost/status note

The pre-private-alpha whole-project estimate was approximately $3.83 by observed provider-credit changes. The user later added $5 for manual testing. All cloud instances should be stopped after testing; there is no reason to start multi-GPU infrastructure before a measured single-GPU limitation.
