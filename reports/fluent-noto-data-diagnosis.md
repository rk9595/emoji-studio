# Fluent/Noto metadata and schedule diagnosis

Audited frozen `data/training/fluent-noto-v1/manifest.json` (SHA-256
`04ceea8fbe448f4ae0441938f6f06f8c1c5b9a010bf61f7e1641dae7f3a3846e`) and
`artifacts/trainers/fluent-noto-v1/schedule.json`. The trainer bundle schedule
contains 2,624 draws, 2,621 unique assets and maximum repetition two. All 128
Noto assets receive one draw. Do not confuse the inherited dataset sampling.json
with this coverage trainer's schedule.

| Concept | Train assets | Validation assets | Scheduled draws |
|---|---:|---:|---:|
| Crossed fingers | 0 | 6 | 0 |
| Grinning face with sweat | 0 | 1 | 0 |
| Pleading face | 0 | 1 | 0 |
| Folded hands | 6 | 0 | 6 |
| High five | 0 | 0 | 0 |
| Pinky promise | 0 | 0 | 0 |

Counts use exact Fluent concept names. Inspection of the Noto subset's Unicode
names found no crossed-fingers, pleading-face or sweat-face target additions.
It includes handshake, man/woman holding hands and fingers-splayed examples.
Three of 128 Noto captions begin with `u+` codes rather than semantic names.
The other captions are lowercased glyph names plus a style suffix. Fluent
captions generally name the concept and skin tone without describing contact
or finger relationships. Captions remain marked not individually visually reviewed.

This is a metadata/schedule audit, not a visual annotation pass. No evidence here
establishes malformed training anatomy or proves the cause of expression
regression. The human six-finger note applies to a whole review group; it does
not identify a specific A/B/C image. Do not attribute it to step-656 without
further inspection. Held-out target failures measure generalization; moving
those images into training would invalidate that interpretation.

## Concrete correction plan

1. Create a separate caption proposal keyed by immutable asset ID and image hash.
   Resolve the three code-only Noto captions by visually inspecting their glyphs.
   Review expression and hand examples with the images visible before adding
   anatomical/contact descriptions. Preserve frozen datasets and captions.
2. Audit semantic overlap between Noto additions and Fluent validation concepts;
   the exporter checks identity collisions, which does not establish semantic
   separation across styles. Record overlap before choosing evaluation claims.
3. Keep existing validation families held out. If training target gestures is
   desired, define a new versioned task/split with independently held-out examples
   and explicit source provenance. Require real high-five/pinky contact examples.
4. Before paid execution, propose one controlled change, with pinned inputs,
   early checkpoint retention, expression regression checks and gesture criteria.
   Do not infer that extra steps or another arbitrary Noto subset will fix quality.

Diagnosis milestone complete. Next ready work is the offline caption/semantic
overlap proposal. No allocation, dataset mutation or model promotion occurred.
Serving stays pilot-25; aggregate prior training/evaluation estimate stays $1.0613.
