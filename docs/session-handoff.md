# Emoji Studio continuation handoff

Updated 2026-09-24.

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
