# Private AMD runtime retention workflow — October 25, 2026

The original dedicated workflow was prepared and reviewed after **72 tests/112 subtests**
passed. It is at `.github/workflows/amd-runtime-retain.yml`, with an identical
review template in `ops/workflows/amd-runtime-retain.yml`.
`scripts/verify_ghcr_retention.py` provides bounded read-only checks; its default
mode reads the local proposal only. No private package success is claimed here.

The user's delegation to continue private-alpha implementation and choose the
builder covers one private runtime artifact within existing zero-paid-resource
bounds. Preparation is now complete, so `configs/amd-image-retention-proposal.json`
recorded that limited publication authority. The gate is now closed after the
failed attempt described below. This is not GPU, public publication,
paid hosting or further-version authority. A repository variable
`AMD_RETENTION_APPROVED_SOURCE` must additionally match the exact workflow commit.
Reruns, different source commits and a stale pricing-check date fail before network
calls. Future changes require a fresh deliberate review, not an automatic retry.

GitHub's [current billing policy](https://docs.github.com/en/billing/concepts/product-billing/github-packages)
still lists container registry storage/bandwidth as free, checked October 25.
The workflow uses standard runners in the existing public repository. It uploads
no Actions artifacts/cache and has no paid-runner fallback. The destination lookup
with the connected CLI returned 404; that is a new-package candidate, not proof
that the workflow token can publish. The actual job checks with its own token.

## Publication and verification sequence

1. Require the publication flag, matching approved source, first run attempt and
   current pricing-check date. Preflight only the fixed
   `rk9595/emoji-studio-amd-runtime` namespace. Existing private packages must have
   zero versions; public, wrong-owner/name/type, existing-version and error responses
   stop the attempt. A 404 may also hide insufficient access; it does not bypass
   provider permissions or prove that publication will work.
2. Use native x86-64, at least 60 GiB free, the previously reviewed 38-file public
   context and base digest. Repeat full CPU validation during the build. Nothing
   private, including credentials/model weights, is copied into the build context.
