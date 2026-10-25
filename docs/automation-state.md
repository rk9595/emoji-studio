# Current state — 2026-10-25

User delegated private-alpha implementation, maximum automation and builder choice.
Read `ops/work-queue.json` next. Preserve unrelated recovery changes; only stage task
files. No new paid resource, GPU allocation, comparison repeat or public endpoint.

## Current cloud work

Private retention run **40170595914** failed at publication; the full CPU build
and 103 in-image tests passed. Fresh-pull job skipped. Source
`7bec449bd4e8b2ce9e2ad5b41c9abf2f556c7ab2`; evidence:
`reports/amd-retention-failure.json`, `docs/amd-private-retention.md`.
Exit 1 after 9m30s does not identify the underlying transport error. No published
manifest, absence, fresh pull or GPU success is established. New local config:
`sha256:776b9b0ab43ca3451205bceb879777bd395271a8d4b398871c29102e32f41ba0`.

Original tag: `cpu-7bec449bd4e8b2ce9e2ad5b41c9abf2f556c7ab2-40170595914`.
Local authenticated reads returned 404 but CLI lacks read:packages. Prepared
five-minute `AMD runtime retention reconciliation` workflow uses packages-read
only: original-tag/metadata reads, no layer downloads/build/push/delete/visibility
change. It preserves uncertainty on 404 and cannot authorize a retry. 79 tests/
120 subtests and Ruff/YAML checks passed; 38-file builder context unchanged.
Publication flag false and repository approved-source variable closed. No rerun.

## Next action after receipt

Read-only reconciliation run **40173475187** is queued at source
`80a5a74176dd97a3b64983ba19d2f49c5864117f`:
https://github.com/rk9595/emoji-studio/actions/runs/40173475187
Queue waiting_cloud with exact workflow/head/run; let ordinary supervisor wait.
On terminal status retain sanitized receipt. If tag exists,
require complete metadata verification; independent fresh pull remains pending.
If package access remains ambiguous, mark waiting_user for owner package-access
resolution. Do not infer absence, push another version or delete anything.

After retention resolution: durable reservations/reconciliation, private export/
ticket storage, independent cleanup scheduling and worker deadlines. GPU smoke
needs separately bounded allowance; persistent hosting needs budget/access.
Active locked-source changes need explicit tested relock. Serving remains pilot25.

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
