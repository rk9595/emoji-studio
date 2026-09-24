# Single-GPU service load test

Status: **complete; every locked check passed and all cloud instances are destroyed**.

On September 23, 2026, the selected step-25 LoRA was served through the real Emoji Studio API on one Vast A100 SXM4 with 40 GB VRAM. The service remained private behind SSH. The remote runner generated its bearer key in memory, rejected an unauthenticated request with HTTP 401, and did not include credentials in the recovered archive.

## Result

| Measurement | Result |
| --- | ---: |
| Smoke jobs | 2/2 succeeded |
| Load-test jobs | 16/16 succeeded |
| Concurrency | 4 |
| Load-test wall time | 142.689 seconds |
| Throughput | 6.728 images/minute |
| Latency p50 | 35.603 seconds |
| Latency p95 | 35.929 seconds |
| Maximum latency | 36.049 seconds |
| Load-test generation time | 136.324 seconds |
| Peak sampled GPU memory | 16,983 MiB |
| Peak sampled utilization | 100% |
| Maximum queued jobs | 3 |
| Failed jobs | 0 |

The first smoke request took 54.230 seconds end to end because it included model download and cold loading; its GPU generation phase took 8.864 seconds. The identical hot request took 8.539 seconds end to end and 8.248 seconds in generation. Both seeded runs produced byte-identical PNG and WebP files.

All 18 outputs were recorded by service metrics. Aggregate GPU generation time was 153.436 seconds and the generation-only cost estimate was $0.02920 at the rented hourly rate. The load test used a single worker, so concurrency exercised authentication, persistence, queueing, polling, and backpressure rather than parallel GPU inference. At concurrency 4, one request ran while the other three queued, explaining the roughly 36-second steady-state latency.

The preserved smoke output is a readable orange rocket emoji with a genuinely transparent background. Both PNG and lossless WebP exports are 512 × 512 RGBA assets with alpha extrema 0–255. After ten idle seconds, the real model unloaded and `/healthz` reported `model_loaded: false`.

## Integrity

- Selected adapter SHA-256: `2c7b15de79e9ac0bf59488068c9ec0f3444dec44899005499de87c2b28e93076`.
- Serving configuration SHA-256: `51ace9667447113a22cfadea1ca606539ad264086421e7e7c241561c7401534f`.
- Test report SHA-256: `c00b25034cf47675aaede0721141a4572e251a27a2d6fa5358ee82f9f4d86526`.
- Final evidence archive SHA-256: `83af16ead6259a034c11ef48d81139920f9031ec6acc1f626f4688f4463258e1`.
- Deterministic PNG SHA-256: `0c7a3d45d0eedf464fe1cfe98449825a8c01be25fd93edfe9dfb87c46dfa3976`.
- Deterministic WebP SHA-256: `aa728632bca43b174081d2f79e80a0a55714084aff89512bb2a9ae17d498136c`.

Primary evidence is in `runs/service-gpu-test/report.json`, `metrics.prom`, `gpu-samples.json`, and the two preserved smoke render pairs. The validated remote archive is `artifacts/vast-service-load-test/emoji-service-94875d4256/final-results.tar.gz`.

## Cost and recovery work

The successful A100 allocation cost $0.10251 by the provider's immediate credit reading. Earlier attempts exposed two infrastructure faults before inference: unstable uploads on one RTX PRO 5000 host and an instance that did not receive the provider-account SSH key. The lifecycle now uses a per-instance ephemeral SSH key, resumable SFTP transfer, archive checksum verification, exact offer selection, a wall-clock guard, a credit guard, and ownership-checked destruction.

Across every serving-test attempt, the latest reconciled account credit changed from $5.31604 to $4.74579: **$0.57025 observed total**, subject to further delayed billing reconciliation. This remained below the user-authorized $1 cap. A final independent provider query returned zero active instances. Adding this milestone to the prior approximate $3.26 project total gives a latest whole-project estimate of roughly **$3.83**.

## Product implication

The current one-worker service is adequate for an alpha and has ample VRAM headroom on a 40 GB GPU. It is not yet a production deployment: a four-request burst produces roughly 36-second p95 latency because inference is intentionally serialized. The next useful work is a persistent deployment with infrastructure scale-to-zero, retention limits, and real-user instrumentation. Batching or a second worker should be introduced only after real traffic shows that this measured queueing behavior is unacceptable.
