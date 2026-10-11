# AMD ROCm validation

Status: completed on 2026-10-11.

Emoji Studio's pinned FLUX.2 Klein inference and LoRA training paths work on a single AMD Instinct MI300X under ROCm. The validation covered model loading, the selected serving adapter, matched base-versus-adapted generation, optimizer updates, checkpoint saving, checkpoint resume, final adapter reload, and a 24-image serving benchmark.

## Environment

| Component | Validated value |
| --- | --- |
| Cloud | AMD Developer Cloud, `atl1` |
| Instance | `gpu-mi300x1-192gb-devcloud` |
| GPU | AMD Instinct MI300X VF, 205,822,885,888 bytes VRAM |
| PyTorch | `2.10.0+rocm7.2.0.gitb6ee5fde` |
| HIP | `7.2.26015` |
| Diffusers | `0.40.0` |
| Transformers | `5.17.0` |
| Model | `black-forest-labs/FLUX.2-klein-base-4B` |
| Model revision | `a3b4f4849157f664bdbc776fd7453c2783562f4d` |
| Serving adapter SHA-256 | `2c7b15de79e9ac0bf59488068c9ec0f3444dec44899005499de87c2b28e93076` |

PyTorch retains the `torch.cuda` API name on ROCm. The reports therefore use calls such as `torch.cuda.is_available()` while recording `backend: rocm`, `hip: 7.2.26015`, and `cuda: null`.

## Results

### Inference smoke

The pinned model loaded in 20.7912 seconds. The cold base render took 36.8493 seconds; after warm-up and adapter loading, the matched adapted render took 3.9684 seconds. Both 512 px, 50-step images were valid and visually reviewable.

Local evidence: `runs/amd-inference-smoke-v1/`.

### Training and resume smoke

The bounded smoke run completed two optimizer steps in 102.3631 seconds. It saved checkpoint 1, restored optimizer, scheduler, sampler, and random state, completed the resumed step, saved checkpoint 2, exported the final LoRA, and reloaded it for inference.

- First step: 43.4375 seconds, 17,495 MiB peak observed VRAM.
- Resumed step: 35.5229 seconds, 17,474 MiB peak observed VRAM.
- Final adapter: 120 finite tensors; SHA-256 `fc8fcd1acff17bb6129aecfa0cfdee3e091548ecbe1ad9744b2ec34c265eb70f`.
- The final adapter differs from the first-step adapter, confirming the resumed optimizer step changed the weights.

Local evidence: `runs/amd-training-smoke-v1/`.

### Matched serving benchmark

The locked development benchmark generated 12 base and 12 adapted images at 512 px and 50 steps in 100.6856 seconds. Excluding the first base warm-up render, base generation averaged 3.5469 seconds per image; adapted generation averaged 3.9992 seconds per image. Peak allocated memory was 17,066,286,080 bytes.

Local evidence: `runs/amd-serving-benchmark-v1/`, including `evaluation-review.html` for side-by-side inspection.

## Conclusion

The current Emoji Studio serving adapter and bounded training workflow are compatible with the tested MI300X/ROCm stack. This validates infrastructure and numerical execution, including checkpoint resume; it is not a claim that a new full training run improves model quality. The selected step-25 serving adapter remains unchanged pending product-level visual review or a deliberately scoped quality-training experiment.
