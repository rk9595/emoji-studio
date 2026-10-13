# Current state — 2026-10-13

User requested continued work toward private alpha, maximum automation, usage-reset
continuation, and concise persistent memory. This file supersedes historical
session handoffs. Read `ops/work-queue.json` for the next ready task.

Completed: AMD MI300X inference, adapter loading, training, checkpoint resume and
24-image benchmark validated on October 11. Original validation VM deleted.
Reviewed serving adapter: pilot step 25, SHA `2c7b15de79e9ac0bf59488068c9ec0f3444dec44899005499de87c2b28e93076`.
Collection training already completed 500 steps; four retained adapters exist.

In progress: `amd-adapter-comparison-v1`, six conditions × 12 prompts × two seeds
= 144 images. The inputs include the base model, pilot step 25 and collection
steps 125/250/375/500. Same model revision, ROCm, prompts, seeds and sampling.
The offline review hides candidate labels and randomizes comparison sides.

Private cloud queue/artifacts: https://github.com/rk9595/emoji-studio-ops
Release: `amd-comparison-v1`; read `state.json` for authoritative runtime status.
One GPU at a time; $1.99/hour ceiling; 55-minute controller deadline; VM self-deletion
65 minutes after initialization; independent hourly reaper; $3 billing reserve.
Snapshots and final results are retained as private release assets. Schedules can
be delayed; the VM guard does not depend on GitHub or the Mac remaining connected.
Existing AMD token was still valid and is now in private operations secrets.
It must eventually be rotated; do not expose it in model context or output.

Codex continuation: `ops/codex_supervisor.py` checks the existing app-server and
documented usage-reset timestamps, backs off while limited, and resumes this same
thread only when idle and work is ready. Runtime config/state live under ignored
`var/automation/`. It does not bypass limits or store Codex credentials in GitHub.
It needs the Mac awake. The GPU job is independent and continues during sleep.
Installed as `com.emoji-studio.codex-supervisor` in the user's LaunchAgents, every
15 minutes. Real read-only checks of this thread and account limits passed; the
first launchd invocation exited 0 and correctly skipped this active thread.
Usage-limit waiting and active-thread protection also have focused regression tests.
After six automatic continuations, it may request context compaction between turns
if the durable handoff was updated. Normal app-managed compaction still applies.

Attempt 1: GitHub run `38253774910`, droplet `608402117`, failed during SCP input
transfer before GPU evaluation. Cleanup verified at 13:12:41 UTC; estimated GPU
cost $0.083 (not a billing receipt). Evidence under
`artifacts/amd-comparison-v1/attempt-1/`. Recovery replaces SCP with resumable rsync
and preserves useful stderr diagnostics.

Attempt 2: run `38254409392`, droplet `608403269`, exposed rsync protocol mismatch
from an unclean remote shell during initialization. Deleted at 13:19:17 UTC.
Both attempts combined used about 373 seconds, approximately $0.207 at list rate.
The final recovery requires `/var/lib/cloud/instance/boot-finished`, the expiry
timer, and an exact clean SSH readiness sentinel before transfer. A regression
test rejects success exit codes accompanied by initialization banners. The
controller additionally reserves 75 minutes plus prior runtime inside the same
$3 allowance. Three attempts maximum, never concurrently; no fourth allocation.
Attempt 3: run `38255542347`, droplet `608405707`, passed the strict readiness gate
and uploaded all inputs, then stopped on an unretried SSH timeout during checksum
verification. Deleted at 13:30:20 UTC. Three attempts used about 674 seconds,
approximately $0.373 at list rate. All three deletions are confirmed; no images
were rendered. October 13 user said continue. The repaired controller reuses one
SSH connection, retries safe commands, and uses an idempotent systemd worker unit.
Run `38352558272` is the fourth attempt inside the same $3 reserve (prior runtime
+ 75-minute reservation projects about $2.86). No fifth allocation.
Read private release `state.json` for its live ID and outcome.

Supervisor repair: systemError threads now follow thread/resume before turn/start;
GitHub state reads retry transient failures. Live account/thread diagnostic passes.
Regression tests cover both changes. Earlier overnight continuation did not occur:
the Mac was often asleep, a cloud-state fetch failed, and systemError was previously
unsupported. Do not claim uninterrupted 24/7 Codex execution.

Coverage audit completed: `reports/collection-coverage-audit.{md,json}`.
Crossed fingers: six validation images, zero training; folded hands: six train
images but zero sampled draws; high-five/pinky promise absent; bicycle one draw.
Six flags took 235 draws versus 231 across 1,504 People & Body images. This informs
future data/sampler work; existing dataset and serving adapter remain unchanged.

No new collection training or serving-adapter promotion has occurred. Historical
files include recovered user changes; commit only deliberately selected files.
