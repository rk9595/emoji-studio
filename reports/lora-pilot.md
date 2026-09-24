# First LoRA pilot: 100-step quality pilot complete

## Objective

Learn the complete adapter-training workflow on one GPU: data loading, flow-matching loss, gradient accumulation, checkpoints, resume, and before/after inference. The first pilot tests style adaptation on objects. It does not claim to teach novel two-hand anatomy or produce a production-ready model.

Klein base 4B is the provisional candidate based on this project's object controls and style response. The small benchmark does not establish broad superiority. [BFL identifies the undistilled base variant as a fine-tuning starting point](https://docs.bfl.ai/flux_2/flux2_klein_training).

## Prepared data

- 20 Microsoft Fluent 3D object concepts, pinned to the existing MIT source revision; the upstream license notice is retained.
- 16 training concepts and four validation concepts: Backpack, Books, Alarm clock and Umbrella. Battery and Low battery stay together in training.
- Captions were written after AI visual inspection of all 20 actual PNGs. This is explicitly not independent human review.
- Remaining 43 imported references are excluded from this object-only pilot, not rejected for poor artwork quality.
- Native size is only 256 x 256. Low-resolution use is explicitly accepted for this learning experiment. Resizing to 512 does not recover missing detail.
- Source transparency is untouched. The implemented export composites RGBA onto white before Lanczos resizing, preserving aspect ratio with centered padding and no augmentation. The 512-pixel RGB copies are in `data/training/pilot-v1`; originals remain unchanged.
- Four validation images are not enough for a reliable final evaluation. These are development splits; no sealed final test set is created here. Existing 40 development prompts also contain source concepts and must not be called unseen training evaluation.

The curation manifest is `data/curation.json`. `emoji-studio training-preflight` checks manifest freshness, checksums, review/caption fields, licenses, explicit resolution acceptance, concept-family and identical-image leakage, split counts and the source license notice. It passes for this curation while always reporting `training_authorized: false`. Browser-local keep/exclude suggestions do not silently change this manifest.

## Proposed technical run

`configs/lora-pilot.json` records a draft configuration: 512 pixels, rank 16, BF16, batch 1, accumulation 4, learning rate 5e-5 and at most 100 optimizer steps. These are conservative experimental starting settings, not tuned recommendations. Freeze the base and text encoder; train only the adapter. Do not automatically push weights or data to a public Hub.

