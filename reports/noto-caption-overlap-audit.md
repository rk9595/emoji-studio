# Caption proposals and validation overlap

AI visually inspected the three code-only images. Proposed descriptions in
`configs/noto-caption-proposals-v1.json` are bound to asset IDs and image hashes.
They are descriptive proposals, not official Unicode names or applied edits.
The local Unicode database is version 15.0.0; the exporter falls back to a code
when a name is unavailable. Preserve the frozen export.

Exact normalized caption names identify 17 Noto training concepts also present
in Fluent validation: fountain, foggy, cherry blossom, pineapple, jack-o-lantern,
desert island, hotel, whale, tropical fish, kissing face with smiling eyes,
upside-down face, water closet, bellhop bell, potato, dumpling, owl and ladder.
Reproduce with `python3 scripts/audit_noto_overlap.py` for asset identities.
Normalization removes punctuation and spaces and lowercases text. This is a
lower bound: aliases such as Unicode names versus display labels may add more.

Therefore the combined export's validation set is not fully concept-held-out.
Identity collision checks in the exporter cannot ensure semantic separation.
This does not prove contamination of the specific 12 review prompts and does
not establish the cause of expression regression. Do not describe all validation
results as unseen-concept generalization.

Next offline step: create an explicit semantic crosswalk for all 128 Noto rows,
mark exact matches, candidate aliases and unresolved rows, and prepare a new
split proposal excluding validation concepts from training. Preserve all existing
files and evaluation labels. Caption and split changes should be staged as a
separate version before any new experiment. No GPU or promotion authorized here.
