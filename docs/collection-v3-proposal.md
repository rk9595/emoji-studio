# Collection v3 proposal — October 16, 2026

Status: **draft; no data migration, new image creation, annotation approval or
training authorization**. Preserve collection-v2, its 2,000-draw schedule, all
existing adapters and the reviewed pilot-25 serving configuration.

## Evidence and scope

The retained [coverage audit](../reports/collection-coverage-audit.md) found only
954 of 2,493 training images sampled. Folded hands had six available training
images but zero draws; crossed fingers was deliberately validation-only;
high-five and pinky promise were absent. Six flags received 235 draws, versus
231 across 1,504 People & Body images. Captions were metadata-checked, not
individually visually verified.

The [AI diagnostic](../reports/amd-comparison-v1.md) found all 84 gesture outputs
failed across base/pilot/collection conditions. These facts motivate a targeted
experiment; they do not prove a causal mechanism or justify longer training with
the old schedule. Separate two future questions:

1. **Coverage-only control:** same eligible v2 training pool and existing holdout,
   but a coverage-guaranteed schedule. Does better exposure help supported concepts?
2. **Gesture-focused dataset:** newly reviewed relationship-rich examples, with a
   new split and fresh evaluation families. Does explicit supervision improve the
   targeted gestures without damaging simple objects, faces and tone consistency?

These are separate ablations, not an invitation to run both automatically.

## Annotation record and acceptance

Proposed records carry source asset hash, source/license provenance, family ID,
split, concept, requested/reference tone label, caption version, review status,
reviewer identity/type and review timestamp. Add structured observations for hand
count, visible digit identities, contact points, occlusions, accessories and
background. Use `unknown` for visually ambiguous details rather than inferring
them from the concept name. AI suggestions remain suggestions until reviewed.

Captions must describe what the image actually shows. For crossed fingers,
verify which two fingers cross and which are folded. For a high-five, distinguish
two participants' palms meeting from one person's folded/praying hands. For pinky
promise, verify that only little fingers link, with the other fingers naturally
curled. These are review criteria, **not approved captions for unseen images**.
Skin-tone labels describe the asset/prompt variant, not an inferred ethnicity.

Reject extra/fused digits, incorrect contact relationships, ambiguous target
gestures, unsupported provenance and near-duplicate leakage. Keep rejections and
reasons in the manifest; do not silently repair or train on them. Visually review
all target gesture assets before inclusion, including old assets proposed for reuse.

## Split and evaluation integrity

Do not move the six v2 crossed-finger validation images into v2 training. Freeze
their IDs/hashes and keep reporting the historical challenge separately. If a
new v3 dataset teaches crossed fingers, it changes the generalization question:
use new source families/poses in its held-out evaluation and label v2 prompt
comparisons as development diagnostics, not untouched tests.

Group tone variants, mirrored variants and source-derived edits by family before
splitting. Check exact hashes and perceptual near-duplicates across splits; manual
review remains necessary for candidate duplicates. Freeze evaluation manifests
before training. Keep repeated seeds and tone variants visible in reporting;
do not count correlated variants as independent concepts.

## Proposed sampler policy

Replace equal-probability group sampling with a deterministic, precomputed
without-replacement coverage pass over eligible training assets. For each pass,
shuffle within concept/tone buckets and interleave buckets; each eligible asset
appears once before it appears twice. Weighting may change order, not silently
multiply tiny groups. Persist seed, ordered asset IDs and manifest checksum.

For the existing 2,493-image training pool, a 2,000-draw budget cannot cover every
asset. The preflight must say this explicitly and refuse a claimed full-coverage
run. Either budget at least one full pass (training-step arithmetic included), or
declare and freeze a smaller reviewed subset before sampling. Do not silently
increase training steps or spend to satisfy coverage.

For a targeted subset, every accepted target concept/tone bucket must receive
at least one draw per pass, with per-asset repeat counts differing by at most one.
Report excluded/missing buckets as unsupported. Additional emphasis requires an
explicit versioned weighting policy with per-asset repetition caps and a full
coverage receipt; it is not hidden inside the sampler implementation.

## Local preflight before any paid run

- Verify source and caption versions, train/validation family disjointness,
  preserved v2 hashes and required visual-review statuses.
- Rebuild the schedule twice from the same seed; require byte-identical output.
- Reject non-training IDs, missing target buckets, unauthorized repeats or a
  draw budget incompatible with its coverage claim.
- Report unique coverage, draws per concept/tone/asset, maximum repeat count,
  omitted assets, draw budget and optimizer-step arithmetic.
- Freeze the evaluation rubric, baseline adapter hashes and checkpoint cadence.
  Score anatomy/contact accuracy separately from style; label AI and human review.
- Produce an experiment manifest and proposed cost/time bounds. Stop before
  allocation until the data decision and bounded compute allowance are approved.

The pure local sampler/preflight prototype is now implemented over synthetic
fixtures and read-only manifests; see [coverage-sampler-prototype.md](coverage-sampler-prototype.md).
It leaves source images, captions, splits and the historical schedule unchanged.
Its 2,496-draw full-pass example is a proposed arithmetic check, not an approved
experiment, annotation decision, training integration or increase in compute.