Use the [official Klein-specific Diffusers trainer](https://github.com/huggingface/diffusers/blob/d035dcd7cc7c88e0a154609b62887d50bba9fdc2/examples/dreambooth/train_dreambooth_lora_flux2_klein.py), pinned to the Diffusers 0.40.0 commit and SHA-256. Its original source and Apache license are cached in `artifacts/trainers/`. The script supports per-image captions through its dataset loader; an image-only directory instead uses a shared instance prompt. Our command uses `--dataset_name <export>/train --caption_column text`, never the combined dataset root or image-only path.

## Local preparation completed

- `export-training` checks curation first, writes a staged export, refuses overwrites, and records source metadata, image hashes, captions, reviewers, splits, preprocessing and the MIT notice. `verify_export` rejects missing, modified or extra files.
- Export hash: `0eaf81532ebbc8d382d5f709df179f00652914a097001a61ffaa629fe1739581`. Counts: 16 train, four validation. No additional image detail is implied by upscaling.
- `uv.lock` now includes optional training dependencies: Datasets 5.0.1, PEFT 0.21.0, Torchvision 0.25.0 and TensorBoard 2.21.0. Torch 2.10.0, Diffusers 0.40.0 and Transformers 5.17.0 remain pinned. The [official PyTorch version pairing](https://pytorch.org/get-started/previous-versions/) is used for Torchvision and CUDA 12.8 wheels.
- The real Datasets loader successfully decoded all 16 training images and verified each caption/image pairing against the export. Four validation images are excluded from its input. Metadata follows [ImageFolder conventions](https://huggingface.co/docs/datasets/image_dataset).
- The exact upstream `parse_args` function was extracted from the hash-verified source and exercised locally, without importing the GPU stack. This is a parser check, **not** a full trainer import or training test. Static inspection confirms the base transformer, VAE and text encoder are frozen before adding the adapter.
- `reports/trainer-preparation.json` records the original local checks and two-optimizer-step draft. The executed smoke used cached latents, component offload, gradient checkpointing, no flipping, no Hub upload and separate explicit adapter inference. Rank was 16; the pinned trainer's LoRA alpha remained its default 4 and target modules remained its defaults. The saved tensors subsequently verified the actual target categories.
- Local verification: 38 unit tests and Ruff pass. Visual spot checks of Brain, Seedling and Umbrella exports show intact composition and white backgrounds. No UI changes were made in this phase.
- The fail-closed Vast training smoke completed under its separate authorization. Full imports and forward/backward passed; checkpoint 1 was saved and explicitly reloaded before step 2; the step-2 adapter contains 120 finite tensors across all expected target categories and differs from the step-1 adapter. Exact-adapter inference also completed. See `reports/training-smoke.md` for measurements, costs and recovery limitations.
- Peak sampled training memory was 16,002 MiB. The two optimizer steps took 1.2104 and 1.1646 seconds, with four accumulated microbatches per optimizer step. The complete remote workload took 256.61 seconds. These timings are one-host smoke measurements, not a quality or large-run benchmark.
- The final adapter is local at `runs/lora-pilot-smoke/pytorch_lora_weights.safetensors`, SHA-256 `25b4c831d894b2e1c322f21411315270c249b405014162833cd110e67939657f`. The remote inference PNG was not recovered, so no visual claim is made. Checkpoint 1's complete state is local; checkpoint 2's optimizer state is not.
- The quality-bearing follow-up is now locally locked in `configs/lora-quality-pilot.json` and `benchmarks/lora-quality-eval.json`: 100 steps, compact adapter copies at 25/50/75/100, and 12 identical-prompt/seed base-versus-adapted pairs. Four prompts cover the validation concepts; bicycle tests an unseen object and raised hand checks an excluded domain for regression. This is still a development evaluation, not a sealed final test.
- `scripts/vast_quality_pilot.py` requires a separate exact, unexpired, single-use authorization tied to all input hashes. It permits one GPU, independently guards credit and elapsed time, downloads and checksum-validates all four adapters plus all 24 evaluation images, and ownership-checks teardown. Hard ceilings are $2 total, $0.70/hour and one hour; the measured-smoke planning proposal is $1 and 45 minutes.
- Current local verification: 55 unit tests, Ruff and the frozen lock check pass. Observed credit change across the earlier training-smoke/recovery attempts was $0.3415524277 against the prior approved $3 ceiling, subject to billing lag. At the initial local-preparation checkpoint, no new cloud call or GPU allocation had been made.
- The first quality-pilot authorization allocated instance 51770686, but the intentionally full remote test suite stopped the workload before model download or training because the minimal upload omitted the development benchmark and one prior smoke shell script used by tests. The instance was destroyed and an independent query returned zero instances. Credit initially changed by $0.0237400767 and had reconciled to $0.0612906387 by the replacement preflight. The bundle now includes complete `configs/`, `benchmarks/` and `scripts/`; all 55 tests pass both locally and from a newly extracted archive. See `reports/quality-pilot-attempt-1.json`.
- A separately authorized replacement completed all 100 steps on RTX PRO 5000 Blackwell. The 100 optimizer steps took 108.61 seconds; sampled peak training memory was 15,982 MiB. All 120 final tensors are finite, and compact adapters from steps 25, 50, 75 and 100 are local. Final adapter SHA-256: `d28456bd713d44836e7a5b323708c5ccf39f967386a6e5a1ccf43b65e4c6c63b`.
- All 24 matched evaluation images passed checksum verification. Unblinded AI review finds a clear shift toward the references' softer, simpler material language on held-out objects. Every adapted concept remains recognizable, but the unseen bicycle regresses mechanically in both seeds. The raised-hand control retains five fingers in both seeds. See `reports/quality-pilot.md`.
- Replacement credit changed by $0.3151572184 at cleanup and later reconciled to $0.3473632394. Combined latest observed quality-pilot spend is $0.4086538781, subject to further billing lag. The instance was destroyed and an independent API query returned zero instances.

Reproduce the loader and parser checks without installing Torch on this Mac:

```sh
uv sync --frozen --group training-data
uv run --frozen --group training-data python scripts/prepare_lora.py
```

The existing export is immutable. To rebuild after a deliberate curation/configuration change, use a new output path with `emoji-studio export-training --output ...`, then pass that path to `prepare_lora.py --dataset ...`. The preparation script downloads only pinned trainer source/license, not model weights. The smoke validated the Linux training environment created with `uv sync --frozen --extra gpu --group training`; future hosts must still regenerate absolute paths and recheck their own CUDA compatibility.

Decision after the quality-bearing pilot:

1. Keep the final and periodic adapters as durable learning artifacts; the pipeline and style-learning hypothesis are validated.
2. Do not promote step 100 as a universal default. Obtain blinded human review of the existing pairs, especially the style-versus-detail tradeoff.
3. If that review is inconclusive, evaluate the already-retained step-25/50/75 adapters on the same locked pairs before authorizing more training. Full optimizer-state recovery after teardown was deliberately not promised.
