# Current state — 2026-11-01

## Active corrective training — waiting on cloud

Run41273277371/source0a960b92de7457a231ed348153b13b898d114db4 is active:
https://github.com/rk9595/emoji-studio-ops/actions/runs/41273277371
Private releaseamd-coverage-20261031b; GPU614682073 last observed booting.
Queue waiting_cloud; source gate closed running-41273277371. Do not dispatch again.
Independent watchdog registered; detached local usage guard PID32970 is watching.
Startup usage was below85% (primary4%, weekly80% at initial check; rechecked before
allocation). Guard requests deletion at85% or two unavailable usage signals.

Started04:29:30UTC November1 (09:59:30IST). Work cutoff05:24:30UTC,
self-expiry05:25:30UTC; max lifetime05:29:30UTC. One GPU, rate ceiling$1.99/hour,
SAME aggregate$2.25 reserve including prior$0.138206 runtime estimate. Controller
freshly verified previous exact GPU404 and prior independent-cleanup receipts.
No training success or current GPU deletion has yet been established.
`reports/amd-coverage-corrective-dispatch.json`, `ops/amd-training-corrective-plan.json`.

When the exact run finishes, download training-state.json, watchdog-result.json,
training-progress.json/results archive from the private release, plus the workflow
artifact if failed. Verify hashes, finite losses, retained adapters and independent
deletion. Record aggregate cost and close the gate as completed/failed. Review
quality before promotion; never reset claims or automatically replace this GPU.
Local supervisor requires awake Mac/app-server, cloud cleanup does not.

## Corrective inputs and prior failure

First run41203305217 stopped before training: provider langchain-core0.3.83 needs
packaging>=23.2,<26; overlay installed26.3. GPU614520349 independently deleted,
estimated$0.1382, zero steps/checkpoints/images. Original campaigna consumed.
`reports/amd-coverage-first-attempt.json`; logs under var/amd-training-live/.

V2 overlay changes only packaging to25.0; all73 other pins unchanged. New
pre-install check validates retained provider requirements; post-install pip check
remains mandatory. Local dependency check, full trainer import and65 tests pass.
Actual AMD backward pass still pending. `reports/amd-training-corrective-preparation.json`.

Frozen inputs3181 files/270449248bytes were reverified against both archive and
local files November1. ArchiveSHA2563936fdac5a815eeeb2dd21332fe4387fc887d7e8efd0f945d3bebe23e1820089;
GitHub private uploaded-asset digest also matches. Local copy:
var/amd-training-live/corrective/inputs.tar.gz. Private source published, plan expiry
refreshed and new dispatch made only after fresh quota headroom. Prior cutoff was
respected: no GPU was left running through the October31 quota reset.

## Unchanged experiment and prior completed work

Two-step/eight-image finite-loss/reload smoke gates624-step Fluent coverage run.
Same pinned base/data/captions/split; keep checkpoint500 and final624. At most49
renders including smoke. All2493 training assets covered in2496 draws; CPU sampler
verified. `docs/coverage-training-v1.md`. Serving pilotstep25 remains unchanged.
Quality and gesture accuracy are not established; AI review must be labeled AI.

Completed API milestone: two images, run41173826485, allfour GPUs deleted,
$0.7751 estimated aggregate within separate$2 reserve. `reports/amd-api-live-result.json`.
Completed comparison:144 images, allfour GPUs deleted, ~$0.99 within separate$3;
run38352558272, `reports/amd-comparison-v1.md`. Neither may be repeated/reset.
Noto PNG licensing/font-route investigation, cutouts, durable-worker recovery and
hosting budget remain separate. GHCR deferred/gate closed. No persistent hosting.
Keep memory short and stage only intentional files; preserve unrelated recovery work.
