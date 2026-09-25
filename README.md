# Emoji Studio

An open-model post-training project for **new emoji concepts in a familiar visual language**. Emoji-sized images and larger stickers share a model; they do not become new Unicode characters or automatically appear in phone keyboards.

## Current milestone

Working: pinned Fluent asset importer, provenance and resolution audit, 40 development prompts, offline reference review, immutable baseline manifests, and a resumable CUDA inference runner.

Real CUDA inference and automatic Vast provisioning, backups, and teardown have been exercised. The original four outputs are diagnostic only: the v1 style brief truncated SDXL's gesture request. Corrected v2 plans put the task first and preflight both SDXL tokenizers before loading image-model weights.

The corrected four-image smoke test is complete. Both models missed the requested gestures; no model winner has been selected. See [measured results, costs and next experiment](reports/smoke-test.md). All instances were destroyed. Eight actual outputs, including the four original diagnostics, are available in the offline workbench.

Latest September 16 update: all [16 control images](reports/sanity-1024.md) are complete after resuming five Klein jobs without regenerating saved outputs. Both models can render coherent objects but miss the two-hand interactions. The viewer now has 24 real outputs; total observed spend is about $1.49, allocated time about 111 minutes, and zero instances remain.

A [first object-only LoRA pilot](reports/quality-pilot.md) completed 100 optimizer steps and 12 matched base/adapted evaluation pairs. The adapter shows a real shift toward the softer, simplified reference style on held-out objects, while both unseen-bicycle samples show mechanical-geometry regressions. A subsequent [checkpoint-selection evaluation](reports/checkpoint-selection.md) rendered 48 verified concept-disjoint samples across steps 25/50/75/100. The completed 72-comparison blinded human review selected step 25 decisively, and serving now locks that adapter by checksum.

The [real single-GPU service load test](reports/service-load-test.md) is complete. On one 40 GB A100, all 18 generation jobs succeeded: two deterministic smoke renders plus 16 requests at concurrency 4. The service sustained 6.73 images/minute, recorded 35.93-second p95 request latency, produced checksum-identical seeded PNG/WebP exports, rejected an unauthenticated request, peaked at 16,983 MiB sampled GPU memory, and unloaded the model after the idle threshold. All cloud instances are destroyed.

For the current model's evidence-backed strengths and limitations, use the [prompt guide](docs/prompt-guide.md). A publication-oriented account of the full experiment is available as a [technical retrospective draft](docs/blog/what-a-small-image-lora-taught-us.md).

The [high-five baseline](reports/high-five-baseline.md) now contains 32 verified
base/step-25 images. Preliminary AI inspection found no clearly correct high-five
in either set of eight, plus a six-digit hand regression in one adapted control.
The interaction data check and review gallery are implemented; four licensed hand
controls are curated, but positive high-five data is still missing. No interaction
adapter has been trained. The same report records a $0.56 observed overrun in the
old manual-test session and late watchdog cleanup; zero instances were verified
on September 25.

The two-step cloud lifecycle in `scripts/vast_train.py` requires a separate, unexpired, single-use authorization record. It permits one GPU only, independently checks the marketplace offer against the authorized hourly rate, enforces provider-credit and wall-clock guards, snapshots checkpoints locally, and destroys the owned instance on exit. The completed smoke ran one optimizer step, saved checkpoint 1, resumed for checkpoint 2, validated finite saved adapter tensors and target categories, then loaded that exact adapter for a four-step inference check. All instances are destroyed.

The first serving vertical slice is implemented and exercised on a rented GPU: bearer authentication, request IDs, a persistent single-worker queue, deterministic seeds, lazy model/adapter caching, idle GPU unload, status polling, transparent PNG/WebP exports, pack requests, a browser UI, a small Python client, and Prometheus metrics. Private-alpha controls now add hashed per-user tokens, owner-isolated history and downloads, persistent daily and 100-image trial quotas, request rate limits, seven-day deletion, explicit feedback, user deletion, and an alpha decision report. The local deterministic mock integration test remains the inexpensive regression path.

