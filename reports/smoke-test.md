# GPU smoke test: 2026-09-15

## Outcome

Completed four corrected, checksum-verified base-model samples: high-five and pinky promise, one seed each, on Klein base 4B and SDXL. This validates remote execution and artifact recovery, not product quality or a model winner. No post-training has run.

Open `../index.html`, then Model runs. Corrected `*-smoke-v2` runs appear first. Four earlier outputs remain separately labeled diagnostic and excluded from comparison scoring.

## Corrected run

- Vast instance 51130452, label `emoji-smoke-dc482ce46c`.
- One RTX 6000 Ada, 48 GB VRAM; $0.654444/hour including 100 GB disk. Transfer rate $0.00403646/GB each direction.
- Allocated lifecycle: 271.57 seconds, approximately 4.53 minutes, including setup and teardown.
- Both models: 512 x 512, seed 0, batch 1, no offload. Klein: 50 steps, BF16, guidance 4. SDXL: 40 steps, FP16, guidance 5. These are different compute budgets, not an equal-compute comparison.
- Environment: Torch 2.10.0+cu128, Diffusers 0.40.0, Transformers 5.17.0, Accelerate 1.15.0.
- Model revisions, exact prompts, sampler configs, environment, timings, checksums and receipts are retained under `runs/*-smoke-v2/`.

| Model / prompt | Generation | Peak allocated VRAM | Visual inspection |
| --- | ---: | ---: | --- |
| Klein / high-five | 10.9464 s | 15.55 GiB | Clean yellow hands, but reads as praying; missing the requested contact burst. |
| Klein / pinky promise | 10.4258 s | 15.55 GiB | Two emoji-like hands; fingers touch rather than hooked little fingers. |
| SDXL / high-five | 3.0287 s | 7.68 GiB | Black/yellow repeated shapes; no readable high-five. |
| SDXL / pinky promise | 2.3325 s | 7.67 GiB | Black/yellow glyph-like shapes; no readable pinky promise. |

None passes the requested gesture criteria in this inspection. These are unblinded judgments on only four images, not a population usability estimate. Images remain RGB with unprocessed backgrounds, not transparent sticker exports. Model-load durations were 19.0412 seconds for Klein and 21.8469 seconds for SDXL; generation figures exclude loading, provisioning and transport.

## Benchmark correction and limitations

The original style-first prompt exceeded SDXL's 77-token CLIP limit, cutting off the actual gesture. That v1 comparison is invalid. All four original artifacts and logs were preserved; they must not be used to judge SDXL's ability.

The v2 brief puts the task first and shortens the shared style description. Both pinned SDXL tokenizers were checked locally and remotely: high-five is 47 tokens and pinky promise is 34 tokens in each tokenizer. The runner now refuses over-limit prompts before loading image-model weights. Corrected logs contain no truncation warning, and receipts include token counts.

Removing truncation did not fix SDXL's outputs. The cause is not established. Resolution, prompt construction and runtime compatibility need isolated controls before attributing the result to model capability. SDXL generally performs best at 1024 x 1024; 512 is supported but lower quality according to the [official Diffusers guidance](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/stable_diffusion_xl). This small 512-pixel smoke test is not an adequate model-selection benchmark.

## Costs and cleanup

Original experiment credit: $8.5761476886. Latest checked credit after cleanup: $7.6211158692. Observed cumulative spend: **$0.9550318194**, including prior setup failures and retries. Provider accounting can lag; this is a credit-delta observation, not a finalized invoice.

All seven allocated attempts total 4499.52 seconds, approximately 74.99 minutes. Each used only one GPU at a time. The approved $5 total, $0.70/hour and two-hour cumulative allocation bounds were not exceeded. The user explicitly approved a 30-minute wall-clock extension after the earlier deadline prevented allocation; the dollar budget was not reset.

The final archive was downloaded before destruction. Vast independently returned `success: true, total_instances: 0` after cleanup. No GPU or instance disk remains allocated. Logs, plans, receipts, periodic backups, cleanup responses and per-attempt credit observations are under `artifacts/vast/`.

## Verification

22 local unit tests and Ruff checks pass. Remote core tests passed. Headless Chrome checks pass at 1440, 390 and 320 pixel viewport widths, including all generated image loads, output detail dialogs, reference filters, tabs, review persistence and export. Screenshots are in `artifacts/`.

## Next experiment, not launched

1. Run a tiny 1024-pixel sanity set: simple isolated object and single-hand prompts plus the two target gestures. Compare raw and short-brief conditions. If SDXL still fails simple controls, isolate runtime/version and pipeline issues before expanding the dataset.
2. After controls pass, run a balanced subset across gestures, reactions, objects and stickers with multiple seeds. Review at 32 and 64 pixels; choose a base from measured quality and cost per usable result.
3. Curate accurate licensed captions and concept-disjoint splits, then prepare the first small style LoRA. The 63 imported reference assets are native 256 pixels and not training-ready. Novel hand interactions require dedicated composition examples; style adaptation alone is not a demonstrated solution.

No additional rental, full baseline or training job is authorized by this report.
