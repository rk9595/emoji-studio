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
`reports/local-http-smoke.json`. **104 focused tests passed** (six new smoke tests,
98 previous tests; seven subtests). Ruff/diff checks pass. Two pre-existing
test-client deprecation warnings remain.

Limits: local disk durability only; no backup/restore, monetary reservations,
provider dispatcher or authenticated remote workers. Metrics/rate windows are
process-local. HTTP POST retries create new jobs: X-Request-ID is correlation,
not an idempotency key. Graceful shutdown waits for rendering; lease expiry does
not terminate a GPU or stop billing.

## Next ready work

Checksum-locked AMD smoke plan based on the completed local HTTP smoke, optional
HTTP idempotency contract and deterministic
sampler/preflight prototype. Keep public hosting and paid execution gated.
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
