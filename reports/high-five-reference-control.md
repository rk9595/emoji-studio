# Reference preservation is not pose control

Completed September 27, 2026. **8/8 images generated, downloaded and verified.**
GPU destroyed after 10.01 minutes; independent provider check showed zero instances.
Later observed cost: **$0.1774972596** against the approved $1.25 additional limit.
No interaction training, no automatic acceptance of generated images.

## Result

In this small, unblinded AI review, all four image-conditioned outputs closely
preserve their selected source's geometry and golden style. None clearly performs
the requested substantial forearm shortening or elevated-camera change. The
text-only controls vary more, but some lose clear palm-to-palm contact or become
folded/clapping-like. This establishes neither dependable high-fives nor useful
new-pose generation. Human per-image rubric review remains pending.

The practical distinction is between retaining an example and learning to produce
new interactions. Reference input demonstrably changes these matched outputs,
but retaining nearly the same pose does not create independent training examples.
These observations apply to this checkpoint, these descriptive prompts and four
matched pairs—not all FLUX editing or imperative edit prompts, which were not tested.

## Matched evidence

Each pair shares its prompt, seed, base model and settings; only the second member
receives actual reference pixels. No style LoRA was loaded. Source PNGs:
[004](../docs/images/high-five-teacher/qwen-hi5-004.png) and
[D-1401](../docs/images/high-five-golden/golden-d-1401.png).

| Source / task / seed | Text-only output | Image-conditioned output | Preliminary observation |
| --- | --- | --- | --- |
| 004 / compact / 2101 | [PNG](../docs/images/high-five-reference/ref-004-compact-text.png) | [PNG](../docs/images/high-five-reference/ref-004-compact-image.png) | Text: two nearly side-by-side backs of hands, unclear palm contact, arms reach frame edges. Image: source's overlapping fan retained; long arms still reach frame edges. |
| 004 / elevated / 2102 | [PNG](../docs/images/high-five-reference/ref-004-elevated-text.png) | [PNG](../docs/images/high-five-reference/ref-004-elevated-image.png) | Text: overlapping hands, rear fingers partly occluded. Image: near-source pose, no clear elevated-camera change. |
| D-1401 / compact / 2201 | [PNG](../docs/images/high-five-reference/ref-1401-compact-text.png) | [PNG](../docs/images/high-five-reference/ref-1401-compact-image.png) | Text: compact framed wrists, but contact is near the inner finger edges rather than an unmistakable palm strike. Image: source's asymmetric arms retained; no clear shortening into stubs. |
| D-1401 / elevated / 2202 | [PNG](../docs/images/high-five-reference/ref-1401-elevated-text.png) | [PNG](../docs/images/high-five-reference/ref-1401-elevated-image.png) | Text: cuff-like wrists and folded/clapping-like contact. Image: near-source pose with material/lighting differences; no clear elevated-camera change. |

Inspection included all full-resolution outputs and the gallery's 32/64px views.
At small sizes contact and occluded fingers remain hard to assess; no human
readability or anatomy grade is inferred. Missing visibility is not proof of a
missing finger. The user's approvals of original 004 and D-1401 remain intact and
do not propagate to these variants. All eight human review rows are unanswered.

All public PNGs are byte-identical to the generated files. Full hashes, prompts,
seeds, timestamps and per-image measurements are in the unchanged
[sampling receipt](high-five-reference-samples.json). Receipt image paths are
relative to the local experiment directory; the table above links public copies.

## Runtime, cost and cleanup

- Model: FLUX.2-klein-base-4B, revision `a3b4f4849157f664bdbc776fd7453c2783562f4d`.
- Plan: `b7686bf8c93ad0722b5b33d04b9bc7c927d771a2a7459de7def8eb781192eeb1`.
- 1024-square outputs and reference inputs, 50 steps, guidance 4, BF16,
  model CPU offload and VAE tiling; no adapter. References resized from their
  original 1328-square RGB images with Pillow LANCZOS, without altering sources.
- GPU: NVIDIA RTX PRO 5000 Blackwell; PyTorch 2.10.0+cu128. Dependencies from the
  frozen lockfile, including Diffusers 0.40.0 and Transformers 5.17.0.
- Text-only: mean 31.09 seconds/image, peak allocated VRAM up to 7.82 GiB.
  Image-conditioned: mean 59.57 seconds/image, peak up to 9.24 GiB. These are
  PyTorch allocation peaks, not total device memory or end-to-end service latency.
- Total measured inference 362.66 seconds; whole allocation 600.30 seconds.
- One instance, 52886728 (`emoji-teacher-b54eb0e0e3`), $0.6711111111/hour.
  Created epoch 1790485506.585121; destroyed at 1790486106.883870, well before
  absolute deadline 1790488206.585124. Launcher exited successfully.
- Observed cost at cleanup $0.1383725356, later $0.1774972596; credit $4.9742964380.
  Later provider query again reported zero instances. Billing can lag; observations
  are credit changes, not a finalized invoice. Qwen candidate trials plus this
  comparison total about $1.2141703989 by the recorded credit changes.
- Approved limits: $1.25 additional, <=$0.80/hour, one GPU, 45 minutes. Authorization
  is now consumed and closed. No further rental or training is authorized.

Private authorization, allocation, archive, watchdog, cleanup and cost receipts
remain under `artifacts/vast-reference-control/emoji-teacher-b54eb0e0e3/` (authorization
in its parent). The inspected upload had 30 entries, 2,861,260 bytes, exactly the
two approved reference PNGs, and no private review records or credentials.

## Review and next decision

Local paired gallery: `runs/high-five-reference-control-v1/review.html`, opened
in the browser. It shows both original sources, four paired comparisons and
32/64px previews. Browser validation found four pairs and all 26 image elements
loaded. Review rebuilding preserves existing hash-bound human answers.

Do not scale this unchanged recipe or count its four conditioned outputs as four
new poses. Keep the two original preferred references. Before more paid sampling,
choose a genuinely different way to obtain controlled, diverse interaction
examples, or explicitly scope a separate edit-instruction diagnostic; neither
is authorized by this completed run. Any source-derived variants stay in their
source lineage/split. The 24-training/8-validation, pose-disjoint and skin-tone
data gate remains unchanged, with zero accepted high-five positives.

Reproduction commands and pinned primary-source documentation are in the
[preparation protocol](high-five-reference-control-preparation.md). Verification:
all 125 tests and Ruff pass, both historical Qwen trials still verify, and the
public image checksums match the eight sampling receipts. These checks establish
artifact integrity, not semantic success.
