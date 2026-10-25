# Current state — 2026-10-25

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Offline private export completed: `docs/smoke-private-export.md`,
`src/emoji_studio/smoke_export.py`, `reports/smoke-export-preparation.json`.
One/two surviving PNG/WebP pairs; pixel-only re-encoding strips metadata; manifest
records source/sanitized hashes and binds plan/serving/allocation. Private new
smoke namespace only. Conditional writes, manifest last, no automatic retries;
only fresh downloads against an externally retained ticket verify export.
Partial/corrupt/missing uploads and lost acknowledgments tested; verification
does not imply cleanup or smoke acceptance. No live storage adapter/upload.
**103 tests/125 subtests passed**, including 21 export tests; two existing warnings.
Ruff and both plan/runtime checks passed. Active 23-file lock unchanged.

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

## Waiting for user — builder/access choice

Queued offline cleanup/export components are complete. Next runtime validation
needs a suitable Linux/amd64 builder with room for 12.76 GB compressed base plus
extracted/build layers. Read-only local check: Docker server linux/arm64; Mac
filesystem ~20 GiB available. No base layers pulled or packages installed.
Request an existing builder/access reference, or a choice to prepare a new builder
proposal. Do not provision paid infrastructure or clean unrelated files to fit it.

After builder choice: prepare/run reviewed runtime build, collect base/post-overlay
inventories, dependency/ABI/import checks, derived-image digest and in-image tests.
Then integrate private storage/ticket/receipt persistence, pre-allocation
reservation/reconciliation, independent cloud scheduling and worker deadlines.
No deployment, comparison reset or spending authorized. Live HIP/GPU validation
still needs separately bounded authority; persistent hosting needs budget/access.
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
