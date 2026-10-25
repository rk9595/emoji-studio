# Current state — 2026-10-25

User delegated private-alpha implementation, maximum automation and builder choice.
Read `ops/work-queue.json` next. Preserve unrelated recovery changes; only stage task
files. No new paid resource, GPU allocation, comparison repeat or public endpoint.

## Current blocker — waiting_user

Private retention remains unresolved. Read-only reconciliation **40173475187**
completed successfully on October 25, but package and original-tag reads both
returned 404 with the repository packages-read token. This is not proof of absence.
Receipt: `reports/amd-retention-reconciliation.json`; source
`80a5a74176dd97a3b64983ba19d2f49c5864117f`:
https://github.com/rk9595/emoji-studio/actions/runs/40173475187
No active cloud job; queue waiting_user prevents repeated automated model turns.

Owner must check GitHub Packages for `rk9595/emoji-studio-amd-runtime`.
If present, confirm private visibility and grant `rk9595/emoji-studio` Actions read
access, then verify the original tag. Do not ask for credentials in chat. If absent,
record the owner observation and deliberately review a revised bounded attempt;
absence alone is not an automatic retry authorization. No new publication now.

Original publication run **40170595914** passed all 103 in-image CPU tests, then
failed in publication (exit 1 after 9m30s); fresh-pull job skipped. Underlying
transport diagnostic is unavailable. `reports/amd-retention-failure.json` retains
the audit and log hash. Original tag:
`cpu-7bec449bd4e8b2ce9e2ad5b41c9abf2f556c7ab2-40170595914`.
New local config identity (not a verified published manifest):
`sha256:776b9b0ab43ca3451205bceb879777bd395271a8d4b398871c29102e32f41ba0`.

Publication flag false and approved-source variable closed. No rerun, second
version, deletion, visibility change or paid fallback. Reconciliation did no layer
download/build/push. Preparation passed 79 tests/120 subtests and Ruff/YAML checks;
38-file builder context unchanged. Independent fresh pull and GPU validation remain
pending. Local CLI lacks read:packages; do not repeat its inconclusive 404 probes.

## After access resolution

Retain owner observation/access resolution; perform only necessary read-only checks
on the original tag. Existing image needs full metadata verification and separately
reviewed independent fresh-pull audit. Never treat workflow success as retention.
Then integrate durable reservations/reconciliation, private exports/ticket storage,
independent cleanup scheduling and worker deadlines. GPU smoke needs separately
bounded allowance; persistent hosting needs budget/access. Active locked-source
changes need explicit tested relock. Serving remains pilot25.

## Completed evidence

CPU run **40166592399**, source `acef6db19b00ddcb07dbff290bfde2ff825c80ed`, passed:
103 in-image tests, dependency/native CPU checks, HTTP and guarded executor smokes.
42 base/78 installed distributions, 45 overlay pins match, five GPU versions unchanged.
`reports/amd-cpu-validation.json`, `docs/amd-cpu-validation.md`. Its ephemeral local
config ID 2c3ad8f4…bb81ab9 is not a published manifest and must not be reused as one.
Base digest bcb2efa1…32763e4, ROCm7.2/Python3.12/Torch2.10; no local GPU install.

`configs/amd-api-smoke-plan.json` still prepared_only, execution false, allowance
null, runtime unresolved; source checker verifies 23 files/private pilot adapter.
Two physical renders/one GPU proposed, zero replacement, 30 minutes including
five for cleanup. CPU validation alone does not clear GPU/controller gates.

Offline components: `docs/render-budget.md`, `docs/mock-smoke-executor.md`,
`docs/smoke-cleanup-contract.md`, `docs/smoke-private-export.md`. Two-call guard;
stable call IDs/publication fencing; exact-resource deletion with durable pending;
sanitized exports with independent download hashes. Live adapters/controller remain.
Durable API is opt-in/schema4, owner-scoped idempotency; default serving unchanged.
Coverage proposal: 2,496 draws/624 steps covers 2,493 assets, not training approval;
`docs/coverage-sampler-prototype.md` and collection audit retain missing-gesture gates.

Consumed comparison: 144 verified images, all four GPUs deleted, ~$0.99 estimated.
Private run https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release `amd-comparison-v1`; `reports/amd-comparison-v1.md` records AI review,
all 84 gesture outputs failed. Serving remains pilot step25. No fifth allocation.

## Automation

LaunchAgent `com.emoji-studio.codex-supervisor` checks every 15 minutes, respects
usage resets/skips active turns, may compact after six handoffs. Mac awake/app-server
required; do not promise uninterrupted reasoning. Exact Actions receipt monitoring
supports CPU validation and private retention; never substitute the old comparison
release for a queued Actions run. Credentials never belong in memory/Git/logs.
