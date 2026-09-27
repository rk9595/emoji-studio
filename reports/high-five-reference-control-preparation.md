# High-five reference-control comparison: preparation protocol

Historical preparation snapshot below. The trial subsequently received explicit
approval and completed 8/8 outputs; see [results and cleanup](high-five-reference-control.md).
Its authorization is consumed and cannot fund another rental.

Prepared September 27, 2026. No new image generation, interaction training, compute
authorization or GPU rental has occurred in this phase.

## Question and method

Can actual image conditioning preserve the two user-selected high-fives while
changing framing or viewpoint? The earlier Qwen trials were text-only; their
reference metadata was never model input. This trial supplies real pixels.

Use the existing, unadapted FLUX.2-klein-base-4B checkpoint at revision
`a3b4f4849157f664bdbc776fd7453c2783562f4d`. Its [pinned model
card](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4B/blob/a3b4f4849157f664bdbc776fd7453c2783562f4d/README.md)
describes reference editing and declares Apache-2.0. Reviewed card SHA-256:
`728ef6804ff3f38528c24ab9e3d168d579e77d57342c30ea01310eaa70e95016`.
The installed [Diffusers 0.40.0 pipeline
source](https://github.com/huggingface/diffusers/blob/v0.40.0/src/diffusers/pipelines/flux2/pipeline_flux2_klein.py)
accepts `image=` and encodes image-conditioning latents. No dependency upgrade,
ControlNet, skeleton control, new adapter, or separate editing model is required.

This is a practical method choice, not evidence that editing succeeds on hands.
We omit the style LoRA in both conditions to isolate reference input on one model.
The earlier FLUX benchmark used different prompts/settings and cannot serve as
this experiment's matched control. Each pair here uses identical descriptive
prompt, seed, model, 1024-square output, 50 steps and guidance 4. Only one member
receives a reference. Same seed is not a claim that all internal execution is identical.

| Source | Task | Seed | Conditions |
| --- | --- | --- | --- |
| 004 | Compact framing and shorter forearm stubs | 2101 | Text only / actual image input |
| 004 | Elevated 35-degree three-quarter camera | 2102 | Text only / actual image input |
| D-1401 | Compact framing and shorter forearm stubs | 2201 | Text only / actual image input |
| D-1401 | Elevated 35-degree three-quarter camera | 2202 | Text only / actual image input |

Eight outputs, four diagnostic pairs, one seed per source/task. This is too small
to establish dependability or a general success rate. Compact framing tests
preservation/layout, not new pose diversity. The elevated view is a requested
change, not a guaranteed new pose. Actual geometric change must be reviewed.

## References, provenance and review

- [004](../docs/images/high-five-teacher/qwen-hi5-004.png): human approved gesture
  and golden 3D style; anatomy and small-size rubric fields remain unanswered.
  SHA-256 `c51db19bc58a3a77f77cb8b699b5fc4bb4f9705a8f410aa394ec60a7d30aae4f`.
- [D-1401](../docs/images/high-five-golden/golden-d-1401.png): user said “1401 looks
  good to me.” Recorded as a keeper/reference, not six separate rubric approvals.
  SHA-256 `bf424e729d5a1e49a2c63294768edd6a86238c4ff05eef35940176544263d22d`.

Both are local Qwen-generated originals with pinned source model/config receipts:
[first pilot](high-five-teacher-pilot.md) and [golden audition](high-five-golden-audition.md).
The upload includes only these two public PNGs, not private human review files.
Hash/path/lineage are allowlisted. For inference they become RGB and are resized
from 1328 square to 1024 square with Pillow LANCZOS; original files are unchanged.

Keep derivatives of each source in its source lineage/split. Paired text-only
controls are conservatively grouped with that source too. Do not automatically
count recolors, crops, seeds, mirrors or camera wording as independent training
poses. No candidate inherits human approval. Review high-five semantics, contact,
wrist separation, anatomy (including uncertainty from occlusion), golden style,
32/64-pixel readability and whether the requested change actually happened.

Proceed to a broader controlled candidate collection only if the edited results
preserve the desired interaction and show useful control. If only framing works,
record it as a layout improvement, not an interaction-generation solution. If
reference input does not help, stop this route before scaling it. Even successful
results cannot meet the unchanged 24-train/8-validation, pose-disjoint and skin-tone
training gate by themselves. This phase does not authorize training.

## Reproduction and proposed compute boundary

```sh
uv run python scripts/sample_reference_control.py plan
# Only after a new, explicit budget approval and a fresh hash-bound local record:
uv run python scripts/vast_teacher_pilot.py --trial reference --authorization <path>
# After real outputs exist:
uv run python scripts/sample_reference_control.py verify
uv run python scripts/build_teacher_review.py --trial reference
open runs/high-five-reference-control-v1/review.html
```

Configuration: `configs/high-five-reference-control.json`; sampler:
`scripts/sample_reference_control.py`. Private artifacts:
`artifacts/vast-reference-control`; output: `runs/high-five-reference-control-v1`.
Locked plan: `b7686bf8c93ad0722b5b33d04b9bc7c927d771a2a7459de7def8eb781192eeb1`.
The sampler locks input hashes, supports verified partial resume, uses actual
`image=` only in the conditioned jobs, and leaves every curation decision pending.
The shared launcher retains single-use trial-bound authorization, result checks,
remote timeout, watchdog, cleanup reserves and refusal to rerent completed work.
Original Qwen sampler files and plan hashes are unchanged.

Proposed new limit: **$1.25 additional total, <=$0.80/hour, one GPU, 45 minutes**.
Retain the already-tested conservative >=48 GB advertised GPU / >=128 GB host RAM
offer filter; this is not a claim that FLUX requires that much memory. Read-only
marketplace check September 27 found three qualifying offers, lowest advertised
hourly cost $0.6711111111, zero instances, and $5.1517936976 credit. These observations
are not a price guarantee or authorization. No new authorization file was created.
The previous pilot/golden approvals are consumed and must not be reused.

The guard reserves $0.15 and three minutes for cleanup; remote process timeout
also bounds inference. Neither mechanism guarantees a billing cap during provider
or network failures. The earlier cleanup-overrun incident remains documented.

Local verification: 125 tests and Ruff pass, including mock sampling of all eight
jobs, exact resized input pixels, paired seeds/prompts, no adapter loading,
partial resume, archive extraction/recomputed plan, two-reference-only packaging,
budget isolation and unchanged historical plans. These are software checks, not
GPU execution or evidence of visual quality.
