# LoRA training smoke: 2026-09-20

The bounded technical smoke completed successfully on one NVIDIA RTX PRO 5000 Blackwell. This proves the pinned Linux/CUDA environment, full trainer import, forward/backward path, checkpoint save, checkpoint reload/resume, final LoRA save and adapter inference path. It does **not** establish adaptation quality: only two optimizer steps were run.

## Measured result

- The first optimizer step took 1.2104 seconds and the resumed step took 1.1646 seconds. Each optimizer step used four gradient-accumulation microbatches.
- Peak GPU memory observed by one-second `nvidia-smi` sampling was 16,002 MiB during each training invocation. Sampling can miss a shorter peak.
- The whole remote workload took 256.61 seconds, including dependency/model setup, two separately invoked trainer processes and adapter inference.
- Checkpoint 1 was explicitly reloaded: model, optimizer, scheduler, dataloader sampler and random states all reported successful restoration before step 2.
- The final adapter contains 120 finite tensors across the expected `to_k`, `to_q`, `to_v`, `to_out` and `to_qkv_mlp_proj` target categories. Its SHA-256 is `25b4c831d894b2e1c322f21411315270c249b405014162833cd110e67939657f`.
- The final adapter differs from the step-1 adapter and is durable at `runs/lora-pilot-smoke/pytorch_lora_weights.safetensors`.
- Exact-adapter inference completed in 10.20 seconds of generation time at four steps. The remote receipt bound the adapter hash above to image hash `4809d1fb3be3116a8ef52a95107dd6342447d1a2fc0d4c02ff90f85991e4c3fe`. The rendered PNG itself was not recovered, so no visual-quality claim is made.

## Recovery and cost

The first allocation stopped before training because the uploaded test suite referenced an omitted launcher file. The second allocation completed the workload. A post-completion full archive transfer timed out, but the retained atomic snapshot contained the complete final adapter and logs; the completed JSON report was recovered from the beginning of the partial transfer and its adapter hash matches the local file. A final recovery allocation was destroyed without starting the workload when its host refused SSH authentication.

All cleanup calls succeeded. A final independent Vast API query returned zero instances. Credit changed from $7.0892051088 to $6.7476526811 across all training-smoke attempts: **$0.3415524277 observed**, subject to billing lag. This remained below the authorized $3 total and every offer remained below $0.70/hour.

## What is and is not durable

Durable locally: final step-2 adapter, checkpoint-1 adapter/optimizer/scheduler/random state, completed remote report, full training log, TensorBoard records and cleanup/cost evidence. Checkpoint 2's full optimizer state and the inference PNG are not local. The final adapter is sufficient for a future before/after evaluation; resuming exactly from optimizer step 2 would require rerunning this smoke or accepting a fresh optimizer state.

The proposed 100-step style pilot was not authorized or run. Its next gate is a new budget plus a fixed before/after prompt-and-seed evaluation plan. Two measured steps indicate ample VRAM headroom on this GPU class, but do not predict useful quality improvement.
