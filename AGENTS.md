# Emoji Studio working memory

Read `docs/automation-state.md` and `ops/work-queue.json` first. They contain the
current milestone, live operation identifiers, limits, and next action. Read older
reports only when needed; `docs/session-handoff.md` contains historical state.

The user authorized continuing toward the private alpha and requested as much
automation as possible on 2026-10-12, including resuming after usage resets and
keeping memory concise. Do not ask again for routine implementation steps.

Maintain those two small files after each meaningful milestone and before a turn
ends. Keep durable links/hashes instead of repeating full logs. Never put tokens,
private keys, or account secrets in memory, Git, reports, or prompts.

The AMD comparison is complete: all 144 images verified, all four allocated
instances deleted, approximately $0.99 estimated GPU cost against a $3 reserve.
See `reports/amd-comparison-v1.md`. Do not reset it or launch a fifth attempt.
The next milestone is now complete: on October31, two real emojis were generated
through the authenticated HTTP API on one AMD MI300X, privately downloaded/hash-
verified, and the GPU independently confirmed deleted. All four API-test instances
are deleted; estimated total$0.7751 within the$2 reserve. See
`reports/amd-api-live-result.json`, run41173826485/releaseamd-api-smoke-20261030d.
API milestone complete, exact-source gate closed. Never reset these claims or the consumed
comparison. No additional allocation belongs to this completed milestone.
The user requires GPU destruction before Codex limits. Retain the85% local usage
stop, independent cloud watchdog and on-instance expiry for future bounded runs.
No GPU may idle while waiting for quota reset. GHCR work remains deferred.
On October31 the user asked to continue training. Bounded Fluent coverage run
41203305217 is active on GPU614520349 (last observed booting). Queue waiting_cloud;
source82b486c9ba73ee47332f4f8f0e1f14b6de9ed6a6, releaseamd-coverage-20261031a.
Read reports/amd-coverage-dispatch.json and docs/coverage-training-v1.md.
One allocation/60minutes/$2.25; two-step smoke gates main624steps and49renders.
Work cutoff13:51:40UTC October31, expiry13:52:40UTC. Local85% usage guard and
independent watchdog active. Gate closed running-41203305217. Do not dispatch again.
Wait using cloud receipts, verify private artifacts and deletion on completion.
Do not claim training success yet. Preserve v2 data/captions/splits, old trainers
and serving adapter. No persistent hosting; Noto licensing remains separate.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
