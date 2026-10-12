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

The AMD comparison is one GPU at a time, six conditions, 144 matched images, at most
$1.99/hour. Its controller deadline is 55 minutes and its independent VM deletion
timer is 65 minutes after cloud initialization; reserve $3 with billing margin.
This reserve is not a provider-enforced spending cap. The initial transfer failed
and was cleaned up; the second exposed unclean SSH during initialization. A final
recorded recovery with a strict readiness sentinel is allowed within the same $3
reserve (three attempts total), checked against prior runtime plus 75 minutes of
new reserved runtime. No further automatic allocation.
Existing overall AMD credit is $100;
this is not a mandate to spend it continuously.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
