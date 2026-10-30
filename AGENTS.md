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
On 2026-10-29 the user explicitly authorized AMD credits for the next milestone:
two emojis through the API on one AMD GPU. The first allocation failed before
generation and was deleted (~$0.1256). On October 30 the user continued after a
reviewed corrective attempt was described. Campaign `amd-api-smoke-20261029b`
allows one corrective MI300X at $1.99/hour, 30 minutes including cleanup; the
aggregate reserve stays $2 across both attempts. No third allocation or automatic
POST retries. Check the current receipt first; never reset either claim or the
consumed comparison. Custom GHCR image
publication is deferred. Existing overall AMD credit is not a mandate to spend it
continuously. Further cloud smoke/training needs a separately bounded allowance;
persistent hosting needs a user-selected recurring budget and access arrangement.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
