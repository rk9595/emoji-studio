# Coverage sampler prototype — October 23, 2026

This is an offline prototype of the coverage-only proposal in
[collection-v3-proposal.md](collection-v3-proposal.md). It does not select an
experiment, approve captions, integrate with a trainer or authorize training.
The existing collection-v2 export and 2,000-draw schedule remain unchanged.

## Implemented contract

`emoji_studio.coverage_preflight` uses only the Python standard library. It reads
a bounded manifest whose exact byte SHA-256 must match an explicit caller-supplied
pin. It validates unique IDs, inclusion/split types, concept/tone/caption metadata,
family IDs and recorded export/source/pixel hashes. Only included training rows
are eligible. Shared family IDs or recorded exact hashes across included training
and validation rows block the proposal. No image files are opened or modified.

Policy `concept-tone-round-robin-sha256-v1` groups by exact concept/tone labels,
hash-shuffles bucket order and assets independently for each pass, then visits
each nonempty bucket in turn. Empty buckets leave the rotation. Every eligible
asset appears once before any appears twice; any prefix has per-asset counts
differing by at most one. Small buckets change ordering without gaining extra
copies. Manifest probabilities and group weights are deliberately unused; this
prototype has no weighting override or subset-selection option.

Hash inputs use sorted-key, compact ASCII JSON plus a trailing newline over
`[policy, seed, pass_index, kind, value]`. SHA-256 sort ties break by the original
label/ID. This avoids relying on interpreter PRNG behavior. Row reordering leaves
draw order unchanged, but changes the exact manifest pin and schedule identity.
Changing the algorithm requires a new policy version and reviewed evidence.

The full report includes seed, manifest hash, ordered asset IDs, canonical schedule
hash, per-asset counts (including zeros), concept/tone bucket counts, omitted IDs,
repeat extrema, coverage and optimizer-step arithmetic. It has no timestamps in
its deterministic payload. Required buckets use exact, case-sensitive labels.
Absent or excluded/validation-only required buckets block. Even an explicitly
partial diagnostic blocks if a required bucket receives no draw.

Default full-coverage claims require at least the entire eligible pool.
`--partial-diagnostic` permits an honestly labeled partial schedule, not an
approved smaller subset. An approved subset would need a separately frozen and
reviewed manifest. The prototype never drops, pads or automatically adds draws.
Draws must divide exactly by batch size × accumulation; arithmetic assumes one
process/device and complete accumulation windows. The report gives the minimum
aligned full-coverage budget as information only.

Optional `--required-caption-status` checks recorded status strings. It cannot
establish who reviewed an image, caption truth, source/license approval, or
whether family IDs/near-duplicate grouping are correct. Those remain separate
review gates. No gesture dataset or annotation status is changed.

## Reproduce and inspect

Run from the repository root; stdout contains the complete proposal and schedule:

```sh
PYTHONPATH=src python3 -m emoji_studio.coverage_preflight \
  data/training/collection-v2/manifest.json \
  --manifest-sha256 72b1f6ca95c26ad5663e9c8f25a019036b08e407248251abd504c99bc29d90ba \
  --seed 29 --draws 2496 --batch-size 1 --accumulation 4
```

Use `--draws 2000` to reproduce the refused full-coverage claim, or explicitly
add `--partial-diagnostic` for a 2,000-draw diagnostic. Add repeated
`--require-bucket 'Folded hands' Default` arguments for exact target buckets.
Exit codes: 0 means prototype checks passed, 1 means blocked, 2 means invalid
input. All reports retain `training_authorized: false`. The CLI writes only stdout;
it offers no output path, data mutation, cloud call or training entry point.

`verify_schedule(schedule, manifest_bytes, **explicit_preflight_options)`
rebuilds the proposal and rejects altered metadata, order, non-training IDs or
unauthorized repetitions. Do not derive the requested budget or manifest pin
from an untrusted supplied schedule.

## Retained-manifest evidence

[Receipt](../reports/collection-coverage-prototype.json) pins code/test hashes,
protected input hashes, checks and results. The
[proposed ordered schedule](../reports/collection-coverage-prototype-schedule.json)
is canonical JSON; its file hash equals the receipt's schedule hash. It is not
installed in the training dataset.

| Scenario | Result |
| --- | --- |
| 2,000 draws claiming full coverage | Blocked: fewer than 2,493 assets |
| 2,000 draws explicitly partial | 2,000 unique assets, 493 omitted, no repeats |
| 2,496 draws proposed full pass | 2,493 unique assets, three repeat draws, 624 optimizer steps |
| Gesture metadata gate | Blocked: missing training buckets and required visual-review status |

The full-pass proposal includes all six folded-hands training assets. Crossed
fingers stays validation-only; high-five and pinky promise remain unsupported.
The 624-step arithmetic is a proposal, not an increase to the existing 500-step
configuration or permission to spend more. The before/after manifest, historical
sampling and serving hashes match; recorded metadata hashes were checked for
leakage, but asset bytes were not re-read.

Validation: 16 new tests cover coverage prefixes, deterministic rebuilds across
interpreters, bucket interleaving, partial reporting, held-out/excluded rows,
exact-hash/family leakage, missing/undrawn buckets, recorded review status,
arithmetic, malformed inputs, read-only CLI behavior and tampered schedules.
Together with local collection regressions and the unchanged AMD draft checker,
32 tests and 38 subtests passed. No GPU was used.
