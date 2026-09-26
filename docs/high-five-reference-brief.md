# High-five variation brief — approved direction, not a training dataset

September 26, 2026. The user approved candidate `qwen-hi5-004` as both a high-five
gesture and the target golden-yellow, rounded 3D style. This is a reference selection,
not approval of unseen fingers, every small-size criterion, or model reliability.

Reference: [original PNG](images/high-five-teacher/qwen-hi5-004.png), seed 404.
SHA-256: `c51db19bc58a3a77f77cb8b699b5fc4bb4f9705a8f410aa394ec60a7d30aae4f`.
Human feedback is saved locally against that exact hash in
`runs/high-five-teacher-pilot-v1/human-review-template.json`.

## Keep and vary

Keep golden-yellow material, smooth rounded forms, gentle shading, two distinct
hands, broad palm contact and the user-approved celebratory reading. Do not drift
back to photographic skin texture. Keep a plain background and omit lettering.

Vary camera angle and the approach of the arms, not just color or seed. Favor
shorter visible forearms and clear margins without changing the gesture the user
approved. Seek views that expose enough of each hand to assess anatomy; do not
invent extra fingers merely to make every digit visible through an occluding hand.

## Proposed next audition: eight candidates

Four intended composition families, two fixed seeds each. These are design targets,
not verified distinct output poses or accepted training/validation examples.

| Family | Composition target | Seeds |
| --- | --- | --- |
| A | Front three-quarter contact, short arms rising from unequal lower positions; thumbs readable on the outer edges. | 1101, 1102 |
| B | Elevated camera showing more of the palm-contact boundary, with one hand slightly higher and fingers naturally offset. | 1201, 1202 |
| C | Low oblique view of the strike, arms spread more widely, with both wrist contours distinct. | 1301, 1302 |
| D | Hands meeting diagonally above center, one arm approaching more horizontally; keep the contact readable without motion decorations. | 1401, 1402 |

Keep the Qwen model revision and sampling settings fixed initially so the new
variable is composition. Candidate 004 is a visual review reference, **not an image
conditioning input** to the existing text-only sampler. If text-only variants do
not retain the intended direction, design a separate reference-conditioned test;
do not silently describe prompting as image-conditioned control.

The eight-candidate trial is now implemented separately in
`configs/high-five-golden-audition.json` and `scripts/sample_golden_teacher.py`.
Its plan is `6820fb673cc9a80a91b1d1883d932923bdc3dbec5a9bfbe68c8beeb3740958fa`;
outputs belong under `runs/high-five-golden-audition-v1/`. The original four-image
sampler and plan remain unchanged. The shared launcher, snapshot worker and review
gallery accept `--trial golden`, with trial-bound authorization and archive checks.

The new prompts explicitly specify golden clay-like hands and exclude photographic
skin texture. This changes styling language from the first trial as well as pose;
it is not a controlled estimate of either change's individual effect. Within this
audition the model and sampling settings remain fixed across all four prompt pairs.

```sh
uv run python scripts/sample_golden_teacher.py plan
# Only after receiving a fresh compute approval and binding its local record:
uv run python scripts/vast_teacher_pilot.py --trial golden --authorization <path>
# After outputs exist:
uv run python scripts/sample_golden_teacher.py verify
uv run python scripts/build_teacher_review.py --trial golden
```

Proposed new limit: $1.25 total, <=$0.80/hour, one GPU, 45 elapsed minutes. The
golden launcher rejects larger limits, reserves $0.15 and three minutes for cleanup,
and refuses a new rental if all eight images already exist. Marketplace availability
was checked read-only: qualifying offers existed below $0.80/hour, zero instances
were active, and credit was $5.5904540856. These observations are not a price guarantee.
Fresh spending approval remains pending; no authorization record or rental has
been created for this trial. The prior rental authorizations are consumed.

Local tests cover eight-job sampling through a mock pipeline, untouched historical
plan hashes, prompt leakage, reference binding, trial-specific budget caps, archive
roundtrips, wrong-trial snapshot rejection and preservation of human answers.
All 119 tests and Ruff passed; the original four-image trial still verifies.
The real upload archive was inspected: 28 entries, about 194 KB, with no old trial
images, human review answers, credentials or alpha-user data.

## Review and training boundary

Review each candidate separately for gesture, anatomy, style and 32/64-pixel
readability. Preserve uncertainty where fingers are hidden. User approval of 004
does not propagate to its variants. Record actual pose families after seeing outputs;
two seeds or a mirrored image do not establish independent composition diversity.

If any future editing run uses 004 as a structural reference, conservatively keep
its derivatives in the same source lineage and split. Maintain pose-disjoint
validation; do not turn closely related variants into a claimed held-out set.

This is a golden-style audition, not the full training collection. The existing
training gate still requires 24 reviewed training positives and eight validation
positives, with pose diversity and light/medium/dark coverage. Golden-only variants
cannot satisfy that gate. Do not silently remove those requirements because the
user selected a golden product style; a later dataset plan must address the broader
evaluation scope explicitly.

No new GPU allocation, generation or training is authorized or launched by this brief.
