# Golden high-five audition: consistent style, limited pose diversity

September 27, 2026 review of the completed September 26 run. **Eight of eight
images are generated, downloaded and checksum-verified.** Cleanup succeeded after
29.04 minutes; a fresh provider check confirmed zero active instances. No interaction
training ran and no candidate was automatically accepted into a training split.

The user's approved target remains the earlier `qwen-hi5-004`: a high-five gesture
in a golden-yellow rounded 3D style. This audition used that image as a visual
review reference, not as an image input to the model.

## What the images show

Preliminary, unblinded AI inspection of every original PNG and browser-rendered
32/64-pixel previews found consistent golden, smooth 3D styling across this batch.
Composition was less controllable: A and B overlap strongly in appearance, C tends
toward folded hands, and D changes the arm approach more visibly. Four different
prompt labels are not evidence of four independent pose families.

| Candidate / original PNG | Preliminary visual finding | Review priority |
| --- | --- | --- |
| [A-1101](../docs/images/high-five-golden/golden-a-1101.png) | Broad open-hand overlap, distinct outer thumbs; similar to the approved target. Rear fingers partly obscured; long arms meet the image edge. | Shortlist for human review. |
| [A-1102](../docs/images/high-five-golden/golden-a-1102.png) | Very similar upright pose to A-1101 with slightly different spacing and finger alignment. | Alternate, not independent pose evidence. |
| [B-1201](../docs/images/high-five-golden/golden-b-1201.png) | Palm-contact reading is plausible, but the requested elevated camera is not clearly distinct from A. Rear-hand digit count remains uncertain. | Hold; limited new composition value. |
| [B-1202](../docs/images/high-five-golden/golden-b-1202.png) | Another tight upright overlap with forearms reaching the frame edges. | Hold; close to A/B rather than a clearly new pose. |
| [C-1301](../docs/images/high-five-golden/golden-c-1301.png) | Symmetric inward thumbs and upright hands strongly read as folded/praying hands, especially at small sizes. | Do not shortlist as a positive high-five target. |
| [C-1302](../docs/images/high-five-golden/golden-c-1302.png) | Narrow side-on contact has substantial folded-hands ambiguity. | Hold; not a clear gesture pass. |
| [D-1401](../docs/images/high-five-golden/golden-d-1401.png) | More asymmetric arm approach and more open fingers; hand contact remains visible. Forearm ends are cut flat inside the frame. | Shortlist for human review, including crop treatment. |
| [D-1402](../docs/images/high-five-golden/golden-d-1402.png) | Diagonal arms, but a tighter upright hand silhouette than D-1401. Flat arm ends and gesture ambiguity remain. | Alternate; not a clear improvement over D-1401. |

These are review notes, not human labels, a blinded ranking or a measured semantic
pass rate. Occluded fingers are not proof of malformed anatomy, but also do not
provide evidence that every digit is correct. The user's approval of the original
004 does not automatically approve these eight outputs.

At small sizes the golden material remains recognizable; the exact gesture is
less discriminable, especially for C. Most A/B/C images also ignore the requested
short forearms and all-around margins. D moves the arm ends inside the frame, but
their abrupt cutoffs need an explicit design decision rather than an automatic pass.

## Reproducible workload and receipts

- Config: `configs/high-five-golden-audition.json`.
- Plan: `6820fb673cc9a80a91b1d1883d932923bdc3dbec5a9bfbe68c8beeb3740958fa`.
- Model: `Qwen/Qwen-Image-2512`, revision
  `25468b98e3276ca6700de15c6628e51b7de54a26`.
- Four composition prompts × two fixed seeds, eight text-only outputs.
- 1328 × 1328, 50 steps, true CFG 4.0, BF16, CPU offload and VAE tiling.
- Device reported by PyTorch: NVIDIA RTX PRO 5000 Blackwell; PyTorch 2.10.0+cu128.
- Inference: 117.83–131.38 seconds per image, 121.58-second mean; 972.66 seconds
  total inference. These exclude container setup, model download and loading.
- Peak PyTorch-allocated GPU memory: about 38.68 GiB, not total device memory use.

[Captured sampler receipts](high-five-golden-samples.json) include exact prompts,
seeds, image hashes, timestamps, per-image device metadata and pending curation
decisions. Their image paths are relative to the original run directory; the table
links byte-identical public copies. No PNG has been edited for this report.

```sh
uv run python scripts/sample_golden_teacher.py verify
uv run python scripts/build_teacher_review.py --trial golden
```

Local gallery: `runs/high-five-golden-audition-v1/review.html`. Its separate human
review template contains eight unanswered records bound to the exact PNG hashes.
The original four-image trial and 004's gesture/style approvals remain intact.
All 119 local tests and Ruff passed. The training-data preflight was rerun and
still reports zero accepted positives and the unmet 24/8, pose and tone requirements.

## Cost and cleanup

Approved limits: $1.25 total, <=$0.80/hour, one GPU, 45 elapsed minutes. The rented
offer was $0.6844444444/hour including allocated disk, plus transfer charges.
Cleanup confirmed after 1,742.20 seconds (29.04 minutes), below the cutoff.

Observed cost was $0.4157023260 at cleanup and $0.4386603880 after the September 27
billing reconciliation. Credit moved from $5.5904540856 to $5.1517936976. Combined
observed spend for the earlier four-candidate Qwen trial and this audition is
$1.0366731393. These are provider-credit deltas, not finalized invoices.

Private lifecycle evidence is under
`artifacts/vast-golden-audition/emoji-teacher-d4ed3f2183/`. No transport-retry log was
recorded for this run. The allocation is destroyed, authorization consumed and
workload complete. Continuing this project does not reuse that rental authorization.

## Decision and next step

The trial supports a narrow conclusion: this prompt set reproduced the desired
golden material consistently. It did not establish reliable pose control, complete
anatomy verification, four distinct pose families or a deployable high-five generator.
Prompt styling also changed relative to the first trial, so this is not an isolated
measurement of the effect of color or any individual phrase.

Ask the user to compare **A-1101 and D-1401** with the approved 004 before spending
more. If the asymmetric D direction is useful, prepare an explicit pose/reference
control experiment rather than bulk-generating more variants of the same upright
shape. The current pipeline has not tested image conditioning, so do not promise
that a reference-guided method will work before measuring it.

The training gate remains closed: zero fully accepted high-five positives, four
existing controls, and unmet 24-train/8-validation, pose-diversity and skin-tone
coverage requirements. These eight golden images alone cannot satisfy that gate.
