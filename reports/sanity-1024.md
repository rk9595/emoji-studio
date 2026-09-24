# 1024-pixel diagnostic controls: 2026-09-16

**Final status:** all 16 planned images are complete and locally verified after a resume-only allocation. The workbench contains 24 images including earlier smoke artifacts. Total observed spend across all attempts is about $1.49, with zero Vast instances remaining. Initial partial-run details below are historical; the completion section supersedes them.

## Purpose and scope

Test whether the earlier 512-pixel failures reflect basic rendering problems, the emoji brief, or difficult hand interactions. Four prompts (apple, raised hand, high-five, pinky promise), raw and brief conditions, one seed per model: 16 planned images. This is an unblinded development diagnostic, not a held-out benchmark or equal-compute comparison.

Plans: `runs/sdxl-sanity-1024/plan.json` and `runs/klein-sanity-1024/plan.json`. Source: `benchmarks/sanity.json`, separate from the unchanged 40-prompt development benchmark. Both models use 1024 x 1024, seed 0, batch 1, no CPU offload. Pinned weights and package versions are unchanged from the corrected smoke test. SDXL uses 40 steps/guidance 5/FP16; Klein uses 50 steps/guidance 4/BF16.

The [official Diffusers SDXL documentation](https://huggingface.co/docs/diffusers/api/pipelines/stable_diffusion/stable_diffusion_xl) recommends 1024 pixels for best results. The previous 512-pixel test must not be treated as a representative quality benchmark. Hardware also changed between runs, so timings are not an isolated resolution comparison.

## SDXL findings

All eight SDXL images completed and were checksum-verified locally. Both CLIP tokenizers received complete prompts: raw/brief counts are 18/42 for apple, 22/46 for raised hand, 23/47 for high-five, and 10/34 for pinky promise, below the 77-token limit.

| Prompt | Raw condition | Short emoji brief |
| --- | --- | --- |
| Apple | Recognizable photographic apple; detached branch and more than one leaf violate the exact request. | Recognizable yellow stylized apple; extra detached foliage remains. |
| Raised hand | Recognizable open palm with five digits; photographic rather than emoji styling, as expected without the brief. | Yellow stylized open palm, but six digits rather than five. |
| High-five | Multiple hands, oversized burst/background, no clear two-palm contact. | Two recognizable stylized hands, but separated palms and an oversized burst. |
| Pinky promise | Two photographic hands with distorted/ambiguous finger interaction, not a clean hooked-pinky gesture. | Two yellow stylized hands with raised, separated fingers, not hooked pinkies. |

These controls contradict the hypothesis of a completely broken SDXL runtime: the current stack generates coherent images. They do not prove that resolution was the sole cause of all earlier failures. The paired hand prompts still show composition errors at 1024 pixels. The brief changes style but can worsen anatomy, so it is not a substitute for testing prompt fidelity.

Generation range: 42.1461-51.8872 seconds per image; peak allocated VRAM about 10.49 GiB. Load/download time: 101.835 seconds; total model session: 474.0687 seconds. This is one sampled RTX 5880 Ada host, not a p50/p95 serving benchmark.

## Klein findings: initial allocation

Three of eight Klein images completed before the outer process timeout:

| Prompt / condition | Visual inspection | Generation |
| --- | --- | ---: |
| Apple / raw | One recognizable apple, one attached leaf and stem, isolated white background. Matches the control criteria. | 235.1884 s |
| Apple / brief | Clean yellow 3D emoji-like apple with one leaf and stem. Matches the control criteria and requested brief. | 229.2598 s |
| Raised hand / raw | One open palm with five digits on white. Matches the control criteria; photographic without the brief. | 212.6757 s |

Peak allocated VRAM: about 17.33 GiB. Load/download time: 162.3185 seconds. The raised-hand brief job was interrupted; both high-five and both pinky-promise jobs were not reached. There are **five unfinished Klein jobs**, not five failed-quality images. No complete Klein session summary was written because the outer timeout terminated the process. Completed image receipts and checksums are intact.

The original 10-20 minute estimate was too optimistic for this host and resolution. Klein actually required about 3.5-3.9 minutes per image. We did not lower sampling steps mid-experiment or silently extend the time limit. A request to increase the runtime allowance was sent, but no approval had been received when this run stopped. The original limits therefore remained in force.

## Initial cost and shutdown

Vast instance 51183629 (`emoji-smoke-4afeab0a3f`), RTX 5880 Ada 48 GB, $0.685185/hour including 100 GB disk. Download/upload rates: $0.00260417/$0.00390625 per GB. Allocated lifecycle: 1571.76 seconds, about 26.20 minutes. Remote process exited 124 at its timeout; the reserved cleanup window was used to download the final archive and destroy the instance.

All **11 completed images** were downloaded and checksum-verified. With the earlier eight smoke artifacts, the workbench now contains 19 real images. The final archive is `artifacts/vast/emoji-smoke-4afeab0a3f/results.tar.gz`; no image is represented as completed merely because its job was planned.

Independent Vast check after teardown: `success: true, remaining_instances: 0`. Initial experiment credit was $8.5761476886; latest observed credit is $7.2509770640. **Cumulative observed spend is $1.3251706246**, including earlier failures, retries and both smoke runs. Credit accounting may lag; this is not a finalized invoice. Cumulative allocated time is 6071.27 seconds, about 101.19 minutes, within the original two-hour limit. About 18.81 allocated minutes remain under that original runtime ceiling, but the current wall-clock window is closed.

Local verification: 25 unit tests and Ruff pass. Tests now also cover separate hashed control manifests, rejecting noncompliant marketplace offers, and uploading only checksum-verified completed outputs for cross-instance resume. Headless Chrome checks cover desktop/mobile layouts, image loading and inspection, filtering, review persistence and export. No training was run.

## Resume completed

After the user's next-step request, the five missing jobs resumed within the original two-hour cumulative limit, without applying the proposed three-hour extension. Completed images and receipts were uploaded; SDXL returned `model_loaded: false`, and Klein skipped its first three jobs. No finished sample was regenerated.

Instance 51189905 (`emoji-smoke-9f187f7031`) used RTX PRO 5000 Blackwell 48 GB at $0.694444/hour including disk. Selection now prioritizes the provider's performance score rather than download speed alone. The advertised score is not a guarantee; the workload measurements below are the evidence.

| Remaining Klein sample | Inspection | Generation |
| --- | --- | ---: |
| Raised hand / brief | Clean yellow rendering, but only four digits visible rather than five. | 22.8484 s |
| High-five / raw | Photographic hands pressed together, reads as praying rather than a high-five. | 22.2703 s |
| High-five / brief | Yellow praying-hands composition; missing the tiny contact burst. | 22.5966 s |
| Pinky promise / raw | Two fists with thumb tips touching; not hooked little fingers. | 22.7711 s |
| Pinky promise / brief | Two yellow thumbs-up hands; not a pinky promise. | 22.8899 s |

Peak allocated VRAM remained about 17.33 GiB. Load/download: 176.0931 seconds. Resumed model session: 290.1725 seconds; entire rental lifecycle: 599.92 seconds. These five timings are from different hardware than the earlier three Klein controls and all SDXL samples. Do not average them into one serving-latency figure or claim an equal-hardware speed comparison.

The final archive contains all 16 checksum-verified controls: `artifacts/vast/emoji-smoke-9f187f7031/results.tar.gz`. Instance destruction succeeded; an independent API check confirmed zero remaining instances. Latest observed credit: $7.0892051088; initial credit: $8.5761476886. **Cumulative observed spend: $1.4869425798**, possibly subject to delayed billing. Cumulative allocated time: 6671.20 seconds, about 111.19 minutes, below the original 120-minute ceiling.

Final verification: 33 unit tests and Ruff pass. Chrome checks pass at 1440, 390 and 320 pixels, including all 24 saved images and pilot-caption details. No training has run.

## Decision and next step

Both models render coherent images, but neither solves the requested two-hand interactions in these samples. Klein's object controls and styling make it a reasonable provisional choice for a style-learning pilot, not a demonstrated general model winner. One seed and four prompts are too little evidence for that claim. Training only existing style examples is not expected to fix high-five or pinky-promise semantics.

The first object-only curation is now prepared: 16 train and four validation concepts, with AI visual review explicitly attributed, source checksums, actual artwork captions and low-resolution acknowledgments. See `data/curation.json`, `reports/training-preflight.json` and `reports/lora-pilot.md`. The next paid experiment should be a separately authorized, measured 100-step technical LoRA pilot, not a full training run or cluster.
