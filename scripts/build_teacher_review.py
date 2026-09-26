"""Build an unblinded teacher gallery, preserving existing human review answers."""

import argparse
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from sample_interaction_teacher import OUTPUT, make_plan, validate_report  # noqa: E402

from emoji_studio.common import read_json, write_json  # noqa: E402


def build(output, plan=None):
    plan = make_plan() if plan is None else plan
    total = len(plan["jobs"])
    report = validate_report(output, plan, require_complete=False)
    cards = []
    for row in report["images"]:
        job = row["job"]
        # Use the canonical verified path, never an arbitrary report-supplied URL.
        path = html.escape(f"images/{job['id']}.png", quote=True)
        label = html.escape(job["id"])
        cards.append(
            f'<article><h2>{label} · seed {job["seed"]}</h2>'
            f'<img class="large" src="{path}" alt="{label}">'
            f'<p>32 px <img width="32" height="32" src="{path}" alt="{label}"> '
            f'64 px <img width="64" height="64" src="{path}" alt="{label}"></p>'
            f'<p>{html.escape(job["prompt"])}</p>'
            f'<p>PNG SHA-256: <code>{row["image_sha256"]}</code></p></article>'
        )
    page = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Qwen high-five teacher review</title><style>
body{font:15px system-ui;margin:24px;color:#171717;background:#eee}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:20px}
article{background:white;padding:16px;border-radius:12px}h2{font-size:16px}
.large{width:100%;height:auto}p img{vertical-align:middle}p{line-height:1.5}
code{overflow-wrap:anywhere}
</style><h1>Qwen high-five teacher review</h1>
<p>Unblinded diagnostic gallery, not a human evaluation. Source PNGs are unchanged.
Inspect gesture, palm contact, wrist separation, anatomy, emoji style and readability.
All images remain pending for training.</p>
''' + f'<p>{len(report["images"])}/{total} verified images. Last saved remote status: ' \
        + html.escape(report["status"]) + ' (not a live status check).</p><div class="grid">' \
        + "".join(cards) + "</div></html>"
    template = output / "human-review-template.json"
    document = read_json(template) if template.exists() else {
        "plan_hash": plan["plan_hash"], "reviewer": "", "reviewer_kind": "human", "images": [],
    }
    if document["plan_hash"] != plan["plan_hash"]:
        raise ValueError("Existing human review belongs to another plan")
    indexed = {row["job_id"]: row for row in document["images"]}
    for row in report["images"]:
        identifier = row["job"]["id"]
        if identifier in indexed:
            if indexed[identifier]["image_sha256"] != row["image_sha256"]:
                raise ValueError("Existing human review is bound to another image")
            continue
        document["images"].append({
            "job_id": identifier, "image_sha256": row["image_sha256"],
            "gesture_correct": None, "anatomy_correct": None, "palm_contact": None,
            "wrists_separated": None, "readable_32px": None, "style_correct": None,
            "notes": "",
        })
    document["trial_outcome"] = f'{len(report["images"])}/{total} verified local images'
    (output / "review.html").write_text(page)
    write_json(template, document)
    print(output / "review.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trial", choices=["pilot", "golden"], default="pilot")
    args = parser.parse_args()
    if args.trial == "golden":
        from sample_golden_teacher import OUTPUT as GOLDEN_OUTPUT
        from sample_golden_teacher import make_plan as golden_plan
        build(ROOT / GOLDEN_OUTPUT, golden_plan())
    else:
        build(ROOT / OUTPUT)
