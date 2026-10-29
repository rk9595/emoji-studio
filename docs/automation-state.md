# Current state — 2026-10-29

User delegated private-alpha implementation, maximum automation and builder choice.
Read `ops/work-queue.json` next. Preserve unrelated recovery changes; only stage task
files. No new paid resource, GPU allocation, comparison repeat or public endpoint.

## Current work — ready, offline only

Offline lifecycle coordination is complete: `docs/smoke-lifecycle.md`,
`reports/smoke-lifecycle-preparation.json`. 28 new tests; combined **215 tests/252
subtests** passed, Ruff passed, existing 23-file execution and 38-file build locks
verified unchanged. No live adapter, deployment or provider calls.

`SmokeLifecycle` pins bound reservation/cleanup/render identities. Registration
intent is persisted once; exact independent-service assertions require fresh reads.
Only MockSmokeExecutor runs; deadline/registration/cleanup gates surround guarded
callbacks. Stage export from owner-scoped successful publications; persist immutable
ticket before one upload; restart verifies downloads without bundle or write retry.
Cleanup uses a separate lock and progresses during blocked upload/render. Completion
is offline only; live smoke/GPU acceptance always false. Independent-service claims
are mocked/trusted assertions; no production scheduler or hard kill is implemented.

Reservation component: `docs/smoke-reservation.md`, 27 tests. One committed CREATE
intent; unknown results never grant a replacement. All reserve/approval amounts in
tests are synthetic. Global authoritative reservations and external durable storage
still need live implementation; local files are not a distributed spend cap.

Next ready task: prepare/test sanitized runtime publication diagnostics and review
a revised bounded retention proposal offline. Retain fixed stage/exit/timing/error
classifications without secrets or signed URLs. Do not auto-retry or re-enable the
closed gate. No active cloud job. Further live integration needs external intent/
receipt storage, independent expiry service and worker deadlines, tested source
relock, verified runtime and separately bounded GPU allowance.

## Private runtime retention — still unverified

October 29 signed-in owner browser showed “Your Packages” / “Get started with
GitHub Packages” with no package rows: `reports/amd-retention-owner-check.json`.
The earlier owner-check request is satisfied; do not keep asking the user or block
independent offline work. This UI observation does not prove atomic registry absence
or explain the original publication failure. No permissions were changed.

Publication **40170595914** passed 103 in-image CPU tests, then failed (exit 1,
9m30s publication step); fresh pull skipped. `reports/amd-retention-failure.json`.
Read-only reconciliation **40173475187** returned package/tag 404 with packages-read:
`reports/amd-retention-reconciliation.json`. Local CLI lacks read:packages.
Original tag: `cpu-7bec449bd4e8b2ce9e2ad5b41c9abf2f556c7ab2-40170595914`.
New local config: `sha256:776b9b0ab43ca3451205bceb879777bd395271a8d4b398871c29102e32f41ba0`.
It is not a verified published manifest. Transport diagnostics were ephemeral.

Publication flag false and approved-source variable closed. Review sanitized
failure diagnostics and any revised bounded attempt deliberately before enabling
publication; current policy has no automatic retry, second version, delete,
visibility change or paid fallback. October 25 pricing review is stale for a new
attempt. Independent fresh pull and GPU validation remain unverified.

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
sanitized exports with independent download hashes. Live adapters/deployed controller remain.
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
