# 100-step LoRA quality pilot: completed

## Outcome

The adapter learned a visible softer, simplified Fluent-like material language on the four held-out object concepts. All 12 adapted images remain recognizable, and no cross-concept or sample collapse is apparent. This is **evidence of style learning**, not a production-ready win: the two unseen-bicycle samples have worse mechanical geometry than their paired base images, and some held-out details are simplified away.

The review was performed by OpenAI Codex with the base/adapted labels visible and the four validation references available. It is not blinded or independent human evaluation. The set contains only six development prompts at two seeds.

## Technical result

- One RTX PRO 5000 Blackwell, CUDA 12.8, pinned dependency environment.
- 100 optimizer steps completed in 108.61 seconds; the complete training process took 312.44 seconds including loading and cached latents.
- Sampled peak training memory: 15,982 MiB.
- Final adapter: `runs/lora-quality-pilot/pytorch_lora_weights.safetensors`, SHA-256 `d28456bd713d44836e7a5b323708c5ccf39f967386a6e5a1ccf43b65e4c6c63b`.
- All 120 adapter tensors are finite and cover the expected target categories. The final tensors equal the retained step-100 checkpoint tensors.
- Compact adapters from steps 25, 50, 75 and 100 are local under `runs/lora-quality-pilot/adapters/`.
- Evaluation produced all 24 checksum-verified images: 12 base and 12 adapted, using identical prompts, seeds, 512-pixel resolution, 50 steps and guidance 4.
- Evaluation generation averaged 14.48 seconds per image. Full remote workload: 689.31 seconds. Provider lifecycle including setup, transfers and teardown: 1,197.97 seconds.

## Visual review

| Concept | Result | Evidence |
| --- | --- | --- |
| Backpack, held out | Positive style shift with detail tradeoff | Both seeds preserve the pink backpack, yellow zipper bar, handle and pocket. Adapted materials and shadows are closer to the simple reference, but zipper/side detail is reduced. |
| Books, held out | Mixed | Exactly three green, pink and blue books remain. Adaptation smooths the forms but suppresses visible page edges, particularly versus base seed 0. |
| Umbrella, held out | Small positive style shift | Purple canopy, brown hooked handle and silhouette remain correct in both seeds. The change is mostly simpler highlights and panels. |
| Alarm clock, held out | Positive style shift | Metallic realism shifts toward the reference's pink/yellow toy-plastic language while both samples remain readable clocks. |
| Bicycle, unseen object | Regression | Both remain recognizable red bicycles with two wheels, but adapted crank, pedal, fork or frame geometry is less coherent than base. |
| Raised hand, excluded domain | No material semantic regression | Both remain single palm-facing hands with five distinct fingers; the adapted material is slightly softer. |

At small display sizes, the simplified adapted silhouettes should generally remain clear, but the book/page distinction and bicycle mechanics lose useful structure. No claim is made for interaction prompts such as high-five or pinky promise; those were outside this object-style training set.

## Cost and cleanup

The replacement run was authorized for at most $0.90, $0.70/hour and 45 minutes. Credit changed by $0.3151572184 at cleanup and later reconciled to $0.3473632394. Including the failed pre-training attempt, the latest combined observed change is $0.4086538781, subject to further billing lag. The instance was destroyed and an independent provider query returned zero instances.

The validated final archive is `artifacts/vast-quality-pilot/emoji-quality-c12dd79192/final-results.tar.gz`. Local reports and images are under `runs/lora-quality-pilot/`; no remote disk is relied upon.

## Decision

Keep the result as a successful pipeline and style-learning pilot. Do not promote the step-100 adapter as a universal default. Before paying for more training, use blinded human review to decide whether the visible style gain outweighs the bicycle/detail regressions. If not, the most focused next experiment is a matched evaluation of the already-retained step-25/50/75 adapters rather than additional training.
