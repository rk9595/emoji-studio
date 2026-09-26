# High-five capability plan

## Objective

Teach and measure one new semantic capability: two distinct hands completing a palm-to-palm high-five. This is separate from the existing style-only object LoRA.

The frozen development benchmark is `benchmarks/high-five-v1.json`. It contains four high-five cases and four nearby controls: one raised hand, folded hands, handshake and clapping. The controls matter because a model that produces two plausible hands but confuses the gesture has still failed.

## Evidence available now

Update, September 25: the [32-image matched baseline](../reports/high-five-baseline.md)
has completed and all image hashes are verified. Preliminary unblinded AI review
found no clear high-five passes in either model condition. The existing object
adapter remains the serving adapter; no interaction training has run.

The licensed Fluent source inventory contains useful anatomy and contrast concepts, including raised hand, waving hand, clapping hands, folded hands, handshake, raising hands, left- and right-facing fists, and pushing hands. It does not contain an exact high-five concept in the reviewed source revision.

Those neighboring gestures are suitable for controls and anatomy preservation. They are not positive high-five examples and must not be mislabeled as such.

## Data gate

Before training, curate or commission positive examples with explicit redistribution and training permission. A first pilot should target:

- 24–40 positive high-five images across front and slight side views;
- balanced light, medium and dark skin-tone pairings;
- clear left/right hands, separated wrists and one palm contact point;
- readable five-finger anatomy at 32 and 64 pixels;
- simple backgrounds and no text;
- 8 pose-disjoint validation positives;
- nearby negative/control examples for raised, folded, clapping and handshake gestures.

Synthetic examples may be considered only with recorded generator, prompt, model/version, date and applicable usage terms. AI-generated data must be visually reviewed; malformed fingers cannot become supervision.

Do not train on the exact frozen benchmark prompts or its generated outputs.

The executable data check is now:

```sh
uv run python scripts/prepare_interactions.py
```

Candidate records live in `configs/high-five-curation.json`. Each kept row needs a
local image and SHA-256, an accurate caption, source/permission evidence, a review
bound to that exact image hash, a pose group and a source lineage group. Related
edits and recolors stay in the same split. `decision: pending` and `reject` never
count toward readiness. Four Fluent controls have explicit AI reviews. Neither
of the two imagegen reference candidates is admitted to training.

The script checks at least eight distinct training pose groups and four validation
pose groups, as well as the 24/8 image minimums and skin-tone coverage. These
numbers are pilot requirements, not evidence that this amount of data is sufficient.

For synthetic data, an open-model candidate source to test is
[Qwen-Image-2512](https://huggingface.co/Qwen/Qwen-Image-2512), whose published model
card declares Apache-2.0. The inspected revision is
`25468b98e3276ca6700de15c6628e51b7de54a26`. This is a proposed teacher, not a proven
high-five solution. Begin with a few novel compositions, inspect actual output
anatomy, and measure memory/runtime before planning the full dataset. Do not copy
the frozen evaluation prompts into this candidate batch.

The [four-image teacher trial is now implemented](../reports/high-five-teacher-preparation.md),
including a locked sampler, independent workload timeout, verified snapshots and
a separate single-use Vast launcher. The [first execution](../reports/high-five-teacher-pilot.md)
recovered one candidate before an SSH failure; cleanup succeeded. The image shows
palm contact but has ambiguous gesture readability and photographic style, so it
is not admitted to training. A bounded recovery for the other three is awaiting
approval. Trial outputs are never automatically accepted for training.

## Baselines

Render the same fixed seeds for:

1. FLUX.2 Klein base without an adapter;
2. the selected style-only step-25 adapter;
3. prompt-only variants using explicit hand count, orientation and contact language;
4. an image-conditioned or controlled pipeline if a suitable licensed pose/reference input is available.

This determines whether another LoRA is justified. If a controlled inference method solves the task more reliably, it may be a better product choice than teaching interaction geometry through a small LoRA.

## Training experiment

If the data gate passes, start with a separate interaction adapter rather than overwriting the current style adapter. Retain frequent checkpoints and compare:

- interaction adapter alone;
- style adapter alone;
- conservative adapter composition or a jointly trained candidate;
- the unadapted base.

The first run remains single-GPU and bounded. No distributed training is justified by the current model size.

## Evaluation

Use at least two locked seeds per prompt. Human review should score each image on:

- correct hand count;
- five readable fingers per hand;
- left/right orientation;
- palm-to-palm contact;
- gesture classification: high-five versus folded, clapping or handshake;
- absence of fused, duplicated or detached anatomy;
- silhouette readability at 32 pixels;
- style consistency and transparent-background quality.

Report semantic pass rate before aesthetic preference. A polished wrong gesture is a failure.

## Go/no-go rule

Do not ship high-five generation until the selected method reaches at least 80% semantic pass rate on the frozen high-five cases, does not regress the four nearby controls below their baseline, and has no repeated severe anatomy defect across both seeds.

## Memes follow later

Meme generation should combine a generated illustration with deterministic HTML, Canvas or SVG typography. The image model should not be responsible for spelling, line wrapping or text placement. That phase starts only after the emoji interaction experiment is measured.
