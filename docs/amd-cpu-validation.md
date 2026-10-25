# AMD CPU validation completed — October 25, 2026

The [bounded public CPU build](https://github.com/rk9595/emoji-studio/actions/runs/40166592399)
passed at source `acef6db19b00ddcb07dbff290bfde2ff825c80ed`.
The job took 523 seconds; its build step took 511 seconds. No GPU was allocated,
model loaded, paid runner selected or serving configuration changed.

`reports/amd-cpu-validation.json` retains the complete sanitized package inventories,
validation receipt, source identity and SHA-256 of the downloaded Actions log.
The report was extracted from the exact completed run, not inferred from its green
status: six test counts, CPU audit marker, import receipt and image digest were
checked. The local inventory validator also rechecked all 45 overlay pins and
protected base versions against the retained receipt.

| Check | Result |
| --- | --- |
| Base / post-overlay inventory | 42 / 78 distributions retained |
| Application overlay | All 45 pins match |
| Apex, Torch, torchaudio, torchvision, Triton | All five base versions unchanged |
| Combined dependency check | No broken requirements |
| Native CPU imports/operators | Passed; BF16 CPU arithmetic and torchvision NMS |
| Six in-image unittest modules | 103 tests passed |
| Real loopback HTTP / guarded mock executor | Both passed |
| GPU execution / model loading | Not performed |

The imported Torch reports `2.10.0+rocm7.2.0.gitb6ee5fde` and HIP `7.2.26015`.
Its distribution metadata includes the additional `lw` build segment; the report
preserves both rather than treating them as identical strings. Matching the
historical version family is not proof of identical historical image bytes.

The observed local image configuration digest is
`sha256:2c3ad8f4db4dd8170be4e2f52da7782313a6da137a29cd03ec1cc3858bb81ab9`.
It is **not a published OCI manifest digest**. The image was ephemeral and is no
longer retained after runner teardown. A later rebuild can produce a different
configuration digest; it must pass its own checks and record its own identity.
Do not set the active smoke runtime to this local ID or claim GPU compatibility.

## Next: retain one private immutable image

`configs/amd-image-retention-proposal.json` recommends
`ghcr.io/rk9595/emoji-studio-amd-runtime` with private visibility and one new
version. It is prepared only; publication remains false. No package was created
and no additional build was dispatched during this receipt review.

GitHub currently documents container registry image storage and bandwidth as
[free](https://docs.github.com/en/billing/concepts/product-billing/github-packages).
It also documents that [new container packages default to private](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry)
and supports workflow-token authentication. This makes private GHCR the recommended
retention path under the zero-paid-resource constraint. Recheck that policy before
execution; do not assume it is permanently free or confuse it with Actions artifact
storage allowances.

The next ready task is to implement and failure-test the dedicated retention
workflow and manifest/privacy checks before resolving the publication gate. It
must reuse the reviewed public-only context, use a unique non-overwriting tag and
repeat CPU validation before pushing. No `latest`, public visibility change,
existing-version deletion, automatic retry or paid fallback is allowed.

After pushing, verify the authenticated remote manifest bytes/digest, platform and
new image configuration digest. Check private visibility and deny anonymous access
to that known-existing manifest. A separate fresh job must pull by digest and repeat
the audit/mock checks; a local cached image or push acknowledgment is insufficient.
Use scoped short-lived workflow credentials, never log or embed them in image layers.
Any future GPU's private pull access is a separate explicit controller integration.

Registry retention does not authorize a GPU smoke or always-on hosting. The active
23-file execution plan stays prepared-only, and `runtime_validated` remains false
until separately authorized HIP/device/model validation and the remaining controller,
cleanup, export and spending gates are met. The completed comparison stays consumed.
