# Current state — 2026-10-25

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

User delegated builder choice October 25. Selected free standard public GitHub
CPU runner; prior host-choice blocker resolved. Read-only capacity run 40166118846
found native x86-64, four CPUs and 85.4 GiB free without deleting tools.
`docs/amd-cpu-builder.md`, `configs/amd-builder-proposal.json` lock 38 public app
inputs and two recipe files. No private artifacts enter context; no broad repo COPY.
One CPU validation run **40166592399** launched at source
`acef6db19b00ddcb07dbff290bfde2ff825c80ed`; live receipt check says running.
https://github.com/rk9595/emoji-studio/actions/runs/40166592399
35-minute build/45-minute job caps; fresh 60-GiB disk guard; no paid fallback,
GPU allocation, model download, registry push or artifact/cache upload.
Receipt: `reports/amd-cpu-build-launch.json`. **52 tests/64 subtests passed**;
six runtime modules (103 tests) also passed from isolated staged context on the
Mac dependencies, proving context completeness only. Ruff/YAML checks passed.
CPU/GPU compatibility and derived OCI manifest digest remain unverified.

Offline export/cleanup prototypes complete: `docs/smoke-private-export.md`,
`docs/smoke-cleanup-contract.md`; preparation receipts under `reports/`.
Sanitized export manifest/images, conditional private writes, independent download
checks and ticket recovery tested; exact resource absence required for cleanup.
Prior 103 tests/125 subtests passed. No live storage/provider adapter or scheduler.

Cleanup prototype complete: `docs/smoke-cleanup-contract.md`,
`reports/smoke-cleanup-preparation.json`. Exact immutable ownership/resource
binding; cleanup minute 25, escalation minute 30, durable pending before calls;
only exact GET absence completes cleanup. Process crash/reopen and failures tested.
No cloud scheduler/adapter/deployment. Independent reaper and controller gates open.

Runtime proposal remains metadata-only: `docs/amd-runtime-proposal.md`,
`reports/amd-runtime-preparation.json`. ROCm7.2/Python3.12/Torch2.10 base digest
bcb2efa1…32763e4 verified; 12.76 GB compressed layers not pulled. Application
overlay has 45 pinned/hash-listed packages. Base GPU packages/dependency traversal
excluded, so combined compatibility is unverified. No image build or installation.
Offline checker: `python3 scripts/check_amd_runtime_proposal.py`.
Status prepared_only; runtime_validated false; derived image digest null.

Mock-only executor/guard complete: `docs/mock-smoke-executor.md`,
`docs/render-budget.md`, `reports/mock-smoke-executor.json`. Stable job/image IDs;
two-call consumption spans render, export validation and atomic queue publication.
Uncertain calls/publications halt new work. No real renderer selection or provider
interface; default API/worker unchanged. Prior 166 tests/38 subtests passed.
Fresh prior HTTP smoke has 14 checks/three processes/two mock images.
No reset/refund/reclaim; trusted local disk only, no rollback/bypass protection.

Coverage prototype remains complete: `docs/coverage-sampler-prototype.md`,
`reports/collection-coverage-prototype.json`. 2,000 draws cannot cover 2,493 assets;
proposed 2,496 draws/624 steps give full coverage, not training approval.
Gesture gate blocks missing training buckets and visual-review metadata.
No dataset/caption/split edits; protected sampling/serving hashes unchanged.
Prior prototype suite: 32 tests/38 subtests passed.

Prior durable API remains opt-in, schema **4**, optional owner-scoped
Idempotency-Key; same request reuses job/seeds/usage across restart/full quota.
Key conflicts/deleted jobs return 409; no key creates a new job. X-Request-ID is
correlation only; UI does not send keys yet. Old DBs require explicit migration.
Docs: `docs/durable-api.md`, `docs/worker-lease-contract.md`. Prior 128 tests and
26 subtests passed (two existing warnings); real HTTP receipt has 14 checks,
three disposable processes and two mock images (`reports/local-http-smoke.json`).
Default API/serving unchanged. No backup/restore, monetary reservations,
provider dispatcher or authenticated remote worker. Metrics/rate windows are
process-local; lease fencing/idempotency are not exactly-once physical rendering.

AMD draft explicitly expanded/relocked for mock executor integration October 24:
`configs/amd-api-smoke-plan.json`, `docs/amd-api-smoke-plan.md`;
`python3 scripts/check_amd_api_smoke_plan.py` verifies 23 files and private adapter.
Receipt: `reports/amd-api-smoke-preparation.json`. Still **prepared_only**,
execution_authorized false, dollar allowance null. Proposed one GPU, two physical
render calls, 30 minutes including five for cleanup, zero automatic POST retries.
ROCm OCI/dependency lock, dedicated budgeted executor, independent reaper/deletion
receipts and verified private export remain prerequisites. Linux GPU dependencies
currently select CUDA; do not install that lock unchanged on AMD.

## Waiting on free CPU build

Queue is waiting_cloud with exact public Actions run/head/workflow. Supervisor
supports this receipt identity and skips model turns while running; it must not
read the completed comparison's release as this build's completion evidence.
Do not model-poll, auto-rerun, weaken checks or switch to paid capacity.
On completion/failure, retain base/post-overlay package inventories and first
failure. Review expected base exclusions, dependency/ABI/import checks and in-image
mock tests; make explicit reviewed recipe/lock changes if needed.
Success gives CPU compatibility only. Local image ID is a config digest, not a
published OCI manifest; plan immutable image retention/publication separately.

After CPU validation, integrate private storage/ticket/receipt persistence,
pre-allocation reservation/reconciliation, independent scheduling and deadlines.
No comparison reset or paid execution. Live HIP/GPU validation still needs a
separately bounded allowance; persistent hosting needs budget/access.
Any active locked changes need tests and explicit reviewed relock.

## Retained evidence

Consumed AMD comparison: 144 verified images, all four GPUs deleted October 13,
about $0.99 estimated total; no fifth attempt or campaign reset.
Run: https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release: `rk9595/emoji-studio-ops`, `amd-comparison-v1`.
Local results: `runs/amd-comparison-v1/`; `reports/amd-comparison-v1.md` records
blinded AI review, not new human review; all 84 gesture outputs failed requirements.
Serving remains reviewed pilot step 25, checksum in `configs/serving.json`.
`reports/collection-coverage-audit.md`: crossed fingers validation-only, folded
hands unsampled, high-five/pinky absent, tiny flags oversampled.
Collection-v3 proposal is a draft; no annotation/training approval changed.

## Automation

LaunchAgent `com.emoji-studio.codex-supervisor` checks every 15 minutes, respects
usage resets, skips active turns and may compact after six fresh handoffs.
Runtime ignored under `var/automation/`; Mac awake/app-server required.
Latest user continuation October 25. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
