# What a 16-image LoRA taught us about post-training an image model

*Draft — private review before publication*

We set out to answer a narrow question: could a small, reproducible post-training experiment teach an open-weight image model a cohesive emoji-like visual language without pretending that a weekend-scale project had produced a universal design tool?

The answer was yes for style and simple objects, and decisively no for new interaction semantics such as a high-five. That distinction became the most useful result of the project.

## What we built

Emoji Studio now contains a deterministic dataset pipeline, a FLUX.2 Klein 4B LoRA training recipe, retained checkpoints, blinded human checkpoint selection, a queued single-GPU inference service, transparent PNG/WebP export, and a private-alpha web interface.

The dataset used 16 training images and four validation images derived from Microsoft's MIT-licensed Fluent Emoji source. Every exported image has provenance, a checksum and a caption. The source artwork was natively 256×256, so the experiment was intentionally bounded: upscaling it would not invent missing detail.

Training ran for 100 optimizer steps and saved adapters at steps 25, 50, 75 and 100. The successful replacement run needed 108.61 seconds of optimizer time and approximately 15,982 MiB of sampled peak GPU memory. Including recovery work, the complete quality-pilot stage cost approximately $0.41 by observed provider-credit change.

That is enough to demonstrate a real style shift. It is not enough to justify a claim that the model understands every kind of emoji.

## We selected a checkpoint instead of assuming “later is better”

The first evaluation compared base and adapted outputs on held-out objects, an unseen bicycle and an excluded-domain raised-hand control. The adapted model consistently moved toward softer, simplified plastic forms, but it also removed useful detail. Both bicycle samples retained two wheels while regressing in crank, fork or frame coherence.

We then rendered 48 images across checkpoints 25, 50, 75 and 100 on a concept-disjoint set. A blinded interface produced 72 pairwise human decisions. Step 25 won 24 comparisons, compared with 19 for step 50 and 10 each for steps 75 and 100. We therefore locked step 25 by checksum for serving.

This was a small study, not a population-level preference evaluation. It was still materially better than choosing the final checkpoint because it happened to be final.

## Serving revealed a different class of problems

On one 40 GB A100, the service completed all 18 jobs in its real GPU test: two deterministic smoke renders and 16 requests at concurrency four. It sustained 6.73 images per minute, measured 35.93-second p95 request latency, and used 16,983 MiB of peak sampled GPU memory. A warm generation took roughly eight to nine seconds.

The concurrency test did not make one diffusion pipeline generate four images simultaneously. It exercised authentication, persistent jobs, polling, queueing and backpressure around one serialized GPU worker. That distinction matters when reporting throughput.

The service now supports deterministic seeds, per-user hashed access tokens, owner-isolated artifacts, daily and alpha-wide quotas, feedback, immediate deletion and seven-day retention. The private-alpha UI is intentionally plain because the unanswered question is utility, not visual polish.

Infrastructure also produced honest failures. A managed serverless deployment could package the application but rejected the approximately 26 MB compressed bundle because its code store was limited to 5 MB; the 32 MB LoRA was the dominant artifact. We did not publish the adapter or send it to an untrusted file host as a shortcut. A bounded ordinary GPU instance plus a localhost SSH tunnel became the private manual-test fallback.

## The high-five failure was the clearest product lesson

When asked for `hi5 emoji`, the served model returned a polished generic smiley face. The result looked like an emoji and completely failed the task.

The shorthand prompt did not help, but prompt wording is not the real explanation. Our training set taught an object-oriented visual language. It did not contain the examples required to learn two hands meeting palm-to-palm, contact geometry, finger anatomy or the semantic distinction between waving and high-fiving.

A style LoRA can change how a known concept looks. It does not automatically add a new compositional skill. Seeds merely sample other points in the model's existing distribution; they do not create a missing capability.

That result also changed the product claim. Today Emoji Studio is useful for exploring simple, centered objects in a cohesive style. It is not yet a dependable high-five generator, emoji editor, text renderer or universal sticker engine.

## What the project cost

Before the live private-alpha session, the latest whole-project estimate was approximately $3.83. That includes baseline inference experiments, training preparation and recovery, the quality LoRA, checkpoint selection and the real service load test. Provider accounting can lag, so every number is reported as an observed credit delta rather than a finalized invoice.

The surprisingly expensive parts were not the 108 seconds of successful gradient updates. Model downloads, failed hosts, uploads, evaluation rendering, artifact recovery and infrastructure validation dominated wall time and spend. This echoes a broader lesson from Hugging Face's watercolor project: rendering and reward or evaluation infrastructure can matter as much as the update step itself.

## What we would do differently

1. Define the desired semantic capability before collecting style data.
2. Separate style evaluation from task-success evaluation.
3. Keep a concept- and pose-disjoint test set from the first day.
4. Retain intermediate checkpoints and select among them blindly.
5. Test artifact movement and model caching before optimizing GPU throughput.
6. Treat a beautiful semantic miss as a failure.
7. Use ordinary layout code for text instead of asking a diffusion model to typeset memes.

## The next experiment: teach the interaction

The next phase will focus narrowly on high-fives. It will begin with a frozen evaluation set covering hand count, finger readability, palm orientation, contact point, skin-tone variation, small-size readability and absence of extra limbs. We will first measure the base model and prompt-only ceiling.

Only then will we curate or commission licensed examples of the interaction. Training and validation will be split by pose and composition family so near-duplicate hands cannot leak across the boundary. The smallest credible experiment will compare the current style-only adapter, a targeted interaction adapter, and an image-conditioned or controlled alternative on identical seeds and prompts.

For memes, the image model should generate the illustration while HTML, Canvas or another normal graphics layer handles typography. That gives us exact spelling, accessible text, editable layouts and deterministic exports.

## Reproducibility and sources

The repository contains the data audit, immutable experiment configs, evaluation reports, serving code and budgeted Vast lifecycle scripts. Training images, model adapters, credentials and cloud artifacts are deliberately excluded from source control.

- [FLUX.2 Klein base 4B model card](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4B)
- [Microsoft Fluent Emoji](https://github.com/microsoft/fluentui-emoji)
- [Hugging Face: Training Models to Paint with Code](https://huggingface.co/blog/train-to-paint-with-code)
- [Tinker forecasting recipe](https://github.com/thinking-machines-lab/tinker-cookbook/tree/main/tinker_cookbook/recipes/forecasting)

The strongest claim we can make is also the simplest: we built and exercised a reproducible post-training system, measured where it worked, preserved where it failed, and used those failures to define the next experiment.