Not yet done: a persistent public control-plane deployment, a custom hostname, image editing, or messaging integration. A one-worker Vast serverless GPU definition is ready, but Vast's 5 MB deployment-code storage limit cannot hold the approximately 32 MB selected adapter. A bounded ordinary-instance session therefore provides private testing through a localhost SSH tunnel without publishing the adapter; it is not the final public-alpha architecture. Mechanical objects such as bicycles and scooters remain a known weakness even with the selected checkpoint. Reference artwork is never presented as generated output. Browser reviews are curation suggestions, not approval to train.

## Run the generation service

Use the mock renderer to exercise the complete API, queue, browser UI, transparent export, and metrics locally without downloading model weights:

```sh
cd emoji-studio
export EMOJI_STUDIO_API_KEY='replace-with-a-long-random-key'
export EMOJI_STUDIO_RENDERER=mock
uv run emoji-studio-api
```

Open `http://localhost:8000`. API documentation is at `http://localhost:8000/docs`. Jobs and artifacts persist under `var/jobs/`; an interrupted `running` job is safely requeued on restart. The worker processes one image at a time and unloads a warm model after five idle minutes by default.

For private-alpha accounts, create tokens one at a time. The command prints each plaintext token once; the users file stores only its SHA-256 digest and is excluded from source control:

```sh
uv run python scripts/create_alpha_user.py alpha-admin --admin
uv run python scripts/create_alpha_user.py tester-01
export EMOJI_STUDIO_USERS_FILE="$PWD/configs/alpha-users.json"
export EMOJI_STUDIO_RETENTION_DAYS=7
export EMOJI_STUDIO_TRIAL_IMAGE_CAP=100
export EMOJI_STUDIO_RENDERER=mock
uv run emoji-studio-api
```

Prompts and outputs are retained for seven days by default, and users can delete completed jobs immediately. Minimal quota events retain only the owner ID, job ID, timestamp, and image count so deletion cannot reset a daily or trial cap.

On a one-GPU Linux host, install the GPU dependencies and omit the mock setting:

```sh
uv sync --extra gpu --frozen
export EMOJI_STUDIO_API_KEY='replace-with-a-long-random-key'
export EMOJI_STUDIO_HOURLY_COST_DOLLARS='0.50'
uv run emoji-studio-api
```

The real renderer requires exactly one visible CUDA GPU, verifies the adapter checksum in `configs/serving.json`, pins the base-model revision, and never publishes weights. `EMOJI_STUDIO_HOURLY_COST_DOLLARS` feeds the per-image cost estimate. GPU-memory, generation-time, queue, failure, and cost metrics are available from authenticated `GET /metrics`. Model unloading releases VRAM; stopping the cloud instance when idle still belongs to the deployment layer and is not claimed by this application.

The optional Vast deployment moves only rendering to a managed one-worker endpoint; the authenticated web/API control plane remains a separate lightweight process. After the Vast account has at least $5 credit, run the bounded smoke test:

```sh
uv sync --extra serverless --frozen
uv run --extra serverless python scripts/smoke_vast_serverless.py
```

The definition accepts only one 40 GB-or-larger GPU at no more than $0.70/hour, permits zero workers after ten idle minutes, and tears down the unattended deployment after thirty minutes. To have the API use it, set `EMOJI_STUDIO_RENDERER=vast-serverless` and install the `serverless` extra. Do not expose the control plane publicly until HTTPS and durable storage are configured.

After an alpha session, create the machine-readable and Markdown result summaries:

```sh
uv run python scripts/summarize_alpha.py
```

Python client example:

```python
from emoji_studio.client import EmojiStudioClient

client = EmojiStudioClient("http://localhost:8000", "replace-with-a-long-random-key")
job = client.generate("a cheerful red panda waving", variations=3, seed=42)
result = client.wait(job["id"])
png = client.download(result["results"][0]["png_url"])
```

## Run locally

```sh
cd emoji-studio
uv sync --frozen
uv run emoji-studio assets
uv run emoji-studio validate
uv run emoji-studio report
uv run python -m unittest discover -s tests -v
```

