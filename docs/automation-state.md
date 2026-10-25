# Current state — 2026-10-25

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

CPU validation **completed successfully**, run **40166592399**, source
`acef6db19b00ddcb07dbff290bfde2ff825c80ed`:
https://github.com/rk9595/emoji-studio/actions/runs/40166592399
523-second job, 511-second build. **103 in-image tests**, real HTTP smoke and
guarded mock executor passed. Full dependency check and CPU native imports/operators
passed; 42 base / 78 installed distributions retained, all 45 overlay pins match,
five base GPU package versions unchanged. `reports/amd-cpu-validation.json` retains
inventories, source identity, audit receipt and log checksum; local inventory
validator rechecked actual evidence. `docs/amd-cpu-validation.md` explains limits.
Imported Torch 2.10.0+rocm7.2.0.gitb6ee5fde; HIP 7.2.26015. No GPU/model validation.
Local image config digest 2c3ad8f4…bb81ab9 is NOT an OCI manifest; image was ephemeral.
No paid resources, registry push, serving change or comparison repeat.

Next retention proposal: `configs/amd-image-retention-proposal.json`, private
`ghcr.io/rk9595/emoji-studio-amd-runtime`, one new version. GHCR container storage/
bandwidth documented free October 25; recheck before execution. Publication false;
no package created or new build dispatched. Prepare workflow and remote digest/
privacy tests next; do not substitute a local config ID for a published manifest.

Offline export/cleanup prototypes complete: `docs/smoke-private-export.md`,
`docs/smoke-cleanup-contract.md`; preparation receipts under `reports/`.
Sanitized export manifest/images, conditional private writes, independent download
checks and ticket recovery tested; exact resource absence required for cleanup.
Prior 103 tests/125 subtests passed. No live storage/provider adapter or scheduler.

Base ROCm7.2/Python3.12/Torch2.10 digest bcb2efa1…32763e4 and 45-package
overlay are now CPU-tested together. Historical metadata preparation remains in
`docs/amd-runtime-proposal.md`, `reports/amd-runtime-preparation.json`.
Base layers/install occurred only on the disposable cloud CPU runner, not the Mac.
Offline checker: `python3 scripts/check_amd_runtime_proposal.py`.
Active proposal remains prepared_only; runtime_validated false; derived OCI digest
null because GPU validation and immutable image retention have not happened.

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

Implement/failure-test private GHCR retention workflow and manifest/privacy checks
from `configs/amd-image-retention-proposal.json`. Publication remains false while
the concrete workflow is prepared/reviewed. One unique version, no overwrite,
public visibility change, automatic retry, existing-version deletion or paid fallback.
New retained build must repeat CPU checks; independent fresh pull must verify the
published manifest/config/platform and private access before recording readiness.
Resolve any remaining publication authority/access choice only after preparation.

Then integrate private export/ticket/receipt persistence, pre-allocation reservation/
reconciliation, independent scheduling and deadlines. GPU smoke needs separately
bounded allowance; hosting needs budget/access. Active source changes need reviewed
relock. No comparison reset/repeat. Queue ready; prior CPU wait is complete.

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
