# High-five capability plan

## Objective

Teach and measure one new semantic capability: two distinct hands completing a palm-to-palm high-five. This is separate from the existing style-only object LoRA.

The frozen development benchmark is `benchmarks/high-five-v1.json`. It contains four high-five cases and four nearby controls: one raised hand, folded hands, handshake and clapping. The controls matter because a model that produces two plausible hands but confuses the gesture has still failed.

## Evidence available now

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
