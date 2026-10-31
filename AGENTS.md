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
On October30 the user said to use AMD credits freely for the API milestone and
destroy GPUs before Codex limits. Keep the concrete $2 aggregate reserve and30min
per-instance lifetime; max$1.99/hr, one concurrent GPU/two renders. Three failed
pre-generation attempts are consumed and independently deleted (~$0.6091 total).
Reviewed next correction permits provider startup15min inside the same lifetime;
campaignamd-api-smoke-20261030d is now dispatched after October31 headroom check.
Use exact run41173826485 and current queue before any action. Do not
allocate while quota is above85%; no GPU may idle waiting for model limits.
No fresh permission is needed for this delegated bounded correction; preserve all
claims and the consumed comparison. No automatic allocation POST retry.
The local usage guard requests cloud deletion at85% or loss of signal; cloud
expiry remains independent of Mac/model availability. GHCR remains deferred.
No new training or persistent hosting; hosting needs recurring budget/access.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
