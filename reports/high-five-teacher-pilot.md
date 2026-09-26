# Qwen high-five trial: one candidate recovered, not training-ready

Updated September 26, 2026. The four-image trial ran on September 25 but was
interrupted by an SSH read failure. One candidate was downloaded and verified.
No interaction training ran and no positive example has been admitted to training.

![Unedited Qwen candidate, seed 101](../docs/images/high-five-teacher/qwen-hi5-001.png)

## What actually ran

- Model: `Qwen/Qwen-Image-2512`, revision
  `25468b98e3276ca6700de15c6628e51b7de54a26`.
- Plan: `b7b32a23c3fe42b0af036e6bc3616ec6eb69473ae9ad8cfcd73fb620bfb5728c`.
- Candidate: `qwen-hi5-001`, seed 101, light/dark hands in an oblique wide-V composition.
  Exact prompt and settings are in `configs/high-five-teacher-pilot.json`.
- Resolution 1328 × 1328; 50 steps; true CFG 4.0; BF16; CPU offload and VAE tiling.
- Device reported by PyTorch: NVIDIA GeForce RTX 4090. The marketplace advertised
  49,140 MB GPU RAM and 128,897 MB host RAM; the sampler's >=45 GiB CUDA check passed.
  This is an observation about this host, not a claim about standard RTX 4090 specs.
- One-image inference time: 151.65 seconds, excluding setup/model loading.
- Peak PyTorch-allocated GPU memory: 38.68 GiB, not total device usage.
- Original PNG SHA-256:
  `dc37291fe3aa4ecaf4a731c0fd271b9a9002d9a0b3c62d3d95113b25db5b69d7`.

The pinned model card declares Apache-2.0; see the
[preparation report](high-five-teacher-preparation.md) for source links and provenance.
This is a synthetic diagnostic output, not a commissioned or human-reviewed example.

## Preliminary visual review

Unblinded AI inspection at full resolution and in a browser at 32/64 pixels:

- Two differently toned hands visibly meet along their palm surfaces.
- The foreground hand has four visible fingers and a thumb. The rear fingers are
  partly occluded; complete anatomy cannot be verified. Occlusion is not itself
  proof of malformed anatomy.
- Forearms diverge, but the wrists are close and the fingers form a tight, upright
  silhouette. A high-five reading is plausible; folded-hands ambiguity remains,
  especially at 32 pixels. This is not a clear semantic pass under our rubric.
- The output is photographic, not the requested rounded 3D emoji style. Forearms
  extend to the bottom edges, contrary to the requested short arms/generous margins.

Decision: **pending, not accepted for training**. Human review is still needed.
The local `runs/high-five-teacher-pilot-v1/review.html` shows the unedited PNG at
large and small sizes; `human-review-template.json` binds the review to its hash.
Do not derive a teacher pass rate from this one recovered image or compare it as a
matched benchmark result: its prompt differs from the frozen FLUX evaluation.

## Interruption and cleanup

The user approved $1.50 total, one GPU, 60 minutes, and later raised only the hourly
ceiling to $0.80. The rented offer cost $0.7583703704/hour including allocated disk;
transfer charges were additional and counted against the total-credit guard.

After snapshots reached 1/4, a read-only `teacher.exit` SSH poll returned code 255.
The old launcher immediately entered cleanup instead of retrying that read.
The underlying network/provider cause is unknown; the evidence does not show a
model crash. The local report's `status: running` is its last saved remote state,
not a currently running job. The report is preserved unchanged for provenance.
The other three outputs were not recovered; do not claim they were generated.

Destruction was confirmed after 673.33 seconds (11.22 minutes). Initial observed
credit change was $0.2454230576; a September 26 reconciliation showed $0.2463501935
and zero instances. Credit was $6.1884668369 before the run and $5.9421166434 at the
later check. Provider billing may lag. This run remained below its approved limits.

Local receipts, archive and cleanup evidence are under
`artifacts/vast-teacher-pilot/emoji-teacher-12cfcfbd23/`; private keys/account details
are excluded from Git. The original authorization is consumed and its time window
has expired. Do not silently reset its limits or launch another rental with it.

## Recovery changes and next step

The launcher now retries only read-only SSH transport failures/timeouts, at most
twice, and checks the cleanup deadline, watchdog freshness/shutdown and observed
spend before every attempt. Remote program failures and integrity failures are
not retried. Allocation and process-launch requests are never blindly retried.
This is tested failure handling, not proof that the next network connection will work.

Recovery archives include only checksum-verified completed images and their report,
so the sampler can skip the first candidate and generate the other three. Uncommitted
files, credentials and unrelated experiment data remain excluded. The original run
also included a pinned `uv==0.10.9` bootstrap fix for fresh GPU containers.

Local verification: 107 tests and Ruff passed. A proposed recovery asks for at most
$1.25 additional spend, <=$0.80/hour, one GPU and a fresh 45-minute window. Combined
observed spend would stay within $1.50, and combined allocated time within 60 minutes
if both individual limits hold. Recovery approval is pending. Even four successful
candidates would not satisfy the separate 24-train/8-validation data gate.
