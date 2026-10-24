# Current state — 2026-10-24

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Standalone render-budget guard completed:
`src/emoji_studio/render_budget.py`, `docs/render-budget.md`,
`reports/render-budget-preparation.json`. Fixed two calls for amd-api-smoke-v1,
bound to allocation ID and plan hash. Atomically commits consumption before its
single-render callback; duplicate IDs never replay. Reserved/failed attempts stop
all further calls, even with unused capacity. No TTL/reclaim/refund/reset.
Explicit create refuses existing files; reopen refuses absent/corrupt/changed
identity or accounting. Callback errors, crash and ambiguous storage acknowledgements
consume capacity. Disk rollback/replacement or bypassing the wrapper is outside
this trusted local boundary. No provider, GPU imports or execution authority.

**101 tests/29 subtests passed**, including 18 new guard tests, queue/API regressions
and unchanged AMD integrity checks; two existing warnings. Ruff/diff checks pass.
Disposable receipt: two fake callbacks, third denied after reopen, ledger removed.
Guard is NOT wired into API/worker or included in the AMD execution source lock.

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

AMD draft last relocked for HTTP idempotency on October 23; unchanged this turn:
`configs/amd-api-smoke-plan.json`, `docs/amd-api-smoke-plan.md`;
`python3 scripts/check_amd_api_smoke_plan.py` verifies 18 files and private adapter.
Receipt: `reports/amd-api-smoke-preparation.json`. Still **prepared_only**,
execution_authorized false, dollar allowance null. Proposed one GPU, two physical
render calls, 30 minutes including five for cleanup, zero automatic POST retries.
ROCm OCI/dependency lock, dedicated budgeted executor, independent reaper/deletion
receipts and verified private export remain prerequisites. Linux GPU dependencies
currently select CUDA; do not install that lock unchanged on AMD.

## Next ready work

Next: mock-only dedicated smoke executor integration using the guard. Bind
stable logical job/image call IDs and exact request/model fingerprints; no retry
after an uncertain call or after rendering succeeded but job publication failed.
The existing renderer interface receives only prompt/seed; do not invent random
attempt IDs that permit duplicate physical work. Preserve default API behavior.
Read `docs/render-budget.md` and `docs/amd-api-smoke-plan.md`. Integration must
explicitly add guard/executor sources to the AMD lock, with fresh tests/local
HTTP smoke and reviewed relock. Keep real rendering/provisioning inaccessible.
Runtime lock, independent expiry/reaper/deletion and private export remain open.
No new training, hosting, invitations, serving promotion or paid allocations.
Ask for compute/hosting choices only when they block remaining offline work.

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
Latest user continuation October 24. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
