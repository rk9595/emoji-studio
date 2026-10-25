# Current state — 2026-10-25

User delegated private-alpha implementation, maximum automation and builder choice.
Read `ops/work-queue.json` next. Preserve unrelated recovery changes; only stage task
files. No new paid resource, GPU allocation, comparison repeat or public endpoint.

## Current cloud work

Private runtime retention run **40170595914** is running at source
`7bec449bd4e8b2ce9e2ad5b41c9abf2f556c7ab2`:
https://github.com/rk9595/emoji-studio/actions/runs/40170595914
Workflow **AMD runtime private retention**; standard public Ubuntu CPU runners.
Exact source is bound by `AMD_RETENTION_APPROVED_SOURCE`. Queue waiting_cloud;
supervisor verified run/head/workflow and skips model turns until terminal status.

`docs/amd-private-retention.md`, `reports/amd-retention-preparation.json`:
72 tests/112 subtests passed; Ruff/YAML checks pass. Read-only verifier checks
manifest/config hashes, platform/rootfs, package ownership/privacy/version count,
anonymous token flow, bounded credential-free CDN redirects and source/rerun gates.
Active/template workflow copies match. Original 38-file builder context unchanged.

Preparation is complete. One private GHCR version is within existing delegated
implementation scope at zero paid cost; publication flag now true, GPU/paid flags
false. GHCR storage/bandwidth policy rechecked October 25. Local namespace lookup
returned 404 (not proof of workflow access). Destination:
`ghcr.io/rk9595/emoji-studio-amd-runtime`; no latest/overwrite/delete/paid fallback.
No registry success is claimed until `RETENTION_RECEIPT` after the fresh job.

First job: repeat CPU build, recheck scope, Skopeo copy with zero command retries,
verify authenticated manifest/config and anonymous denial. 45-minute job cap,
30-minute build/10-minute copy. Second fresh runner has packages-read only:
pull immutable digest, compare config/platform, repeat CPU audit offline, recheck
privacy. 30-minute cap, 20-minute pull/five-minute audit. No GPU/model execution.
Tokens stay out of image/build context; auth files and transport diagnostics stay
in disposable runner storage. No Actions artifact/cache upload.

## Next action after receipt

Inspect exact run only when terminal. Retain sanitized receipts and first failure.
If successful, record published manifest/config digest and independent pull/CPU
verification; keep GPU validation false. If copy fails/ack is lost, reconcile the
original unique tag read-only; do not rerun/push another version or delete one.
If preflight fails before publication, retain evidence and review cause before any
new attempt. Never weaken privacy/digest checks or silently change registry scope.

Then integrate durable reservations/reconciliation, private export/ticket storage,
independent cleanup scheduling and worker deadlines. GPU smoke needs a separately
bounded allowance; persistent hosting needs budget/access. Active locked-source
changes need explicit tested relock. No human review or adapter promotion occurred.

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
