# Retained collection training coverage — October 13

The saved sampling schedule exposes a concrete limitation of the 500-step pilot:
it never drew a crossed-fingers or folded-hands example, and it contains no
high-five or pinky-promise training assets. This does not establish the cause of
any generated-image defect, but it means the run did not directly train those
target gestures.

The audit reads the immutable collection-v2 manifest and the actual 2,000-draw
schedule. It does not change the dataset, captions, split, or sampler.

| Concept | Training images | Validation images | Actual training draws |
| --- | ---: | ---: | ---: |
| Crossed fingers | 0 | 6 | 0 |
| Folded hands | 6 | 0 | 0 |
| High five | 0 | 0 | 0 |
| Pinky promise | 0 | 0 | 0 |
| Bicycle | 1 | 0 | 1 |

The deliberately held-out crossed-fingers prompts test generalization. They are
not evidence of a failed attempt to learn crossed fingers from explicit training
examples. Folded hands was available in the training pool but absent from the
actual sampled draws. The bicycle received only one draw.

The group sampler also gives six flag images 235 draws, while 1,504 People & Body
images receive 231 draws. That is roughly 255 times more mean exposure per flag
image. Only 203 People & Body images were sampled at all. Overall, the run drew
954 distinct images out of 2,493 training images (38.3%).

All 3,144 included captions are marked metadata-checked, with detailed visual
content not individually reviewed. The gesture captions name the concept and
tone, but do not describe finger relationships or palm contact.

## Implication for the next training experiment

First finish the retained-checkpoint comparison. For any later gesture-focused
experiment, create a new versioned dataset with visually verified gesture and
tone examples, explicit anatomy/contact captions, and a schedule that guarantees
the intended examples are actually seen. Reduce extreme repetition from tiny
groups. Preserve collection-v2 and use fresh held-out examples to measure any
targeted training improvement.

This is a metadata and sampling audit, not a visual annotation pass, model-quality
score, or authorization to launch another training job.

Evidence: [machine-readable audit](collection-coverage-audit.json).
Reproduce with `python3 scripts/audit_collection_coverage.py`.
