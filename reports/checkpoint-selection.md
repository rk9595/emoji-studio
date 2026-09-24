# Checkpoint selection evaluation

Status: **complete; step 25 selected by blinded human review**.

The retained step-25, step-50, step-75, and step-100 LoRA adapters were evaluated on a concept-disjoint development set. None of the six prompt concepts appears among the 16 training or 4 validation concepts. Each prompt used two fixed seeds, producing 12 matched sets and 48 verified images.

## Locked evaluation

- Concepts: pineapple, ladybug, bicycle, kick scooter, instant camera, and teapot.
- Seeds: 17 and 29.
- Sampling: 512 × 512, 50 steps, guidance 4.0.
- Conditions: four retained adapters, with identical prompt and seed within each matched set.
- Output: 12 images per checkpoint, 48 total.
- Integrity: every local image checksum matches `runs/checkpoint-selection/report.json`.
- Report SHA-256: `c443af2f92dcbaac9dc96250f9e93168de8da2f63fe548845ac8174a199cfe48`.

The completed evaluation recorded 660.804 seconds of aggregate image generation time, 13.767 seconds per image on average (12.571 minimum, 33.005 maximum). The resumed run's wall time, including model and adapter setup plus 36 new renders, was 609.649 seconds. Sampled peak GPU allocation was 7,998.9 MiB and peak reservation was 8,026.0 MiB with model CPU offload.

## Blinded review result

The human review export contains all 72 expected decisions and matches the locked review ID. No candidate was marked with a severe geometry error. The resulting scores were:

| Checkpoint | Wins | Losses | Both unusable | Severe flags | Preference score |
| ---: | ---: | ---: | ---: | ---: | ---: |
| **25** | **24** | **8** | 4 | 0 | **24.0** |
| 50 | 19 | 12 | 5 | 0 | 19.0 |
| 75 | 10 | 21 | 5 | 0 | 10.0 |
| 100 | 10 | 22 | 4 | 0 | 10.0 |

Step 25 beat each later checkpoint in direct comparison: 8–3 over step 50, 8–2 over step 75, and 8–3 over step 100, with the remaining comparisons marked both unusable. This is a decisive result rather than a tie-break outcome. The serving configuration now locks the step-25 adapter and its SHA-256.

The structured-object comparisons most clearly favored step 25. Mechanical geometry remained the weakest category across all checkpoints: 9 of its 24 pairwise comparisons marked both candidates unusable. Selecting step 25 reduces later-training regressions, but does not make bicycles and scooters production-safe.

Review artifacts:

- Human export: `runs/checkpoint-selection/human-review.json` (`f187ea03806413b781202e8140db9b03b903bdce3523e943c101fcf1fa4a1c0a`).
- Decoded selection: `runs/checkpoint-selection/selection.json` (`fb92c27e4961b98129e3f4951898a7adac7492404d7edeeceac4bb7a4de75b6b`).
- Selected adapter: `runs/lora-quality-pilot/adapters/step-25.safetensors` (`2c7b15de79e9ac0bf59488068c9ec0f3444dec44899005499de87c2b28e93076`).

## Reproducing the review

Open [`runs/checkpoint-selection/checkpoint-review.html`](../runs/checkpoint-selection/checkpoint-review.html) directly in a browser. It contains all six checkpoint pairings for each of the 12 matched prompt/seed sets: 72 decisions total. Candidate sides are deterministically randomized, image filenames are opaque, and the checkpoint mapping is kept separately in `blind-map.json`.

For each comparison:

1. Prefer A or B based on prompt fidelity, emoji-style coherence, and readability at small size.
2. Use **Tie** only when the results are genuinely equivalent.
3. Use **Both unusable** when neither meets the prompt.
4. Mark severe geometry errors independently for either side.
5. Export `checkpoint-review.json` after all 72 decisions.

Decode a completed export with:

```sh
uv run python scripts/analyze_checkpoint_review.py /path/to/checkpoint-review.json
```

The locked rule selects the highest pairwise preference score among checkpoints with fewer than two severe-geometry flags. The earliest checkpoint wins an exact score tie. If every checkpoint has repeated severe regressions, no checkpoint is selected.

For a new independent review, do not inspect `blind-map.json` before exporting the decisions. The completed first review is preserved; rerunning the analysis yields the same step-25 recommendation.

## Cloud lifecycle and cost

All work used one GPU at a time with single-use authorization records, an independent elapsed-time/credit guard, ownership-checked teardown, and no credentials in remote bundles. All instances are destroyed.

The provider reported these per-attempt credit changes:

- Allocation-response/upload timeout recovery: $0.1631.
- Retry that exposed the missing PEFT inference dependency: $0.2133.
- Partial render that exposed inference-mode adapter switching: $0.2979; it preserved 12 verified step-25 images.
- Successful resumable completion of the remaining 36 images: $0.2611.

The per-attempt sum is approximately **$0.94**. Because provider billing updates lag, the latest account-credit difference across the checkpoint-selection work is approximately **$1.02**. This brings the latest whole-project estimate from about $2.24 to about **$3.26**, still below the recommended $5 productization experiment budget. No active spend remains.

## Engineering findings

- PEFT is required for LoRA inference, not only training. It now belongs to the shared `gpu` dependency extra, fixing both evaluation and the real serving path.
- `torch.inference_mode()` is unsafe when PEFT adapters must be reactivated after a render because cached inference tensors cannot have `requires_grad` toggled. The evaluator uses `torch.no_grad()` instead.
- Provider allocation requests can time out after committing. The lifecycle now recovers only an instance carrying the exact unique label, preventing accidental duplicate allocation.
- Intermediate snapshots now omit the exit marker until it exists, allowing partial image receipts to be backed up and resumed.
- Local upload bandwidth, not GPU work, dominated this experiment's wall time and cost. Future deployment should keep adapters and model cache close to the GPU worker.
