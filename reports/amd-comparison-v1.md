# Retained-adapter comparison — October 13, 2026

Decision: retain the reviewed pilot step-25 serving adapter. No collection
checkpoint earns promotion from this diagnostic. This is **AI visual review,
not human review**, and does not establish a statistically significant winner.

## Execution and provenance

The base model, pilot step 25, and collection steps 125/250/375/500 each rendered
the same 12 development prompts at seeds 0 and 1: 144 images. All input locks,
adapter hashes, image hashes, identities and metadata verified locally through
`scripts/amd_compare.py review`. Runtime: MI300X, PyTorch 2.10.0 ROCm 7.2;
evaluation wall time 607.25 seconds, including model setup. This is not a
per-request latency measurement.

Private execution: [successful run](https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272).
Private artifacts: [release](https://github.com/rk9595/emoji-studio-ops/releases/tag/amd-comparison-v1).
Local gallery: `runs/amd-comparison-v1/checkpoint-review.html` (120 randomized
incumbent-versus-candidate pairs). Weights and images were not published publicly.

Four allocated attempts together lasted 1,792.29 seconds, including startup and
cleanup: approximately **$0.99 at the observed $1.99/hour rate**, not a billing
receipt. Final droplet `608604896` deletion was confirmed at 05:58:48 UTC.
Independent provider lookup afterwards returned zero campaign droplets. The $3
reserve was not exhausted. No fifth allocation is permitted for this campaign.

The final startup repair closed one provider-bootstrap SSH connection whose
cached forced command kept returning a provisioning banner. Future readiness
checks use fresh SSH sessions; multiplexing starts only after clean readiness.
Input transfer, inference, snapshots and deletion then completed automatically.

## Label-blinded AI observations

All images were inspected in 24 shuffled A–F montages, including 32px thumbnails.
Observations were committed as `87a7e24` before decoding checkpoint identities.
The ordinal rubric distinguishes major failures (0), partial/uncertain results
(1), and major requested details met without obvious material defects (2).
It is not a calibrated quality metric or a substitute for independent reviewers.

| Condition | Major failures | Partial/uncertain | Major details met |
|---|---:|---:|---:|
| Base | 14 | 6 | 4 |
| Pilot 25 | 14 | 6 | 4 |
| Collection 125 | 14 | 7 | 3 |
| Collection 250 | 15 | 6 | 3 |
| Collection 375 | 15 | 7 | 2 |
| Collection 500 | 15 | 6 | 3 |

Each row contains 24 outputs, deliberately weighted toward difficult gestures:

- All 60 crossed-fingers outputs failed the crossing requirement, generally
  showing one raised finger; one showed two parallel fingers.
- All 12 high-five outputs read as folded/praying hands, explicitly excluded by
  the benchmark. All 12 pinky-promise outputs failed little-finger linking.
- All 12 backpacks retained the requested object and colors clearly.
- Faces were coherent, but sweat drops and watery pleading eyes were inconsistent.
- Firefighter helmets remained ambiguous with construction-worker hard hats.
  Bicycles were recognizable but pedal/axle geometry remained incomplete or
  uncertain, with one visibly disconnected handlebar.

The 84 gesture failures are shared across all six conditions. The collection
adapters did not solve those failures, and their small score differences on this
24-output sample do not justify replacing an already reviewed serving adapter.
The base/pilot tie does not invalidate the earlier independent human selection.
These are development prompts, not a sealed generalization test; the five
crossed-finger tones are correlated variants, not five independent concepts.

## Next action

Combine this evidence with `reports/collection-coverage-audit.md`: the next
quality intervention should address relationship captions and sampler coverage,
not automatically extend the same training run. Prepare a versioned data/sampler
proposal, retain the old dataset and held-out split, and keep serving pilot 25.
No new training is authorized by this report itself.

For private alpha, implement the control-plane/worker boundary locally first;
see `docs/private-alpha-deployment-plan.md`. Live AMD web/API smoke remains
separate from this successful evaluator run. No persistent public deployment
or additional paid GPU has been started.

## Reproduction

After restoring private results under `runs/amd-comparison-v1`:

```sh
python scripts/amd_compare.py review
python scripts/build_amd_review_sheets.py
python scripts/build_amd_review_sheets.py \
  --observations reports/amd-comparison-ai-observations.json \
  --summary-output reports/amd-comparison-ai-summary.json
```

The summary validates full observation coverage and maps every label back to a
verified image hash. Observation SHA-256:
`1e872bc94c7d7617948cfd55ed7e0b06b1280e5a83103edf961feadd18ae35a9`.
Private results archive SHA-256:
`1c31350a4cb783b742371d7c17c6ba947f266e07bad565f1964f2c5336a72243`.
