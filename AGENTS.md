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
On October30 the user explicitly approved a third bounded API attempt and asked
for GPU destruction before Codex usage limits. Active campaign
`amd-api-smoke-20261030c`: one MI300X, max30 minutes, $1.99/hour ceiling, two physical
renders, unchanged $2 aggregate reserve including ~$0.3696 from two failed/deleted
attempts. Prior allocation claims and comparison remain consumed. Do not ask again
for this approved attempt or routine fixes. No automatic allocation/POST retries.
Local `ops/amd_usage_guard.py` reads usage every30sec and requests cloud cleanup at
85% usage, or after two unavailable usage readings. Cloud controller/watchdog honor
the bound stop request; on-instance expiry is independent of Mac/model availability.
Custom GHCR publication remains deferred. No training or persistent hosting begun;
persistent hosting still needs recurring budget/access.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
