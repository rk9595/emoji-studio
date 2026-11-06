# Human retrospective review of campaign e

The user supplied `noto-review-scores.json` on November 6, 2026. The export
covers all 24 prompt/seed groups and all 72 shuffled images, with valid scores
from 0 (major failure) to 2 (requested details met). Labels were decoded only
after validating coverage. This was a retrospective comparison across separate
runs, so it is useful diagnostic evidence, not a controlled or sealed test.

| Prompt category | Base | Pilot 25 | Step 656 |
|---|---:|---:|---:|
| Held-out expressions (4 each) | 1.25 | 2.00 | 0.50 |
| Held-out tone-specific gestures (10 each) | 0.90 | 0.90 | 0.90 |
| Held-out person (2 each) | 1.50 | 1.50 | 1.00 |
| Held-out object (2 each) | 2.00 | 2.00 | 2.00 |
| Trained geometry control (2 each) | 2.00 | 2.00 | 2.00 |
| Novel composition challenge (4 each) | 1.25 | 1.25 | 1.00 |

Means aggregate the user's 0/1/2 criterion scores; each category has few,
correlated observations. The reviewer noted that `dev-collection-03-seed-0`
looks like it has six fingers. Expressions are the clearest regression: step-656
averages 0.50 versus pilot-25's 2.00 on four images. Step-656 has no advantage on
the object or trained bicycle controls and is slightly lower on person and
novel-composition prompts.

Decision: do not promote step-656. Keep serving on reviewed pilot step-25. The
scores support a targeted data/caption and gesture-structure investigation
before another bounded experiment. A new GPU run needs a fresh immutable plan
and authorization; consumed campaigns remain closed.

The export is preserved at `runs/noto-retrospective-review-v2/noto-review-scores.json`.