Open `index.html` directly. No server or API key is required. Review decisions stay in the browser; export them to JSON for a durable copy. The report is a snapshot: rebuild it after importing assets or running inference. Imported PNGs and generated images remain separate.

Initial audit: 3,145 source PNGs across 1,595 concepts; 63 of the 64 preferred references were found. All 63 are native 256 x 256. `Watering can` is absent from this source revision. These are reference assets, not a training-ready dataset.

Browser verification (requires Google Chrome installed):

```sh
uv sync --group browser --frozen
uv run --group browser python scripts/check_workbench.py
```

This fixture expects the default 63 references and checks generated images against the report's run manifests. It writes desktop/mobile screenshots and a test review export to `artifacts/`.

## First GPU experiment

Use a Linux CUDA machine. Start with one GPU, a two-image smoke test, and a provider-side spending limit. This Mac's 8 GB RAM is insufficient for these unquantized baselines. Confirm GPU memory and available host RAM before renting; CPU offload trades GPU memory for RAM and latency. Do not provision a cluster yet.

Transfer the project including `uv.lock`, configs, benchmarks, and the desired run manifests. Install a suitable NVIDIA driver and `uv`, then:

```sh
uv sync --extra gpu --frozen
uv run emoji-studio plan --model klein --output runs/klein-new/plan.json --limit 2 --seeds 0
uv run emoji-studio generate --plan runs/klein-new/plan.json --max-seconds 900 --cpu-offload
uv run emoji-studio report
```

Repeat with `--model sdxl` and a different output directory. Model download requires network access; no inference API is used. Accept each model's license before downloading. Klein base uses Apache-2.0; SDXL uses CreativeML Open RAIL++-M. Revisions, precision, sampling steps, guidance, and seeds are pinned in each plan. Repeating `generate` verifies checksums and skips completed jobs. It stops on the first failed job and resumes remaining jobs on the next invocation.

`--max-seconds` is a cooperative sampling deadline, **not a billing cap**: downloads, model loading, or a stuck CUDA call can exceed it. The approved smoke lifecycle in `scripts/vast_smoke.py` adds an independent local watchdog, remote process timeout, periodic artifact backups, and ownership-checked instance destruction. Its guard depends on this Mac remaining connected and the provider API responding; credit accounting can lag. Do not reuse its budget file as permission for a new experiment. Record provider charges separately from measured inference time. CUDA inference was validated remotely, not on this local Mac.

Once both smoke tests pass, create matched raw-prompt and fixed-style-brief runs:

```sh
uv run emoji-studio plan --model klein --output runs/klein-baseline/plan.json --conditions raw brief
uv run emoji-studio plan --model sdxl --output runs/sdxl-baseline/plan.json --conditions raw brief
```

Each is 40 prompts x 4 seeds x 2 conditions = 320 samples. These commands only create plans. Estimate cost from smoke-test timings before execution; reduce sample count if necessary. Equal seed numbers do not equate model noise or compute. Compare both usability and seconds/cost per usable sample. The raw condition isolates the contribution of the fixed style brief.

## Post-training sequence

Inspect the existing curated data without loading any model:

```sh
uv run emoji-studio training-preflight
```

Review records are in `data/curation.json`; original imported metadata stays unchanged. `curation-template` creates pending records only and refuses to overwrite existing review decisions. The workbench's reference detail dialog shows pilot assignments and AI-reviewed captions. Passing data checks is not training authorization.

The prepared RGB dataset is `data/training/pilot-v1`, with separate `train/` and `validation/` metadata files, checksums and the source license. Re-run its real ImageFolder loader and pinned trainer argument checks locally:

```sh
uv run --frozen --group training-data python scripts/prepare_lora.py
```

This does not load model weights or launch training. Results are recorded in `reports/trainer-preparation.json`. `export-training --output <new-directory>` creates a new export only after data preflight passes; it refuses to replace an existing export.

