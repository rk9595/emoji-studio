# Current state — 2026-10-23

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

Opt-in local API: `emoji_studio.durable_api.create_app`, explicitly supplied
renderer/database; default `api.create_app` and serving entry point unchanged.
See `docs/durable-api.md` and `docs/worker-lease-contract.md`.
SQLite queue schema **3** adds request/result metadata, timestamps and feedback
to atomic admission/usage and lease-fenced output commits. Refuses schema-2/legacy
migration; no existing jobs/databases were modified. Local worker renews leases,
recovers expired attempts and rejects stale outputs; complete packs publish atomically.
API covers auth/ownership, status/history, PNG/WebP exports, quotas, feedback,
terminal deletion and retention without refunding usage. Tests use temporary
databases and MockRenderer; no live GPU/API or public deployment claim.
Real loopback HTTP smoke now implemented: `python -m emoji_studio.smoke_http`.
Three API processes, fresh temporary DB, two mock images; verifies queued and
completed restart recovery, deterministic exports, auth/ownership, feedback,
quotas and deletion accounting. Bounded cleanup plus independent child watchdog;
no public listener, persistent service or GPU. Receipt/source hashes:
`reports/local-http-smoke.json`.

AMD API smoke draft source lock prepared: `configs/amd-api-smoke-plan.json` and
`docs/amd-api-smoke-plan.md`. Read-only checker:
`python3 scripts/check_amd_api_smoke_plan.py`. Verified 18 source/evidence files
and the private pilot-25 adapter; receipt `reports/amd-api-smoke-preparation.json`.
Status is **prepared_only**, not execution-ready/authorized. Proposed bounds:
one new GPU allocation, two admitted images/physical render calls, 30 minutes
including five for cleanup; approved dollars remain null. ROCm OCI digest and
AMD dependency lock, dedicated budgeted executor, independent reaper/deletion
receipts and verified private export destination remain prerequisites. Existing
Linux GPU dependency lock selects CUDA wheels; never install it unchanged on AMD.
**114 focused tests passed**, 19 subtests, Ruff/diff checks pass; two existing
test-client warnings. Ten new tests enforce draft limits/authority/source integrity.

Limits: local disk durability only; no backup/restore, monetary reservations,
provider dispatcher or authenticated remote workers. Metrics/rate windows are
process-local. HTTP POST retries create new jobs: X-Request-ID is correlation,
not an idempotency key. Graceful shutdown waits for rendering; lease expiry does
not terminate a GPU or stop billing.

## Next ready work

Optional HTTP idempotency contract, then deterministic sampler/preflight prototype.
Changing API/worker sources invalidates the AMD draft lock: rerun tests/local
smoke, refresh the receipt and review an explicit relock; never silently bless drift.
Resolve remaining AMD executor/runtime/cleanup prerequisites offline where possible.
Keep public hosting and paid execution gated.
Legacy service smoke is NVIDIA/Vast-specific; don't reuse unchanged for AMD.
No new training, hosting, invitations, serving promotion or paid allocations.
Ask for missing compute/hosting choices only when they block remaining work.

## Retained evidence

AMD comparison completed: 144 verified images; all four GPUs deleted October 13;
about $0.99 estimated total GPU cost. No fifth attempt or campaign reset.
Run: https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release: `rk9595/emoji-studio-ops`, `amd-comparison-v1`.
Local results/gallery: `runs/amd-comparison-v1/`.
`reports/amd-comparison-v1.md`: blinded AI review, not new human review; all
84 gesture outputs failed key requirements, no collection checkpoint promoted.
Serving remains pilot step 25 with the checksum locked in `configs/serving.json`.

`reports/collection-coverage-audit.md`: crossed fingers validation-only, folded
hands unsampled, high-five/pinky absent, tiny flags group oversampled.
`docs/collection-v3-proposal.md`: draft coverage/gesture experiments only; no
data, captions, holdout or annotation approval changed.

## Automation

Completed cloud campaign state prevents reallocation; independent expiry/reaper
guards retained. Local LaunchAgent `com.emoji-studio.codex-supervisor` checks
every 15 minutes, respects usage-reset timestamps, skips active turns, and may
compact after six continuations with a fresh handoff. Runtime is ignored under
`var/automation/`; same thread, no Codex credentials exported.
Needs Mac awake and app-server available; latest scheduled continuation October 23.
Do not promise uninterrupted 24/7 reasoning. AMD token needs eventual rotation;
never expose credentials in prompts, logs, reports or Git.
