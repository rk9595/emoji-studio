# Conservative cross-source split proposal

Completed a 128-row triage in `configs/noto-semantic-crosswalk-v1.json`, bound
to the frozen source manifest and individual image hashes. Reproduce with
`python3 scripts/build_noto_crosswalk.py`. No source dataset has been edited.

- 17 exact normalized names overlap Fluent validation.
- Six candidate aliases: waving black flag → Black flag; older woman → Old
  woman; cat face with tears of joy → Cat with tears of joy; clock face eight
  oclock → Eight oclock; person with pouting face → Person pouting; squared
  CJK ideograph-7a7a → Japanese vacancy button.
- 105 remain unresolved. Absence of an exact name match is not evidence of
  semantic independence. Alias assignments are AI name-based triage, not a
  completed visual or authoritative Unicode mapping review.

Proposed policy: retain all 2,493 Fluent training and 651 validation examples
in their existing splits. Exclude the 23 exact/candidate matches from Noto
training eligibility; quarantine the remaining 105 until semantic review.
At this stage no Noto example is cleared for a new training run. Do not relabel
excluded Noto examples as new validation evidence or alter historical results.
The three descriptive caption proposals are attached to their crosswalk rows,
but caption repair alone does not clear an example for training.

Next ready offline task: review the six aliases using paired Noto/Fluent images
and resolve the 105 rows against all Fluent concepts/families, recording a
reason and evidence for every decision. Produce a versioned allowlist only
after the review. The proposed split is not an execution authorization.
No new GPU spending; serving remains pilot-25.
