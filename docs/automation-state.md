# Current state — 2026-10-31

## Milestone complete — no active GPU

**Two real emojis were generated through the authenticated HTTP API on one AMD
MI300X, downloaded/verified, and the GPU independently confirmed deleted.**
Queue `complete`; no scheduled continuation or further GPU allocation for this
milestone. Preserve unrelated recovery files; stage only intentional changes.

Private run41173826485 succeeded (smoke and independent watchdog):
https://github.com/rk9595/emoji-studio-ops/actions/runs/41173826485
Sourcecbce1857e1b23f19fa9ee977f14d11cf2fc02b47,
releaseamd-api-smoke-20261030d, GPU614450630 deleted.
Primary evidence: `reports/amd-api-live-result.json`,
`reports/amd-api-gpu-output-receipt.json`.
Local PNG/WebP outputs: `artifacts/amd-api-milestone-20261031/api-results/`.
Private archive SHA25662256f01d4f737eac4e2298df0328a8cdfefc3a9a663291c671d3b4b8b2e716e.

Both 512px RGBA outputs match their hashes and show nonempty transparent content.
Real FLUX2 Klein4B/pilotstep25; ROCm7.2, Torch2.10, one MI300X. Physical ledger
consumed exactly2 successful calls. Authentication rejection and third-image cap
passed. Controller and independent watchdog observed exact-resource deletion.
GPU lifetime300.369sec; estimated successful cost$0.166, **all API attempts$0.7751**
against$2 reserve. These are runtime estimates, not provider invoices.
Render times33.657sec and3.952sec; API job64.228sec. Two samples are not a benchmark.

AI visual review (not human): recognizable red apple and yellow smile. The smile
retains a large gray shadow/background patch; improve cutout/shadow quality before
production. No adapter promotion. No public endpoint or persistent hosting.

Exact-source gate is closed: `completed-41173826485`. All previous API claims remain
consumed: GPUs613866182/614256807/614271639 independently deleted, zero images from
those attempts. Their result reports are retained as first/second/third-attempt
receipts. Never repeat/reset them or the separately consumed comparison.

## Usage safety and automation

User explicitly requires destroying GPUs before Codex usage limits. Detached local
usage guard reads quota every30sec, requests cloud cleanup at85% or two unavailable
signals. Cloud controller/watchdog honor the run-bound stop request. Minute26
self-expiry and minute25 work cutoff are independent of Mac/model availability.
The last guard finished normally; no quota stop was needed. Future runs must retain
these controls. No GPU may wait idle for quota reset. `docs/amd-usage-cleanup.md`.
Supervisor also handles waiting_usage at85%. Mac/app-server must be awake to resume
local work; cloud cleanup does not depend on model reasoning. Queue complete stops
automatic continuations now. 35 focused tests passed before the successful run.

## Next production work (not launched)

- Improve matting/shadows on saved outputs and establish image-quality gates.
- Validate durable API/worker crash/retry behavior with the real renderer; current
  milestone exercised the legacy API with a strict two-render guard.
- Resolve Noto3D PNG-specific license terms before a separate dataset/training
  pilot. Current training data is Microsoft Fluent3D. Noto audit pins99701e07d…;
  README says images Apache2 but linked root LICENSE is OFL1.1. No new training.
- Benchmark capacity/cost and choose recurring budget/access before hosting.

`docs/production-next.md` and `reports/noto-3d-candidate-audit.json` retain details.
Custom GHCR publication remains deferred/gate closed; direct provider image worked.
Old prepared-only smoke plan/23-file lock stays intact. CPU validation passed103
in-image tests; old retention failures remain historical, not the next task.

Consumed comparison:144 images/four GPUs deleted,~$0.99 against separate$3 reserve;
private run38352558272/releaseamd-comparison-v1. Never repeat it. AI review found
all84 gesture outputs failed; do not claim human review or production quality.
