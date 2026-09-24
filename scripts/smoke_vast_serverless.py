"""Deploy the bounded serverless worker and verify one deterministic render."""

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

import aiohttp.connector
from aiohttp.resolver import ThreadedResolver
from PIL import Image

# aiodns can time out on otherwise healthy macOS DNS. The system resolver is stable here
# and changes only local name resolution, not deployment behavior or TLS verification.
aiohttp.connector.DefaultResolver = ThreadedResolver

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from vast_smoke import credit  # noqa: E402

from deployment.vast_flux import app, render  # noqa: E402
from emoji_studio.common import now, write_json  # noqa: E402
from emoji_studio.service import make_sticker  # noqa: E402

MINIMUM_SERVERLESS_CREDIT = 5.0


async def run(output):
    started = time.monotonic()
    await app.async_ensure_ready()
    ready_seconds = time.monotonic() - started
    result = await render("a cheerful red panda waving", 4242)
    raw = output / "raw.png"
    raw.write_bytes(result.pop("png"))
    with Image.open(raw) as image:
        sticker = make_sticker(image)
    sticker_path = output / "sticker.png"
    sticker.save(sticker_path, format="PNG", optimize=True)
    report = {
        "schema_version": 1,
        "status": "completed",
        "created_at": now(),
        "deployment": "emoji-studio-flux",
        "tag": "alpha-v1",
        "max_workers": 1,
        "scale_to_zero_seconds": 600,
        "automatic_teardown_seconds": 1800,
        "ready_seconds": round(ready_seconds, 4),
        "result": result,
        "raw_png_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "sticker_png_sha256": hashlib.sha256(sticker_path.read_bytes()).hexdigest(),
        "sticker_mode": sticker.mode,
        "sticker_size": list(sticker.size),
        "alpha_extrema": list(sticker.getchannel("A").getextrema()),
    }
    write_json(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "runs/serverless-smoke", help="New output folder"
    )
    args = parser.parse_args()
    available_credit = credit()
    if available_credit < MINIMUM_SERVERLESS_CREDIT:
        shortfall = MINIMUM_SERVERLESS_CREDIT - available_credit
        raise SystemExit(
            f"Vast Serverless requires at least ${MINIMUM_SERVERLESS_CREDIT:.2f} credit; "
            f"current credit is ${available_credit:.6f} (${shortfall:.6f} short)."
        )
    if args.output.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {args.output}")
    args.output.mkdir(parents=True)
    report = asyncio.run(run(args.output))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
