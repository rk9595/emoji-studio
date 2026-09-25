"""Build a local review page without altering the generated image files."""

import html
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.common import read_json  # noqa: E402


def build(output):
    report = read_json(output / "report.json")
    cards = []
    # This is explicitly an unblinded diagnostic gallery, not preference evidence.
    for row in sorted(report["images"], key=lambda row: (
        row["job"]["prompt_id"], row["job"]["variant"], row["job"]["seed"]
    )):
        job = row["job"]
        image = html.escape(row["image"], quote=True)
        label = html.escape(job["id"])
        cards.append(f'<article><h3>{label}</h3><img class="large" src="{image}">'
                     f'<p>32 px <img width="32" height="32" src="{image}"> '
                     f'64 px <img width="64" height="64" src="{image}"></p>'
                     f'<p>{html.escape(job["prompt"])}</p>'
                     f'<p>{html.escape("; ".join(job["criteria"]))}</p></article>')
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>High-five baseline review</title><style>
body{font:15px system-ui;background:#eee;margin:24px;color:#171717}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:16px}
article{background:white;padding:16px;border-radius:12px}h3{font-size:13px}
.large{width:100%;height:auto}p img{vertical-align:middle}p{line-height:1.5}
</style><h1>High-five baseline: base versus style adapter</h1>
<p>Unblinded diagnostic gallery. AI inspection is not human preference evidence.
Count semantic failures even when the image looks polished. Source PNGs are unchanged.</p>
<div class="grid">''' + "".join(cards) + "</div></html>"
    (output / "review.html").write_text(page)
    review_path = output / "human-review-template.json"
    if report["status"] == "completed" and not review_path.exists():
        review_path.write_text(json.dumps({
            "plan_hash": report["plan_hash"], "reviewer": "", "reviewer_kind": "human",
            "images": [{"job_id": row["job"]["id"], "image_sha256": row["image_sha256"],
                        "gesture_correct": None, "anatomy_correct": None,
                        "readable_32px": None, "criteria_pass": None,
                        "severe_anatomy_defect": None, "notes": ""}
                       for row in report["images"]],
        }, indent=2) + "\n")
    print(output / "review.html")


if __name__ == "__main__":
    build(ROOT / "runs/high-five-baseline-v1")
