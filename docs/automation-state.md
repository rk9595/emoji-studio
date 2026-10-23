# Current state — 2026-10-23

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Opt-in local API: `emoji_studio.durable_api.create_app`; default API/serving
entry point unchanged. See `docs/durable-api.md`, `docs/worker-lease-contract.md`.
Optional owner-scoped `Idempotency-Key` now atomically deduplicates HTTP admission.
Same normalized prompts/requested seed return the original job and resolved seeds,
including after restart/full quota/lost response; changed input or deleted jobs
return 409. No key means a new job; X-Request-ID remains correlation only.
Auth and request-rate limits still apply. Usage and hashed key tombstones survive
deletion/retention. SQLite schema **4** refuses schema 3 and older without modifying
them; no production database migrated. Client UI does not yet send keys.

Lease-fenced local worker, atomic pack publication, auth/ownership, exports,
feedback, quotas and retention remain implemented. Same-disk durability only:
no backup/restore, money reservations, provider dispatcher or remote workers.
Metrics/rate windows are process-local; idempotency is not exactly-once rendering.
Lease expiry does not stop billing; graceful shutdown waits for rendering.

Fresh real loopback HTTP smoke: three disposable API processes, two mock images,
14 checks including keyed retries across restart/full quota/deletion. Receipt:
`reports/local-http-smoke.json`. **128 tests and 26 subtests passed** across the
regression suite and draft-integrity suite; two existing test-client warnings.
Ruff/diff checks passed. Tests include cross-process duplicate/conflicting requests,
rollback, random seeds, lost responses, owner isolation and schema-3 refusal.

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

Deterministic coverage sampler/preflight prototype using synthetic fixtures and
read-only manifests per `docs/collection-v3-proposal.md`. Do not alter data,
captions, splits or adapter. Then resolve remaining AMD prerequisites offline.
Any locked source changes require fresh smoke/tests and explicit reviewed relock;
the checker must never silently bless drift. Older local databases need a separately
designed migration before reuse; never reset them to bypass schema checks.
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
Latest scheduled continuation October 23. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
