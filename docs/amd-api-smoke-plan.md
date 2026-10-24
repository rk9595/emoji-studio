# AMD API smoke v1 — prepared only, October 23, 2026

This is a checksum-locked **proposal, not execution authorization**. No GPU,
runtime image, paid host, public endpoint or campaign state was created. The
completed comparison's four allocations and $3 reserve remain consumed and
cannot fund or trigger this plan. The new identifier is `amd-api-smoke-v1`.

`configs/amd-api-smoke-plan.json` locks 23 source/config/evidence files at baseline
commit `d1bbf89` with the reviewed October 24 mock executor integration explicitly
relocked, plus the reviewed pilot-25 adapter hash and model revision.
`scripts/check_amd_api_smoke_plan.py` checks integrity without network access,
credentials, GPU imports or filesystem writes:

```sh
python3 scripts/check_amd_api_smoke_plan.py
```

Success explicitly returns `prepared_only` and `execution_authorized: false`.
It checks the private adapter if locally present; an absent private artifact is
reported separately and is never execution readiness. Missing source files,
source drift, changed serving identity, symlinks, duplicate JSON keys, altered
limits or authorization claims fail closed. It cannot approve spending or relock
files. This is an integrity aid within trusted Git review, not a digital signature.
Future API changes invalidate this snapshot: rerun local
tests/smoke and explicitly review a refreshed plan before any execution.

## Proposed bounded workload

One new allocation, one GPU, no replacement allocations. Two admitted images and
at most two physical render calls, using the same apple prompt and seed 7 twice.
No base/adapter comparison, additional checkpoint, gesture evaluation, training
or promotion. Keep `configs/serving.json` unchanged: FLUX.2-klein-base-4B revision
`a3b4f4849157f664bdbc776fd7453c2783562f4d`, pilot step 25, 512px, 50 steps,
guidance 4.0, with the existing style suffix.

Propose a 30-minute allocation lifetime **including** startup/download/work and
five minutes reserved for cleanup; stop work no later than minute 25. These are
draft upper bounds, not approved capacity. `approved_allowance_usd` stays null.
A user-approved separate dollar ceiling and current provider price check are
required before creating a reservation. Do not infer credit balance, capacity or
current pricing from the old comparison receipt. If setup cannot fit the bound,
abort and delete; do not extend deadlines or allocate a replacement automatically.

## Unresolved runtime and executor gates

- The successful comparison reported `torch 2.10.0+rocm7.2.0.gitb6ee5fde`, HIP
  `7.2.26015`, and AMD Instinct MI300X VF. That is historical evidence from
  `runs/amd-comparison-v1/report.json`, not a reproducible runtime lock. The old
  provider image ID and `rocm` container name are not immutable OCI digests.
- `pyproject.toml`/`uv.lock` are locked here as source evidence, **not an AMD
  installation recipe**: Linux torch packages select the NVIDIA `cu128` index.
  Do not install this GPU extra unchanged on AMD. Before execution, pin a ROCm
  container digest and hash-locked AMD-compatible dependencies (including API,
  Pillow, diffusers/transformers/peft and transitive dependencies), record an SBOM
  or package manifest, and test the same application source in that runtime.
- A dedicated live AMD executor is still required. The new
  [mock-only executor](mock-smoke-executor.md) connects queue, render budget and
  publication with stable logical call IDs, and is included in this source lock.
  It rejects real-renderer injection and supplies no provisioning path.
  `smoke_http.py` intentionally supports
  only MockRenderer and 45/60-second local bounds; do not merely switch its
  renderer to FLUX. The old NVIDIA/Vast launchers are not interchangeable either.
  Use `durable_api.create_app` with `FluxRenderer` only after explicit ROCm/HIP,
  one-visible-GPU and BF16 preflight. PyTorch's `cuda` namespace alone does not
  establish that the installed build is ROCm.
- Enforce the two-physical-render budget outside the queue. The queue can retry
  expired leases up to three times, so a two-image quota is not a compute limit.
  Persist the render budget before starting each call; uncertain/interrupted
  execution consumes a call. Abort ambiguous in-flight work, without replay.
  The guard and mock-only executor are now implemented, tested offline and locked;
  see [render-budget.md](render-budget.md). Live runtime/deadline/cleanup integration
  is still required; the live executor gate remains open. Default API/worker unchanged.
- New campaign ownership/state, pre-allocation reservation, independent cloud
  expiry/reaper and exact-resource deletion verification must be implemented and
  failure-tested before provisioning. Never modify/reset `amd-comparison-v1`,
  reuse its workflow entry point, or rely on the Mac, Codex, an API lease or model
  unload to stop billing. No provider credentials belong in the API process.

## Proposed acceptance sequence after all gates are cleared

1. Verify the plan/source/model/adapter and AMD runtime locks. Create a fresh
   smoke-only database and temporary per-user tokens. Bind only loopback with
   access through a private SSH tunnel; firewall denies a public API listener.
   Confirm independent expiry and export destination before loading the model.
2. With rendering disabled, reject unauthenticated submission (401), non-admin
   metrics (403), and admit exactly one seed-7 image (202). Verify queued state
   and active-job deletion conflict (409). Restart the API on the same disk,
   enable one local worker, and finish that queued job once.
3. Download and decode PNG/WebP; verify 512px RGBA, transparency, metadata,
   request ID, seed, model/adapter identity and checksums. Another user must see
   404 for status/export and empty history. Record cold-load/generation timing
   and peak VRAM; no performance or quality claim follows from this small smoke.
4. Admit the second identical request once. Compare outputs in the same pinned
   runtime and record hashes; mismatch requires investigation, not extra paid
   samples. Do not demand byte identity against mock images or other hardware.
   Save feedback and check daily/global quota rejection without admitting work.
5. Restart only after all rendering is terminal. Verify completed metadata,
   history, usage and export bytes survive the restart. Delete one terminal job;
   its exports disappear but quota usage remains two. This tests same-disk
   process durability, not availability after GPU deletion or disk loss.
6. Export a sanitized receipt and surviving artifacts to a **new private** release
   or storage prefix, download independently and verify hashes. Do not copy
   secrets, auth tokens, raw environment dumps or a production database. Record
   failed checks as failures; the absence of a receipt is not success.
7. Delete the exact owned GPU and reconcile provider absence. Always prioritize
   cleanup on failure/deadline, even if export fails. Preserve a pending-cleanup
   reservation and escalate if deletion cannot be verified; never replace the
   GPU. Final acceptance requires both checksum-verified results and deletion
   receipts. A local process exit is insufficient evidence of stopped billing.

The optional HTTP idempotency contract is now tested locally and included in the
refreshed source lock; see `docs/durable-api.md`. Use distinct persisted keys for
the two intended images. This proposal still permits **zero automatic POST
retries**: idempotency does not increase its physical render budget or authorize
execution. After an ambiguous submit, reconcile its original job and abort if
identity cannot be resolved. X-Request-ID remains correlation only. Any later
executor retry-policy change needs an explicitly reviewed plan and failure tests.

Offline checker tests and the local HTTP smoke can proceed without a budget.
Public hosting, recurring CPU/storage costs, HTTPS/DNS and tester invitations
remain separate user decisions. This smoke is not the always-on private alpha.
