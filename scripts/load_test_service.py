"""Submit a bounded load test to an already-running Emoji Studio service."""

import argparse
import concurrent.futures
import json
import os
import statistics
import time

from emoji_studio.client import EmojiStudioClient

PROMPTS = [
    "a cheerful red panda waving",
    "a blue bicycle with a flower basket",
    "a cozy stack of three books",
    "a smiling avocado holding a tiny flag",
    "a yellow submarine with round windows",
    "a sleepy moon wearing a nightcap",
    "a green watering can with one daisy",
    "a friendly robot giving a thumbs up",
]


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * fraction))]


def run_one(client, index, timeout):
    started = time.monotonic()
    job = client.generate(PROMPTS[index % len(PROMPTS)], seed=10_000 + index)
    result = client.wait(job["id"], poll_seconds=0.25, timeout=timeout)
    return {
        "job_id": job["id"],
        "seconds": time.monotonic() - started,
        "generation_seconds": result["results"][0]["metrics"]["generation_seconds"],
        "estimated_cost_dollars": result["results"][0]["metrics"]["estimated_cost_dollars"],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--api-key", default=os.environ.get("EMOJI_STUDIO_API_KEY"))
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    if not args.api_key:
        parser.error("--api-key or EMOJI_STUDIO_API_KEY is required")
    if not 1 <= args.requests <= 100:
        parser.error("--requests must be between 1 and 100")
    if not 1 <= args.concurrency <= 16:
        parser.error("--concurrency must be between 1 and 16")

    client = EmojiStudioClient(args.url, args.api_key, timeout=30)
    started = time.monotonic()
    rows = []
    failures = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = {
            pool.submit(run_one, client, index, args.timeout): index
            for index in range(args.requests)
        }
        for future in concurrent.futures.as_completed(futures):
            try:
                rows.append(future.result())
            except Exception as error:
                failures.append(
                    {"index": futures[future], "error": f"{type(error).__name__}: {error}"}
                )
    wall = time.monotonic() - started
    latencies = [row["seconds"] for row in rows]
    report = {
        "requests": args.requests,
        "concurrency": args.concurrency,
        "completed": len(rows),
        "failed": len(failures),
        "wall_seconds": round(wall, 4),
        "throughput_images_per_minute": round(len(rows) * 60 / wall, 4),
        "latency_seconds": {
            "p50": round(statistics.median(latencies), 4) if latencies else None,
            "p95": round(percentile(latencies, 0.95), 4) if latencies else None,
            "max": round(max(latencies), 4) if latencies else None,
        },
        "generation_seconds_sum": round(sum(row["generation_seconds"] for row in rows), 4),
        "estimated_cost_dollars": round(sum(row["estimated_cost_dollars"] for row in rows), 8),
        "failures": failures,
    }
    print(json.dumps(report, indent=2))
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
