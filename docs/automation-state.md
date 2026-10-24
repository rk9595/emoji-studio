# Current state — 2026-10-23

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Coverage sampler/preflight prototype complete:
`src/emoji_studio/coverage_preflight.py`, `docs/coverage-sampler-prototype.md`.
Stdlib-only, checksum-pinned read-only manifest; deterministic concept/tone
interleaving without replacement per pass. Checks split family/exact-hash leakage,
required buckets/review-status metadata, complete-step arithmetic; rejects altered
supplied schedules. No trainer integration, data/caption/split edits or GPU work.
Receipt `reports/collection-coverage-prototype.json`; ordered proposal in
`reports/collection-coverage-prototype-schedule.json`. Protected manifest,
historical sampling and serving hashes unchanged.

Retained v2: 2,000 draws cannot cover 2,493 assets. Proposed aligned 2,496 draws
cover all assets in 624 steps with three repeats; these are NOT approved steps.
Explicit 2,000-draw diagnostic covers 2,000 unique assets. Gesture gate blocks on
missing crossed-fingers/high-five/pinky buckets and missing visual-review status.
Six folded-hands train assets appear in the full proposal. Metadata checks cannot
prove caption truth, provenance, family correctness or perceptual non-duplication.
**32 tests/38 subtests passed**, including 16 new tests plus local collection
regressions and unchanged AMD integrity tests. Ruff/diff checks pass.

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

AMD draft explicitly reviewed/relocked after these changes:
`configs/amd-api-smoke-plan.json`, `docs/amd-api-smoke-plan.md`;
`python3 scripts/check_amd_api_smoke_plan.py` verifies 18 files and private adapter.
Receipt: `reports/amd-api-smoke-preparation.json`. Still **prepared_only**,
execution_authorized false, dollar allowance null. Proposed one GPU, two physical
render calls, 30 minutes including five for cleanup, zero automatic POST retries.
ROCm OCI/dependency lock, dedicated budgeted executor, independent reaper/deletion
receipts and verified private export remain prerequisites. Linux GPU dependencies
currently select CUDA; do not install that lock unchanged on AMD.

## Next ready work

Resolve remaining AMD smoke prerequisites offline. Next concrete component:
durable physical-render budget for the proposed two-call smoke, reserved before
each render; uncertain/interrupted calls consume budget. Test concurrent attempts,
restart/crash and budget exhaustion without allocating or loading a GPU. Keep it
separate from the consumed comparison and avoid importing provisioning credentials.
Read `docs/amd-api-smoke-plan.md` before implementing. Runtime/independent cleanup
and private export still need work; never provision merely to investigate.
Any AMD-locked source changes require fresh smoke/tests and explicit reviewed
relock. No training, hosting, invitations or serving promotion authorized.
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
Latest scheduled continuation October 23. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
