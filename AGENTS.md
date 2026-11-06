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
The next milestone is now complete: on October31, two real emojis were generated
through the authenticated HTTP API on one AMD MI300X, privately downloaded/hash-
verified, and the GPU independently confirmed deleted. All four API-test instances
are deleted; estimated total$0.7751 within the$2 reserve. See
`reports/amd-api-live-result.json`, run41173826485/releaseamd-api-smoke-20261030d.
API milestone complete, exact-source gate closed. Never reset these claims or the consumed
comparison. No additional allocation belongs to this completed milestone.
The user requires GPU destruction before Codex limits. Retain the85% local usage
stop, independent cloud watchdog and on-instance expiry for future bounded runs.
No GPU may idle while waiting for quota reset. GHCR work remains deferred.
Training run41203305217 failed before the worker started: provider langchain-core
requires packaging<26, but the overlay installed26.3. GPU614520349 independently
confirmed deleted; estimated$0.1382. Claim consumed; gate failed-41203305217.
Corrective overlayv2 pins packaging25.0; other73pins unchanged. 65tests and local
trainer import/dependency checks pass. Read reports/amd-coverage-first-attempt.json
and reports/amd-training-corrective-preparation.json. That attempt produced no
training or checkpoints.
Corrective run41273277371 stopped during boot when usage reached85%; no training.
GPU614682073 deletion independently confirmed by read-only run41274185805 (exact404).
Both training GPUs deleted; aggregate estimated$0.2075 within SAME$2.25 reserve.
Campaignb claim consumed, gate failed-41273277371. reports/amd-coverage-second-attempt.json.
Original watchdog failed an ownership check; strict checks retained, bounded retry
handling now tested. Do not claim its original watchdog succeeded. 26focused tests pass.
On 2026-11-01 the user continued in Cursor and authorized the launch, raising the
training reserve to $10. Run 41282477874 completed the 656-step Fluent-plus-Noto
train and saved step-656.safetensors. Evaluation failed: step-500 was not
retained. GPU 614708454 is deleted. Estimated cost $0.504, aggregate $0.7115.
Campaign c is consumed. Evaluation release amd-noto-eval-20261101d, run
41321034924, source 51b989c0207d7b7d430c85c71b1808043154375d, allocated GPU
614806003 and deleted it. The worker failed before any image: eval mode skipped
the overlay, so safetensors was missing. Estimated cost $0.1299, aggregate
$0.8414 of the $10 reserve. Watchdog confirmed cleanup. No images. Claim
consumed. No promotion. Codex usage guard stays off.
Corrected evaluation campaign e completed: release amd-noto-eval-20261105e,
run41998689039, source f973f98918eed2f26c6567cfe38b2866a018fc96. Exactly24
512px images and the saved step-656 adapter were archive/hash verified; no
training. Results sha256 1a72454f8e11db3a51e069f0c1d0628e79339aad6e8ecaf4d0e4a691c75821c1.
GPU616116808 was deleted and independently confirmed absent. Cost~$0.2199;
training/evaluation aggregate~$1.0613 of$10. Claim consumed; never rerun.
AI review: faces/objects are coherent, but high-fives read as prayer hands,
crossed fingers are ambiguous/inconsistent, and pinky-promise quality is mixed.
No matched baseline, improvement claim, or promotion. Serving stays pilotstep25.
Current milestone is complete; a new training direction or promotion requires
user judgment and a fresh immutable plan/claim.
November 6 continuation verified that historical base/pilot images match all
24 candidate prompt/seed pairs and rendering settings. See
reports/noto-baseline-reuse.md and scripts/audit_noto_comparison.py. Next ready
work is an offline shuffled review using retained images; no GPU required.

Public code: `rk9595/emoji-studio`. Private execution and model artifacts:
`rk9595/emoji-studio-ops`, release `amd-comparison-v1`.
Jobs should survive Mac sleep and Codex usage limits. The local Codex supervisor
requires the Mac to be awake and app-server available. Polling is ordinary code;
only ready work should start a model turn. Leave a clear waiting state when blocked.

Keep the serving adapter at the reviewed pilot step 25 until a documented quality
decision warrants changing it. Label automated visual judgments as AI review.
Preserve recovered uncommitted files and the USB original. Stage only intentional
changes for this task; the worktree contains unrelated recovery changes.
