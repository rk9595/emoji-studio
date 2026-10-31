# Next training experiment: coverage correction

The user asked to continue training toward production on October 31. We are
preparing a separate Fluent coverage experiment under that delegation. The API
milestone is complete; it was not a model-quality acceptance test. No training
GPU has been allocated for this experiment and no adapter has been promoted.

The October 2 run completed 500 steps but sampled only 954 of 2,493 eligible
training images. Its final adapter did not establish improved gesture accuracy.
The next experiment keeps the pinned base, Fluent v2 images, provisional captions,
split, rank 16, learning rate 5e-5, seed 29, batch 1 and accumulation 4. It changes
sampling to a deterministic coverage pass. It does not add Noto, revise gesture
captions or move crossed fingers out of validation.

`configs/lora-coverage-v1.json` pins the data, trainer and development benchmark.
At step 500, the new schedule has exposed 2,000 distinct images; the final 624
steps consume 2,496 draws, covering all 2,493 assets with three repeats. Keep both
step 500 and the final adapter. Comparing the 500-step checkpoints controls step
count; comparing 624 against the old 500 also changes training duration. AMD versus
the historical NVIDIA runtime is another potential difference, so this is a
development diagnostic, not proof that the sampler alone caused any improvement.

## Implemented and verified locally

`coverage_training.py` patches the checksum-pinned upstream trainer into a new
bundle without changing the old export, its sampling file, or its trainer.
The runtime rejects recipe drift, schedule changes, validation IDs, caption/order
mismatches, a changed training budget, resume, augmentation, and multiple training
processes. The launcher must pin the runtime helper and dependency bundle too.

All 3,148 export files passed hash verification. The actual ImageFolder loader's
2,493 image/ID/caption associations were checked against decoded source-export
pixels. Torch 2.10 / Datasets 5.0.1 / Accelerate 1.15 on CPU consumed the exact
2,496-item sequence with 624 accumulation boundaries. All four patched latent/text
cache assignments preserve detached independent CPU copies. These checks do not
exercise model forward/backward or AMD kernels. The lightweight suite passed
25 tests. Preparing the same immutable bundle twice also passed.

Receipts: `reports/coverage-training-preparation.json` and
`reports/coverage-training-cpu-check.json`. Local bundle:
`artifacts/trainers/coverage-v1/`. Local CPU environment:
`var/coverage-validation/`; it is not the AMD dependency lock.

```sh
PYTHONPATH=src var/coverage-validation/bin/python -m emoji_studio.coverage_training \
  --recipe configs/lora-coverage-v1.json \
  --output artifacts/trainers/coverage-v1 \
  --report reports/coverage-training-preparation.json
PYTHONPATH=src var/coverage-validation/bin/python scripts/check_coverage_training.py
```

## Next execution work

Build a fresh private training lifecycle using the proven AMD allocation/deletion
controls. Do not repurpose a consumed API/comparison claim. Proposed bound: one
MI300X, one allocation, at most 60 minutes, hourly ceiling $1.99 and total ceiling
$2.25. Refresh availability/rate and Codex usage before allocation. Retain the
85% usage stop, independent cloud watchdog, instance expiry, private checkpoint
backup and independent deletion check. No GPU may wait for quota reset.

The inference overlay is not yet a validated AMD training environment. Add/pin
training dependencies, run a short finite-loss/checkpoint-reload smoke, and only
then run the frozen recipe within the same elapsed/cost cap. The smoke needs its
own explicit small diagnostic schedule; do not quietly override this recipe's
624-step guard. A failed smoke must stop and clean up, not launch a replacement.

Evaluate step 500 and 624 with the frozen twelve development prompts and two
seeds: at most 48 new evaluation images. Recover and hash-check historical base
and old step-500 outputs for comparison rather than repeating the consumed AMD
comparison. Score meaning, anatomy/contact, tone, object geometry and 32px/64px
readability separately from style. Label AI judgments as AI; captions remain
metadata-checked rather than individually visually approved. Crossed fingers is
held out; high-five and pinky promise have no training examples here. More steps
alone do not establish these capabilities.

Keep serving pilot step 25 until a documented comparison supports promotion.
Noto licensing/data work, robust cutouts and durable production-worker validation
remain separate work. No persistent hosting or automatic adapter promotion is
part of this training experiment.

## Bounded cloud implementation prepared

The independent training controller and worker now exist in
`ops/amd_training_live.py` / `ops/amd_training_worker.py`. The dedicated live plan
controls this separate execution; the immutable recipe retains its historical
preparation flags. A separate eight-image/two-step smoke package is prepared;
finite TensorBoard losses, finite learned adapter tensors and successful reload
are required before main training. Checkpoints are copied privately as they appear.
One reload image plus48 development images is the total physical render cap.
The worker refuses restarts, existing outputs, altered input hashes and changed
GPU packages. Cloud work stops at55 minutes and independent expiry starts at56.

The74-package training overlay preserves all inference pins except fsspec,
changed from2026.9.0 to2026.6.0 to satisfy Datasets5.0.1. It excludes provider GPU
packages and installs with hashes and no dependency traversal. Full trainer
import and package compatibility passed in the isolated Mac environment; Linux
and actual AMD forward/backward remain cloud checks. Receipts:
`reports/amd-training-environment.json`, `reports/coverage-smoke-preparation.json`.
58 focused tests passed, including deletion ownership, early usage binding,
artifact bounds and preservation of child-process result records.
