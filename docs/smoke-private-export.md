# Private smoke export — offline prototype

`src/emoji_studio/smoke_export.py` prepares sanitized image pairs, uploads them
through an abstract private store, and verifies fresh downloads against a retained
manifest fingerprint. `tests/test_smoke_export.py` uses in-memory storage and real
MockRenderer exports. No remote store, release, credentials or network client was
created or used. This component is complete as an offline prototype; the live
private-export gate and active 23-file execution lock remain unchanged.

## Contents and identity

An `ExportBinding` contains a fresh allocation nonce, plan SHA-256 and serving
configuration SHA-256. The only allowed destination is the private
`rk9595/emoji-studio-ops` repository with a new
`amd-api-smoke-v1/<allocation nonce>` namespace. The consumed comparison namespace
is never accepted. This is an abstract object namespace; a future release adapter
must map it explicitly to a new private release, not reuse the comparison release.

`prepare_export` accepts one or two surviving image pairs at original indices 0/1,
each containing exactly PNG and WebP bytes. This supports exporting the remaining
job after the smoke's terminal-job deletion check. Each input is bounded to 4 MiB,
single-frame 512×512 RGBA with transparency. Inputs are decoded and re-encoded from
pixels into new images, discarding EXIF, XMP, ICC, textual metadata and trailing
bytes. Sanitized files may have different byte hashes from their source files;
the manifest records both hashes and the sanitized byte length. Pixel content is
not redacted, and no equality claim between the PNG and WebP pixels is made.

Manifest fields are fixed: schema version, smoke campaign, binding, declared
renderer (`MockRenderer` or `FluxRenderer`), fixed seed 7, and artifact descriptors.
It does not copy arbitrary job dictionaries, prompts, request headers, owner IDs,
raw errors, environment data, databases, model files or filesystem paths. Artifact
names are generated (`image-0.png`, etc.), with no caller-supplied paths or URLs.
Strict schema validation rejects unknown/duplicate fields, invalid names, missing
pairs, altered bindings and noncanonical JSON. Manifest size is capped at 16 KiB.

Binding hashes and renderer labels are trusted caller assertions, not proof that
a model ran or that a plan was approved. The future controller must supply them
from validated execution evidence. Source bytes are not uploaded, so source hashes
record provenance rather than enabling reconstruction of stripped metadata.

## Upload, recovery and verification

1. `export_ticket(bundle)` validates every artifact and the manifest without any
   storage calls. Persist this ticket in trusted durable storage outside the GPU
   **before upload**. It contains only the binding and manifest fingerprint.
2. `upload_export(bundle, writer)` checks destination identity/privacy and invokes
   `put_if_absent` once per artifact, with the manifest last. There is no automatic
   retry, overwrite, destination creation or deletion. Existing identical bytes
   may be accepted by the adapter; conflicting bytes must fail atomically.
3. Use a separate authenticated download client for `verify_export(ticket, reader)`.
   Verification requires neither the local bundle nor the original images. It
   downloads the manifest, checks its pinned hash, canonical schema and binding,
   then downloads every expected object and checks its exact length and hash.
4. Only successful independent downloads return `export_verified`. Upload
   acknowledgments are insufficient. Lost upload acknowledgments can be reconciled
   from the retained ticket, without re-uploading. Partial uploads, missing objects,
   changed manifests, corrupted/truncated/oversized bytes and read failures remain
   unverified. A trusted controller must persist the verification receipt separately.

The convenience function `transfer_and_verify` rejects the same object as writer
and reader. Separate Python objects alone do not establish network independence:
the live adapter must perform fresh authenticated reads without upload caches.
Privacy/scope is rechecked before each operation and after verification. A privacy
change detected during the transfer aborts it; client checks cannot prevent an
administrator from changing repository visibility between or after those checks.
Live storage therefore also needs enforced private access and scoped credentials.

Each storage call receives a ten-second timeout; reads also receive explicit byte
limits. The adapter must enforce connection/read/total deadlines and streaming
limits, reject redirects/public URLs, and suppress transport-level write retries.
The prototype cannot enforce timeouts against a hung or nonconforming adapter.
Raw adapter exception messages are replaced with fixed error codes.

`export_verified` is deliberately separate from resource deletion and full smoke
acceptance: its receipt contains `cleanup_verified: false` and
`smoke_accepted: false`. Export failure never changes the cleanup ledger. The
independent expiry service must continue while an export hangs, fails or loses
its worker; do not place that service behind a sequential export call or disable
it when upload succeeds. No second render/allocation is allowed to repair export.

## Validation and remaining work

Tests cover real mock-worker image output, both image-count cases, metadata
removal, strict manifests, byte limits, private scopes, scope changes, separate
readers, conflicts, partial uploads, missing/corrupt downloads, lost acknowledgments,
ticket-only recovery and independent cleanup after export failure. No live privacy,
durability or network timeout claim follows from these mocks.

Next runtime validation needs a Linux/amd64 build environment with capacity for
the 12.76 GB compressed base plus extracted/build layers. The checked local Docker
server is Linux/arm64; the Mac filesystem reported about 20 GiB available. No base
layers were pulled. Select a suitable existing builder/access arrangement before
attempting the runtime build, inventory, dependency/ABI checks and in-image tests.

After that choice, remaining work includes the actual private storage adapter,
durable external ticket/receipt storage, reservation/controller integration and
independent cloud cleanup deployment. The smoke still needs a separately bounded
GPU allowance and a reviewed source-lock update before any live execution.
Persistent hosting remains a separate budget/access decision.
