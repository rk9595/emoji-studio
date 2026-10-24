# Current state — 2026-10-24

User authorized continuing private-alpha work with maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next. Preserve unrelated
recovered worktree changes; historical handoffs are not the current plan.

## Latest completed work

AMD runtime metadata proposal completed:
`configs/amd-runtime-proposal.json`, `docs/amd-runtime-proposal.md`,
`reports/amd-runtime-preparation.json`. Official ROCm 7.2 / Ubuntu24.04 / Python3.12 /
Torch2.10 candidate base manifest digest bcb2efa1…32763e4 verified against registry
bytes and archived public config. Eight layers total 12.76 GB compressed; NO
layers pulled, GPU packages installed or GPU allocated. This is not proven to be
the identical image used in the historical comparison.

`configs/amd-overlay-linux-py312.txt`: 45 pinned/hash-listed application packages,
11 direct pins from retained uv.lock. Base Torch/vision/audio/Triton/Apex excluded
with their dependency traversal, so combined dependency compatibility remains
unverified. Second compile from cached metadata was byte-identical.
Checker `python3 scripts/check_amd_runtime_proposal.py` is offline/read-only;
explicit --registry reads only public fixed metadata and rejects tag drift.
**22 tests/30 subtests passed**, including 10 new tests; Ruff/diff checks pass.
Status prepared_only; runtime_validated false; derived image digest null.
Existing 23-file execution source lock unchanged, runtime still unresolved.

Mock-only executor/guard complete: `docs/mock-smoke-executor.md`,
`docs/render-budget.md`, `reports/mock-smoke-executor.json`. Stable job/image IDs;
two-call consumption spans render, export validation and atomic queue publication.
Uncertain calls/publications halt new work. No real renderer selection or provider
interface; default API/worker unchanged. Prior 166 tests/38 subtests passed.
Fresh prior HTTP smoke has 14 checks/three processes/two mock images.
No reset/refund/reclaim; trusted local disk only, no rollback/bypass protection.

Coverage prototype remains complete: `docs/coverage-sampler-prototype.md`,
`reports/collection-coverage-prototype.json`. 2,000 draws cannot cover 2,493 assets;
proposed 2,496 draws/624 steps give full coverage, not training approval.
Gesture gate blocks missing training buckets and visual-review metadata.
No dataset/caption/split edits; protected sampling/serving hashes unchanged.
Prior prototype suite: 32 tests/38 subtests passed.

Prior durable API remains opt-in, schema **4**, optional owner-scoped
Idempotency-Key; same request reuses job/seeds/usage across restart/full quota.
Key conflicts/deleted jobs return 409; no key creates a new job. X-Request-ID is
correlation only; UI does not send keys yet. Old DBs require explicit migration.
Docs: `docs/durable-api.md`, `docs/worker-lease-contract.md`. Prior 128 tests and
26 subtests passed (two existing warnings); real HTTP receipt has 14 checks,
three disposable processes and two mock images (`reports/local-http-smoke.json`).
Default API/serving unchanged. No backup/restore, monetary reservations,
provider dispatcher or authenticated remote worker. Metrics/rate windows are
process-local; lease fencing/idempotency are not exactly-once physical rendering.

AMD draft explicitly expanded/relocked for mock executor integration October 24:
`configs/amd-api-smoke-plan.json`, `docs/amd-api-smoke-plan.md`;
`python3 scripts/check_amd_api_smoke_plan.py` verifies 23 files and private adapter.
Receipt: `reports/amd-api-smoke-preparation.json`. Still **prepared_only**,
execution_authorized false, dollar allowance null. Proposed one GPU, two physical
render calls, 30 minutes including five for cleanup, zero automatic POST retries.
ROCm OCI/dependency lock, dedicated budgeted executor, independent reaper/deletion
receipts and verified private export remain prerequisites. Linux GPU dependencies
currently select CUDA; do not install that lock unchanged on AMD.

## Next ready work

Next: implement/failure-test independent expiry/reaper and exact-resource deletion
for the NEW smoke using mocked provider responses and the existing retained cleanup
patterns. Bind resource ownership/campaign/deadline, never delete unrelated assets,
and retain pending-cleanup until provider absence is verified. No deployment,
provisioning or modification/reset of the consumed comparison.
Then implement verified private export. Runtime proposal still needs a suitable
Linux/amd64 build environment with disk capacity, base/post-overlay inventories,
dependency/ABI/import checks, derived-image digest and in-image mock tests.
Do not install the overlay into this Mac or silently treat exclusions as validation.
Live HIP/GPU validation requires separately bounded authority; deadline/controller
gates remain open. Any active locked changes need tests and reviewed relock.
Ask for bounded compute/hosting/build choices when they block remaining offline work.

## Retained evidence

Consumed AMD comparison: 144 verified images, all four GPUs deleted October 13,
about $0.99 estimated total; no fifth attempt or campaign reset.
Run: https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release: `rk9595/emoji-studio-ops`, `amd-comparison-v1`.
Local results: `runs/amd-comparison-v1/`; `reports/amd-comparison-v1.md` records
blinded AI review, not new human review; all 84 gesture outputs failed requirements.
Serving remains reviewed pilot step 25, checksum in `configs/serving.json`.
`reports/collection-coverage-audit.md`: crossed fingers validation-only, folded
hands unsampled, high-five/pinky absent, tiny flags oversampled.
Collection-v3 proposal is a draft; no annotation/training approval changed.

## Automation

LaunchAgent `com.emoji-studio.codex-supervisor` checks every 15 minutes, respects
usage resets, skips active turns and may compact after six fresh handoffs.
Runtime ignored under `var/automation/`; Mac awake/app-server required.
Latest user continuation October 24. Do not promise uninterrupted reasoning.
Cloud campaign is complete and guarded against reallocation. AMD token needs
eventual rotation; never expose credentials in prompts/logs/reports/Git.