3. Recheck preflight immediately before one registry copy. Use a tag containing
   the complete source SHA and Actions run ID, no `latest`, no all-tags operation,
   no overwrite request and no existing-version deletion. Skopeo is supplied by
   the signed Ubuntu distribution and its version is logged; it is runner tooling,
   not an application dependency installed into the image. Its supported
   [`--retry-times 0` and `--digestfile`](https://raw.githubusercontent.com/containers/skopeo/main/docs/skopeo-copy.1.md)
   control command retries and retain the resulting manifest identity. Build/copy
   deadlines are 30/10 minutes inside a 45-minute job.
4. Read authenticated remote manifest bytes by the copy's digest. Verify SHA-256,
   digest response header, single-image media type, descriptor sizes, config hash,
   Linux/amd64 platform and rootfs/layer counts. Reject indexes, foreign URL layers,
   more than 32 layers or over 20 GiB compressed content. The config must equal the
   **new** local image ID, not the earlier discarded CPU build's ID.
5. Require private GitHub package metadata with exactly one version. Check the
   anonymous token flow separately. A public registry also initially challenges
   clients, so a bare unauthenticated 401 is insufficient: if an anonymous pull
   token is granted, the known manifest must then return 401/403. A 200, redirect,
   404 or transient error in that probe fails verification. Recheck private metadata.
6. A second standard runner, with packages-read permission only, verifies the
   remote metadata again, refuses a pre-cached target, and pulls the exact manifest
   digest. Compare its config ID/platform and rerun the complete CPU audit with
   network disabled. Only baked audit outputs are removed in the disposable
   container's writable layer; the registry image and base inventory are untouched.
   The fresh job has a 30-minute cap (20-minute pull, five-minute audit).
7. Recheck privacy and print `RETENTION_RECEIPT` only after the fresh audit passes.
   The receipt explicitly leaves GPU validation false. The supervisor accepts the
   exact retention workflow/run/head identity and avoids model polling while active.

New packages [default to private](https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry).
The workflow never changes visibility. One workflow concurrency group serializes
cooperating publishers. Registry tags do not provide atomic create-if-absent here:
the fixed namespace must remain exclusive to this workflow; source/run uniqueness
and repeated metadata checks are not protection against a separate concurrent writer.
Private visibility checks describe the observed state, not a guarantee against a
later administrator change. Any unexpected visibility or version count stops work.

## Credentials, failures and limits

Only short-lived workflow tokens are used: write permission for publication,
read permission for fresh verification. Tokens go to CLI stdin/temporary private
auth files and never into Docker build arguments or layers. Auth files are removed
on step exit. Login/copy/pull diagnostics stay in disposable private runner files;
they are not echoed into public logs because transport errors can include signed
URLs. The verifier prints only fixed error codes and sanitized digest receipts.

HTTP reads use fixed GitHub/GHCR origins, verified HTTPS, no environment proxies,
no automatic retries, bounded bodies and deadlines. Manifest/token redirects fail.
Config blobs alone may follow up to two HTTPS CDN redirects on a fixed allowlist;
credentials are stripped before following them. Unknown CDN hosts fail closed.

A copy timeout or lost acknowledgment leaves publication uncertain. Do not rerun
the job or push another version: inspect the original unique tag and package using
read-only reconciliation. The verifier marks remote metadata verification separately
from a fresh pull, and cannot itself claim independent image execution. Failed fresh
verification leaves a retained but unaccepted version; no automatic deletion occurs.

The [registry protocol](https://distribution.github.io/distribution/spec/api/)
and [GitHub package API](https://docs.github.com/en/rest/packages/packages)
inform these checks. Local tests cover digest/config/platform corruption, public
anonymous access, malformed/duplicate JSON, size bounds, scope/version failures,
privacy changes, CDN credential stripping, transport failures, approval/rerun gates
and exact supervisor receipt selection. Live GHCR permissions, copy performance
and fresh-pull behavior remain to be verified by the actual bounded attempt.

## Failed attempt and read-only reconciliation

Run [40170595914](https://github.com/rk9595/emoji-studio/actions/runs/40170595914)
passed the full CPU build and all 103 in-image tests, then failed in the publication
step (exit 1 after 9m30s). Fresh verification was skipped. The private transport
logs were not retained, so neither a timeout nor a particular registry error is
established. `reports/amd-retention-failure.json` preserves the audit, original tag,
new local config identity and log hash. No published digest or successful retention
is claimed.

Local authenticated package/tag reads returned 404, but the CLI lacks read:packages;
this is not proof of absence. A five-minute standard CPU workflow,
`amd-runtime-reconcile.yml`, uses packages-read only to inspect the original unique
tag and, if found, verify its digest/config/platform/privacy. It never builds,
pushes, pulls image layers, deletes or changes visibility. A missing tag remains
`publication_unresolved`; even a found/verified manifest does not prove a fresh pull.
Its code passed 79 tests/120 subtests together with the existing checks. The 38-file
builder lock is unchanged. The publication flag and approved-source repository
variable are closed; no automatic retry or second version is authorized.


Reconciliation run [40173475187](https://github.com/rk9595/emoji-studio/actions/runs/40173475187)
completed successfully, but its receipt is `publication_unresolved`: both package
and original-tag reads returned 404 with the repository packages-read token.
`reports/amd-retention-reconciliation.json` retains this result and log hash.
This does not verify absence or retention. Queue is `waiting_user` for the owner to
check package existence and, if present, private visibility/repository Actions read
access. Publication gates stay closed. No automatic retry, deletion or second
version follows from this result; fresh pull and GPU validation remain unverified.


October 29 owner-side observation: the signed-in `rk9595` Packages page displayed
“Your Packages” with “Get started with GitHub Packages” and no package rows.
`reports/amd-retention-owner-check.json` records the read-only observation. This
satisfies the requested owner check, so offline work no longer waits on the user.
It is not an atomic absence guarantee or a diagnosis of the original failure.
Publication remains disabled pending deliberate diagnostics/revised-attempt review;
no retry, permission change or additional version was performed.
