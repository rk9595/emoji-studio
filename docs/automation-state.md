# Current state — 2026-10-25

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Offline cleanup contract completed: `docs/smoke-cleanup-contract.md`,
`src/emoji_studio/smoke_cleanup.py`, `reports/smoke-cleanup-preparation.json`.
Immutable account/campaign/allocation/resource/plan/creation binding; cleanup at
minute 25, hard deadline minute 30. Durable pending state precedes provider calls;
only exact GET absence completes cleanup. Crash/ack loss, identity mismatches,
deadline failures and clock rollback tested. Separate POSIX lock file serializes
ticks; missing/replaced files fail closed. No network adapter, scheduler, cloud
deployment or allocation. Local trusted disk only; no distributed durability claim.
**82 tests/85 subtests passed**, including 24 cleanup tests; two existing warnings.
Ruff and both plan/runtime checks passed; active 23-file lock unchanged. Live
reaper gate remains open: external registration/scheduling, provider adapter,
pre-allocation reservation/reconciliation and deadline/controller integration needed.

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

## Next ready work

Next: implement/failure-test checksum-verified private export with mocked storage,
sanitized manifests and independent download verification for the NEW smoke.
No deployment, provisioning or modification/reset of the consumed comparison.
Runtime proposal still needs a suitable
Linux/amd64 build environment with disk capacity, base/post-overlay inventories,
dependency/ABI/import checks, derived-image digest and in-image mock tests.
Do not install the overlay into this Mac or silently treat exclusions as validation.
Live HIP/GPU validation requires separately bounded authority; deadline/controller
gates remain open. Any active locked changes need tests and reviewed relock.
Ask for bounded compute/hosting/build choices when they block remaining offline work.

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
