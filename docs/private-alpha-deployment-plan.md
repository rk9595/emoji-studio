# Private-alpha deployment plan — October 13, 2026

Target: an always-available authenticated web/API queue with GPU workers paid for
only while needed. This is a proposed architecture, not a deployed service or a
commitment to new hosting charges. Keep pilot step 25 and its checksum lock.

## Verified baseline and missing work

The current FastAPI service already implements per-user hashed tokens, isolated
jobs/downloads, persistent usage records, quotas, feedback, PNG/WebP exports,
retention, and a single in-process generation worker. Its local jobs directory
survives process restart, **not loss of an ephemeral GPU VM**. Its GPU unload
releases VRAM, **not the provider bill**. Its rate limiter is process-local.

On October 13, 34 existing focused tests passed across API, alpha policy/reports,
GPU lifecycle and campaign/supervisor automation. These are local tests, including
mock rendering; they do not certify HTTPS, remote storage, or a deployed AMD API.
The independent 144-image ROCm evaluator passed, but used a different execution
path from the serving API. A live API smoke is still required.

## Proposed ownership boundary

| Component | Owns | Required behavior |
|---|---|---|
| Always-on CPU web/API | User authentication, admission, durable queue and usage ledger | Accept/status/download remain available without a GPU; quotas survive restart and deletion |
| Private durable storage | Job state, outputs and minimal accounting | Outputs survive GPU deletion; owner-authorized downloads and seven-day retention |
| Bounded dispatcher | Provider credentials, spend reservations, worker leases | One GPU maximum; no allocation when budget or capacity is unavailable; no secrets sent to browser |
| Disposable AMD worker | Pinned model and adapter, one leased job at a time | Upload/verify outputs before completion; recover interruptions without duplicate logical results |
| Cleanup monitor | Exact campaign ownership and expiry | Independent deletion timer plus reconciliation; record deletion receipt before releasing reservation |

The existing local file-backed API is a useful baseline but cannot simply be
exposed on a disposable GPU and called durable. Start with one API process; do
not add multiple replicas until admission and leasing are transactional across
processes. Add a remote AMD worker adapter rather than treating the existing
Vast-specific adapter as interchangeable.

## Ordered implementation gates

1. **Offline worker contract — completed October 16, no spending.** Local SQLite
   claim/heartbeat/lease expiry, atomic output commit, bounded failure/recovery,
   restart and duplicate/late-result handling are implemented and tested.
   See `docs/worker-lease-contract.md`. Simulated-worker and independent-process
   tests passed; the existing local rendering/API path is unchanged.
2. **Durable integration — local first.** Implement queue/storage adapters and
   transactional reservations. Test owner isolation, retries, retained usage
   after deletion, recovery after API/worker restart, and verified artifact
   commit. Surface waiting-for-capacity/budget honestly in the UI.
3. **Bounded AMD API smoke — prepare before allocation.** Validate the actual
   serving code through a private SSH tunnel: reject missing credentials, submit
   deterministic generation, poll, download PNG/WebP, verify transparency and
   metadata, reject another user's access, recover a restart, export artifacts,
   and confirm deletion. Lock the plan and a new explicit spend/time allowance;
   do not reset or reuse the consumed comparison campaign.
4. **Persistent hosting gate — requires a user decision.** Select the CPU host,
   durable storage location, HTTPS hostname/access arrangement and recurring
   monthly spending ceiling before provisioning. No paid provider signup,
   DNS modification, public endpoint or tester invitation is implied by this plan.
5. **Limited alpha.** Start with explicit per-user quotas and the existing
   100-image trial cap. Record prompt accuracy/anatomy feedback separately from
   visual style. Explain that crossed fingers and two-hand interactions remain
   unreliable. Run restore, isolation and cleanup checks before inviting users.

## Cost and automation controls

The completed comparison observed $1.99/hour for this AMD size. At that rate,
continuous allocation would be $47.76/day or $1,432.80 per 30 days, excluding
other charges. This arithmetic explains why the existing $100 AMD credit is not
an always-on GPU plan. Recheck actual prices before a future allocation.

Require a budget reservation covering startup, model download, work and cleanup
before allocation. Stop admitting paid work when no reservation fits. GPU idling
must lead to verified provider deletion, not merely `pipeline.unload()`.
Do not advertise interactive latency until cold-start and queue timings have
been measured through the serving API.

Provider cleanup and queued cloud jobs must work without the Mac or Codex.
The installed local Codex supervisor is a separate development convenience: it
checks available usage and the current thread, and can request continuation when
work is ready. It still requires the Mac awake and app-server available. Nothing
in this plan bypasses account limits or promises uninterrupted model reasoning.

## Parallel quality work without paid execution

Draft saved October 16 as `docs/collection-v3-proposal.md`, based on the coverage
audit and blinded review. Preserve old data, sampling receipts and holdout integrity.
Specify explicit finger identity/contact relationships and minimum exposures
for supported concepts; cap tiny-group oversampling. Do not invent visual
captions from labels, auto-approve reference images, or launch another training
run until the data and bounded experiment are reviewed.
