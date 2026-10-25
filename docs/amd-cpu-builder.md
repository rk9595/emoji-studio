# AMD runtime CPU builder — October 25, 2026

Decision: use one **standard public GitHub-hosted Ubuntu 24.04 x86-64 runner**
for CPU runtime validation. The user delegated the builder choice. There is no
paid fallback, GPU allocation, registry publication, model download or change to
the consumed comparison. The previous request for a user-supplied host is resolved
for this CPU experiment.

[GitHub's runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
states that standard runners are free for public repositories, lists x64 Ubuntu
with four CPUs/16 GB RAM, and documents 14 GB SSD storage. The repository was
checked as public. The documented disk allowance alone is insufficient planning
evidence, so a read-only capacity job ran first. Its [retained receipt](https://github.com/rk9595/emoji-studio/actions/runs/40166118846)
reports native x86-64, four CPUs and **91,737,362,432 free bytes (~85.4 GiB)** on
the filesystem containing Docker. No files/tools were deleted or layers pulled.
Future runners may differ: the actual build repeats a minimum-60-GiB free-space
check and stops before pulling if it fails. That threshold is a conservative
operational guard, not a measured peak footprint or guarantee of sufficient space.

[GitHub billing documentation](https://docs.github.com/en/billing/concepts/product-billing/github-actions)
distinguishes free standard public-repository runner usage from storage charges.
These workflows use no upload-artifact/cache action, registry push, larger runner
or private-repository execution. Small receipts remain in ordinary workflow logs;
the image is discarded with the disposable VM. No ongoing host is created.

## Reviewed recipe

`configs/amd-builder-proposal.json` separately hashes the 38 public application
inputs and two recipe files. The active smoke execution lock remains unchanged.
`scripts/prepare_amd_build_context.py` validates every input before creating a new
context directory; it refuses changed inputs, symlinks and an existing destination.
Only those reviewed bytes are copied. No broad repository COPY, private adapters,
training images, credentials, Git metadata or local runtime databases are included.
The staging script never invokes Docker or installs anything.

`ops/runtime/Dockerfile` uses the already-pinned ROCm image digest and its Python
3.12 virtual environment. It records base package names/versions, installs the
45-package application overlay with binary wheels, required distribution hashes,
no dependency auto-installation and no pip cache, then validates the combined
environment. These installation constraints follow [pip's secure-install guidance](https://pip.pypa.io/en/stable/topics/secure-installs/).
The CUDA-oriented project GPU extra/uv.lock is never an installation input.

`ops/runtime/audit_runtime.py` records the installed inventory and requires all five
proposed base GPU packages to exist. Their versions and other GPU-prefixed base
packages must remain unchanged; every application pin must match the overlay.
Missing expected base packages require reviewing the inventory, not automatically
installing replacement Torch/Triton/Apex. NVIDIA/CUDA distributions fail the audit.
The full environment must pass [`pip check`](https://pip.pypa.io/en/stable/cli/pip_check/).
The audit then checks imports, HIP build identity, CPU BF16 matrix arithmetic and
torchvision's native CPU operator. It requires zero visible GPUs and loads no model.

Six unittest modules exercise the render budget, mock executor, cleanup, private
export and existing plan/runtime integrity. Real loopback HTTP and mock executor
smokes also run inside the image. This validation stage uses Docker's disabled
network mode; the base pull and hashed wheel installation are the only network
stages. Base/post-overlay inventories are printed as bounded package metadata so
they remain available even if Docker discards a failed intermediate layer.

The manual-only `.github/workflows/amd-runtime-cpu-build.yml` restricts execution
to this public repository and a standard runner, pins checkout by commit, disables
persisted checkout credentials, grants only contents-read permission and supplies
no secrets to the build. One build command has a 35-minute timeout; the entire
job has a 45-minute limit. There are no automatic retries or schedules.

## What success and failure mean

A successful run establishes CPU package/import/mock-test compatibility for the
recorded build, not GPU/runtime readiness for serving. The reported local Docker
image ID is a **configuration digest**, not a published OCI manifest digest.
`configs/amd-runtime-proposal.json` therefore retains `runtime_validated: false`
and a null derived image digest; spending/serving gates remain closed.

If any gate fails, retain the first failure and inventories, review the cause and
make a deliberate source/lock change before another attempt. Do not weaken checks,
replace the GPU stack automatically or upgrade to a paid runner. A failure of this
free CPU build does not consume or create a GPU allocation.

After CPU validation, plan an explicit immutable image retention/publication
arrangement and integrate the controller, private export and independent cleanup.
Only a separately bounded GPU authorization can cover HIP/device/model execution.
This experiment does not create the always-on private alpha.

## Continuation

The local supervisor can now inspect a queued CPU Actions run by exact repository,
run ID, source commit and workflow name. While it is queued/running it skips model
turns; completion/failure wakes review. The historical comparison release remains
the legacy fallback only when no CPU run ID is queued. This adds receipt-based
continuation without model polling, subject to the existing Mac/app-server limits.

Local verification: 52 tests/64 subtests passed across builder, CPU receipt,
automation and existing plan/runtime checks; Ruff passed. The six in-image test
modules (103 tests) also passed from the isolated staged context using the existing
Mac test dependencies, verifying context completeness, not ROCm compatibility.
No local base pull/build or GPU-package installation was performed.
