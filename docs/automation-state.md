# Current state — 2026-10-16

User requested continued private-alpha work, maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next; older session
handoffs are historical. Preserve recovered unrelated worktree changes.

## Completed milestones

Offline worker foundation: `src/emoji_studio/worker_queue.py`, contract in
`docs/worker-lease-contract.md`. Local SQLite, one running claim, token-fenced
leases, heartbeats, bounded retries, atomic PNG/WebP pack commit, idempotent
completion, owner-scoped/hash-checked downloads. 18 new tests including separate
processes and transaction interruption; 57 focused tests passed overall.
Not wired into FastAPI yet; no quota/spend ledger or remote worker endpoint.
Existing service untouched. Lease expiry does not stop GPU billing.

Versioned data/sampler proposal: `docs/collection-v3-proposal.md` (draft only).
No data/caption/split edits, new images, model promotion or training. It separates
coverage-only and new-gesture experiments and requires explicit full-pass coverage.

AMD comparison finished: six conditions × 12 prompts × two seeds = 144 verified
images, PyTorch 2.10/ROCm 7.2 MI300X, evaluation wall time 607.25 seconds.
Run: https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release: `rk9595/emoji-studio-ops`, `amd-comparison-v1`; final `state.json`
and `results.tar.gz`. Local outputs: `runs/amd-comparison-v1/`; HTML blinded gallery
there. All image hashes, adapter locks and metadata passed verification.
All four allocated GPUs deleted; last `608604896` deletion confirmed 05:58:48 UTC.
Independent provider check returned zero campaign droplets. Total 1,792.29 seconds
allocated, approximately $0.99 at observed $1.99/hour (estimate, not billing receipt).
No fifth allocation or reset of this consumed campaign.

AI review: `reports/amd-comparison-v1.md`, raw observations and decoded summary
alongside it. Labels hidden until observations committed (`87a7e24`). All 84 gesture
outputs failed key relationships; all 12 backpacks met major details. Collection
checkpoints offer no clear promotion case. Serving remains pilot step 25, SHA
`2c7b15de79e9ac0bf59488068c9ec0f3444dec44899005499de87c2b28e93076`.
This was AI diagnostic review, not new human review or a sealed test.

Coverage audit: `reports/collection-coverage-audit.{md,json}`. Crossed fingers only
in validation; folded hands had zero sampled draws; high-five/pinky promise absent.
Six flags took 235 draws versus 231 across 1,504 People & Body images. Preserve
existing data; draft versioned corrections before further training.

## Next milestone and limits

`docs/private-alpha-deployment-plan.md` defines offline worker leases/recovery,
durable control-plane integration, bounded AMD API smoke, then hosted alpha.
Next: transactional admission/usage ledger plus opt-in local API/worker integration,
then prepare an AMD-specific API smoke plan. Legacy service smoke is NVIDIA/Vast
specific (path, monitoring, $0.70 cap); do not reuse it unchanged for AMD.
Live AMD API smoke and durable public deployment are not done.
No new training, serving promotion, hosting, invitations or paid allocations.
Queue ready work is local integration/tests, smoke preparation and sampler preflight.
Ask for a new
bounded execution allowance/hosting choice only when that becomes the blocker.

## Automation

Cloud evaluation and cleanup ran independently of the Mac. Fresh SSH readiness
connections avoid cached provider bootstrap commands; reuse begins after readiness.
Controller deadline 55 minutes, VM guard 65 minutes after initialization, independent
hourly reaper. Completed state prevents scheduled comparison reallocation.

Local LaunchAgent `com.emoji-studio.codex-supervisor` checks every 15 minutes.
`ops/codex_supervisor.py` reads account reset timestamps, skips active threads,
resumes idle/notLoaded/systemError states and requests compaction after six
continuations only with a fresh durable handoff. Runtime under ignored
`var/automation/`; same thread, no Codex credentials exported to cloud.
Needs Mac awake and app-server available. Read-only diagnostics and active-thread
skip passed; a scheduled continuation was received in this thread October 16.
Do not claim uninterrupted 24/7 Codex execution. AMD token still needs eventual
rotation; never expose credentials in prompts, logs, reports or Git.
