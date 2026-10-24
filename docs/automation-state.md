# Current state — 2026-10-24

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Mock-only dedicated executor integration complete:
`src/emoji_studio/mock_smoke_executor.py`, `docs/mock-smoke-executor.md`,
`reports/mock-smoke-executor.json`. Uses dedicated API with worker disabled and
trial cap two. Stable call ID = durable job ID + image position; fingerprint binds
prompt/seed, mock implementation, planned model identity and serving-config hash.
Guard reservation spans rendering, PNG/WebP validation and queue publication.
Crashes/failure/lost acknowledgement halt further calls, including after publication.
Startup reconciles consumed calls against published job identity/status; missing
or unguarded publications block. No renderer injection or provisioning interface.
Default API/DurableWorker unchanged; this is NOT a live AMD executor.

Guard: `src/emoji_studio/render_budget.py`, `docs/render-budget.md`; fixed two
calls, no reset/refund/reclaim. Historical standalone receipt:
`reports/render-budget-preparation.json`. Same trusted local disk assumptions;
disk rollback or bypassing the wrapper remains outside this boundary.

**166 focused tests/38 subtests passed**, including 18 executor tests and expanded
draft checker; two existing warnings. Ruff/diff checks pass. Fresh mock integration:
two jobs published, matching exports, API replay/reopen, third call denied.
Fresh real loopback HTTP smoke: 14 checks, three processes, two mock images;
`reports/local-http-smoke.json`. Mock receipt also reverified after the relock.
All runtime queue/ledger files disposable; no GPU allocations or spending.

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

Next: resolve an immutable AMD runtime/dependency proposal from official registry
metadata and the retained ROCm receipt, without provisioning or installing GPU
packages into this Mac. Separate historical working versions from a reproducible
OCI/package lock; current Linux GPU extra is CUDA. Keep any runtime proposal
prepared-only until reproducibility is demonstrated. Then implement/failure-test
independent expiry/reaper/deletion and verified private export for the new smoke,
preserving the consumed comparison campaign. Do not simply swap the mock renderer.
A live executor still needs runtime validation, long-render lease/deadline behavior
and controller gates. Any locked changes need fresh checks and reviewed relock.
No new training, hosting, invitations, serving promotion or paid allocations.
Ask for bounded compute/hosting choices when they block remaining offline work.

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
Latest scheduled continuation October 24. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