The completed smoke authorization was deliberately separate from the earlier inference budget: one GPU at a time, at most $0.70/hour, $3 total and 90 elapsed minutes. Observed credit change across setup, the successful run and recovery attempts was $0.3415524277, subject to billing lag. The smoke launcher also has hard code ceilings of $5, $0.70/hour and two hours, and refuses reused, expired, mismatched or out-of-tree authorization files.

The completed quality pilot is documented in `reports/quality-pilot.md` and `reports/quality-pilot.json`. It retained compact adapters at steps 25/50/75/100 and rendered 12 matched base/adapted pairs: the four validation concepts plus unseen-bicycle and excluded-hand controls, each at seeds 0 and 1 with identical 50-step settings. Training used 15,982 MiB sampled peak VRAM and took 108.61 seconds for 100 optimizer steps. Latest observed replacement spend is $0.3473632394; combined with the failed pre-training attempt, the latest observed quality-pilot spend is $0.4086538781, subject to billing lag. All instances are destroyed.

Before a wider quality comparison, use the separate diagnostic control set at 1024 pixels:

```sh
uv run emoji-studio plan --model sdxl --output runs/sdxl-sanity-1024/plan.json --benchmark benchmarks/sanity.json --conditions raw brief --seeds 0 --resolution 1024
uv run emoji-studio plan --model klein --output runs/klein-sanity-1024/plan.json --benchmark benchmarks/sanity.json --conditions raw brief --seeds 0 --resolution 1024
```

Each plan contains eight jobs: apple, raised hand, high-five and pinky promise in raw and brief conditions. This tests basic rendering and prompt effects; one seed per condition cannot establish a model winner. Plans are immutable and creating them does not rent a GPU. The controlled Vast lifecycle selects these plans with `--experiment sanity`; its spending authorization is separate from these reproduction commands.

1. **Baseline:** score prompt semantics, hand anatomy, silhouette at 32 px, unwanted text, and style consistency. Keep failures. Use a separate blinded evaluation before reporting a model winner; the workbench is not blinded.
2. **Data pilot:** audit licensing and native resolution; curate one consistent style with accurate captions. Split by concept family before adding skin-tone variants or augmentations. Existing imports have draft captions and no training split, deliberately.
3. **Style LoRA:** choose the baseline from measured results, then build a model-compatible training recipe. Start with a small single-GPU pilot, comparing identical development prompts before and after training. Upscaling a low-resolution source does not add detail.
4. **Novel composition:** curate licensed/commissioned combinations such as a readable high-five or pinky promise. A style LoRA alone will not reliably teach new hand anatomy or interactions.
5. **Product:** add transparent-background QA, image editing, pack consistency, and platform-specific export. Collect explicit consent before retaining user prompts or images for training.
6. **Scale:** only after a measured bottleneck, add batching, queued GPU workers, then a controlled multi-GPU training experiment. Keep a sealed, concept-disjoint final test set outside this development benchmark.

## Layout and provenance

- `configs/`: source/model revisions and selected source concepts.
- `benchmarks/development.json`: development prompts and concrete criteria, not a held-out test set.
- `data/inventory.json`: all discoverable Fluent 3D PNGs, including tone variants.
- `data/references.json`: selected originals with SHA-256, source Git blob SHA, license, native size, and draft caption provenance.
- `data/asset-audit.json`: counts, dimensions, missing preferred concepts, and the reference-manifest hash.
- `data/sources/fluent/<revision>/LICENSE`: upstream MIT copyright and permission notice. Retain this notice with redistributed source artwork.
- `runs/<name>/`: immutable plan, per-image receipts, images, session environment, and resumable status.

The default pilot prioritizes default-tone references; it is not a representative skin-tone evaluation. Inventory includes variants for subsequent balanced curation. Source images retain their original alpha. Generated baselines have plain backgrounds and are explicitly marked `alpha_processed: false`.

Sources: [Fluent Emoji](https://github.com/microsoft/fluentui-emoji), [FLUX.2 Klein base 4B](https://huggingface.co/black-forest-labs/FLUX.2-klein-base-4B), [SDXL base](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0), [Diffusers](https://huggingface.co/docs/diffusers/index).
