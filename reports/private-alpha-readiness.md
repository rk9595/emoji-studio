# Private-alpha readiness

## Outcome

The Emoji Studio control plane is ready for a bounded local or private deployment. It now enforces per-user authentication, isolation, daily quotas, request-rate limits, a persistent 100-image trial ceiling, seven-day output retention, immediate user deletion, feedback capture, and admin-only metrics. The browser shows both the user's remaining daily quota and the remaining alpha-wide allowance.

The GPU deployment definition is also ready and connected to the same API through the `vast-serverless` renderer. It is limited to one worker and 40 GB or more of GPU memory, filters offers above $0.70/hour, scales to zero workers after ten idle minutes, and has a thirty-minute unattended endpoint teardown for the first live smoke.

## Live deployment status

A private manual-test session launched successfully on September 24, 2026. The authenticated web application is forwarded over SSH to `http://127.0.0.1:8000`; it is not exposed on a public port. Its first real request generated a verified 512×512 transparent RGBA sticker in 9.814 seconds after the cold model download and used 16,727,727,104 bytes of peak allocated VRAM.

- GPU: RTX PRO 5000
- Hourly rate: $0.694444
- Daily images remaining after the smoke: 19
- Alpha-wide images remaining: 99
- Automatic destruction: September 25, 2026 at 00:05:44 IST, or $3 shared observed spend, whichever comes first

The managed serverless path remains blocked by Vast's 5 MB deployment-code storage limit because the selected adapter is approximately 32 MB. No adapter was published to bypass that limit. The temporary ordinary-instance session preserves the same one-GPU and spending bounds and is appropriate for this owner's manual test, but it is not the final public-alpha architecture.

Stop the temporary session early with:

```sh
uv run python scripts/vast_alpha_session.py stop
```

## Alpha measurement

Run the summary after testers have used the service:

```sh
uv run python scripts/summarize_alpha.py
```

It writes `reports/private-alpha.json` and `reports/private-alpha.md`. The decision checks use the locked thresholds in `configs/alpha.json`: at least 70% positive feedback among rated jobs, no more than 5% failed terminal jobs, no more than $0.03 measured warm generation cost per successful image, and no breach of the 100-image cap. Feedback coverage is reported separately and must be judged before treating those checks as conclusive.

## Remaining production boundary

Vast serverless supplies the GPU execution layer, not the durable public product. A real external alpha still needs a small always-available HTTPS host for this FastAPI/UI control plane and durable storage for its job ledger, feedback, and artifacts. The present filesystem store is intentionally single-process. Selecting or creating those external services requires the owner's hosting/domain account choice; no such account or resource was inferred or created.
