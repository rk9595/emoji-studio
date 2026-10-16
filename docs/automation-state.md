# Current state — 2026-10-16

User requested continued private-alpha work, maximum automation, usage-reset
continuation and concise memory. Read `ops/work-queue.json` next; older session
handoffs are historical. Preserve recovered unrelated worktree changes.

## Completed milestones

Offline worker queue: `src/emoji_studio/worker_queue.py`; contract in
`docs/worker-lease-contract.md`. One running claim, token-fenced renewable leases,
bounded retries, atomic output commit and hash-checked owner-scoped downloads.
Schema v2 adds atomic admission + daily UTC/global lifetime image-usage ledger,
idempotent reservations and terminal-content deletion that retains accounting.
Trial policy is persisted; legacy/unversioned databases require explicit migration.
18 lease tests + 23 admission tests; 80 focused tests passed overall, including
separate-process races and transaction failures. No FastAPI wiring, automatic
retention, monetary reservations or remote worker endpoint yet. Existing serving
path/data untouched. Lease expiry does not stop GPU billing.

Versioned data/sampler proposal: `docs/collection-v3-proposal.md` (draft only).
No data/caption/split edits, new images, model promotion or training. It separates
coverage-only and new-gesture experiments and requires explicit full-pass coverage.

AMD comparison completed: 144 verified images, six conditions, MI300X/ROCm 7.2.
Run: https://github.com/rk9595/emoji-studio-ops/actions/runs/38352558272
Private release: `rk9595/emoji-studio-ops`, `amd-comparison-v1`; local outputs and
gallery in `runs/amd-comparison-v1/`. All four allocated GPUs deleted October 13;
provider lookup confirmed none remained. About $0.99 estimated total GPU cost.
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
Next: opt-in local API/worker integration using the completed atomic admission
method, then prepare an AMD-specific API smoke plan. Legacy service smoke is NVIDIA/Vast
specific (path, monitoring, $0.70 cap); do not reuse it unchanged for AMD.
Live AMD API smoke and durable public deployment are not done.
No new training, serving promotion, hosting, invitations or paid allocations.
Queue ready work is local integration/tests, smoke preparation and sampler preflight.
Ask for a new bounded execution allowance/hosting choice only when it blocks progress.

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
