# AMD runtime proposal — October 24, 2026

Status: **prepared-only metadata and conditional overlay lock**. No image layers
were pulled, no container built, no GPU packages installed on the Mac, no GPU
allocated and no spending authorized. The existing AMD execution plan still
marks its runtime unresolved. This proposal does not change that gate.

## Immutable base candidate

[AMD's versioned ROCm 7.2 documentation](https://rocm.docs.amd.com/projects/install-on-linux/en/docs-7.2.0/install/3rd-party/pytorch-install.html)
lists the Ubuntu 24.04 / Python 3.12 / PyTorch 2.10 image; it labels PyTorch 2.10
as preview. The selected tag is
`rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.10.0`.
[Docker Hub's image record](https://hub.docker.com/layers/rocm/pytorch/rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.10.0/images/sha256-bcb2efa1d43f66cc59fa45a1975d621a50b2b06d21a2abdfa2ba821ab32763e4)
provides the manifest identity. Direct registry inspection verified these bytes:

```text
docker.io/rocm/pytorch@sha256:bcb2efa1d43f66cc59fa45a1975d621a50b2b06d21a2abdfa2ba821ab32763e4
config: sha256:701f42ee1596bdb69351147d27496b45613016b1072024229064eb756524906c
platform: linux/amd64
```

The archived public manifest/config in `reports/amd-runtime-registry.json` are
verified by their original byte hashes, descriptor linkage, config size and
architecture. Eight compressed layers total 12,763,439,494 bytes (about 12.76 GB,
11.89 GiB). Registry metadata was fetched; layers were not. This size matters for
future build disk and startup-transfer planning within the proposed 30 minutes.

The historical comparison receipt proves a working Torch
`2.10.0+rocm7.2.0.gitb6ee5fde`, HIP `7.2.26015`, MI300X VF environment. It does
**not** identify its container digest or full Python inventory. The candidate
shares the advertised version family; identical historical runtime is unproven.
The pinned config's build history is evidence of its recipe, not an installed
package inventory or execution of that recipe in this session.

## Application overlay

`configs/amd-overlay.in` pins 11 direct dependencies from the retained project
`uv.lock`, including the API, Pillow, diffusers/transformers/peft, Accelerate,
safetensors and the test HTTP client. `configs/amd-overlay-linux-py312.txt`
contains 45 exactly pinned application packages and distribution SHA-256 hashes.
It resolves for Python 3.12 on x86_64 manylinux 2.39, with candidates restricted
to uploads before October 24. A second offline compile from cached metadata
produced byte-identical output. No environment was installed or synchronized.

The exclusion file deliberately omits base-provided Torch, torchvision,
torchaudio, Triton and Apex **and their dependency traversal**. Consequently this
is an application overlay, not proof of the entire combined dependency closure.
The candidate image must supply those packages; its exact inventory, ABI and
compatibility with this overlay remain unverified. No CUDA/NVIDIA packages are
allowed in the overlay. The project's existing Linux GPU extra/uv.lock remains
unchanged and must not be used to install the AMD environment.

Compile with the recorded `uv 0.9.18` tool ([uv locking documentation](https://docs.astral.sh/uv/pip/compile/)):

```sh
uv pip compile configs/amd-overlay.in \
  --excludes configs/amd-base-provided.in \
  --python-version 3.12 --python-platform x86_64-manylinux_2_39 \
  --generate-hashes --only-binary :all: --no-python-downloads --no-sources \
  --default-index https://pypi.org/simple --exclude-newer 2026-10-24 \
  --no-header --no-annotate
```

That command prints a candidate for review; do not overwrite the locked file
automatically. uv's hashes can cover multiple distributions of a pinned package;
future installation must still require compatible binary wheels and hashes.
Do not `sync` this partial overlay over the base environment or let a resolver
replace its GPU stack. A future controlled Linux image build should install only
the explicitly locked overlay with dependency auto-installation disabled, then
verify the *complete* environment. This session does not provide a launch/build
entry point or install command on the Mac.

## Checks and remaining gates

```sh
python3 scripts/check_amd_runtime_proposal.py
```

The default checker is offline/read-only. It verifies the four input hashes,
archived registry digest linkage, strict overlay pins/hashes, protected exclusions,
target platform and prepared-only authority fields. `--registry` explicitly reads
only the fixed public tag/manifest/config, rejects tag drift, and emits a fresh
receipt to stdout. Anonymous read tokens are kept in memory and never archived.
Neither mode pulls layers, executes build history, installs packages or relocks
changed inputs. Ten new tests plus the existing AMD plan checks passed: 22 tests,
30 subtests. Passing these checks proves integrity of the proposal, not HIP/GPU
availability or that the overlay will install successfully.

Before clearing the runtime gate:

1. Build in an appropriate Linux/amd64 environment with sufficient disk and an
   explicit resource arrangement. Record full base and post-overlay package
   inventories, verify hashes, and run dependency/ABI/import checks. Reconcile
   excluded dependencies rather than weakening checks or silently replacing Torch.
2. Record the derived image's immutable digest and inventory/SBOM. Run the locked
   application tests and mock HTTP/executor checks inside that exact image.
3. Confirm provider host-driver/runtime compatibility and, only under separately
   bounded GPU authority, verify HIP, exactly one visible MI300X-class GPU, BF16,
   model/adapter identity and the guarded two-image smoke. Prior receipts do not
   prove the new image works on an available provider host.

Independent expiry/deletion, private export verification and the new dollar
allowance remain separate gates. `configs/amd-runtime-proposal.json` retains
`runtime_validated: false`, `derived_image_digest: null` and false execution
authority. It is not yet substituted into the 23-file execution source lock.
