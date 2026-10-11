#!/usr/bin/env python3
"""Build a checksum-verified matched base/adapter evaluation gallery."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
from pathlib import Path

from evaluate_lora import evaluation_jobs


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(output: Path, config_path: Path, title: str, adapted_label: str) -> dict:
    report_path = output / "evaluation/report.json"
    report = json.loads(report_path.read_text())
    config, benchmark_path, jobs = evaluation_jobs(config_path=config_path)
    expected_settings = {
        key: value for key, value in config["evaluation"].items() if key != "benchmark"
    }
    actual_settings = report.get("settings", {})
    if (
        report.get("status") != "completed"
        or any(actual_settings.get(key) != value for key, value in expected_settings.items())
        or report.get("model_id") != config["model_id"]
        or report.get("model_revision") != config["model_revision"]
        or report.get("benchmark_sha256") != sha256(benchmark_path)
    ):
        raise ValueError("Evaluation is incomplete or differs from the selected recipe")
    adapter = output / "pytorch_lora_weights.safetensors"
    if not adapter.is_file() or sha256(adapter) != report["adapter_sha256"]:
        raise ValueError("Evaluation adapter checksum differs")

    rows = {}
    for row in report["images"]:
        key = (row["pair_id"], row["condition"])
        source = output / row["image"]
        if (
            key in rows
            or not source.resolve().is_relative_to(output.resolve())
            or not source.is_file()
            or sha256(source) != row["image_sha256"]
        ):
            raise ValueError("Evaluation image is duplicated, missing, unsafe, or corrupt")
        rows[key] = row
    expected_rows = {
        (job["pair_id"], condition) for job in jobs for condition in ("base", "adapted")
    }
    if set(rows) != expected_rows:
        raise ValueError("Evaluation pairs are incomplete")

    cards = []
    for job in jobs:
        figures = []
        for condition, label in (("base", "Base model"), ("adapted", adapted_label)):
            row = rows[(job["pair_id"], condition)]
            if any(row.get(key) != job[key] for key in ("prompt_id", "prompt", "seed")):
                raise ValueError("Evaluation prompt or seed differs")
            source = html.escape(row["image"], quote=True)
            figures.append(
                f"<figure><figcaption>{html.escape(label)}</figcaption>"
                f'<a href="{source}"><img class="main" src="{source}" '
                f'alt="{html.escape(job["prompt"], quote=True)}"></a>'
                f'<p>32 px <img width="32" height="32" src="{source}" alt=""> '
                f'64 px <img width="64" height="64" src="{source}" alt=""></p></figure>'
            )
        cards.append(
            f'<article data-category="{html.escape(job["category"], quote=True)}">'
            f"<h2>{html.escape(job['prompt_id'])} · seed {job['seed']}</h2>"
            f"<p>{html.escape(job['prompt'])}</p><div class=\"pair\">"
            + "".join(figures)
            + f'</div><p class="criteria">{html.escape("; ".join(job["criteria"]))}</p>'
            + "</article>"
        )
    categories = sorted({job["category"] for job in jobs})
    options = "".join(f"<option>{html.escape(category)}</option>" for category in categories)
    environment = report.get("environment") or {}
    environment_text = " · ".join(
        str(value)
        for value in (environment.get("gpu"), environment.get("backend"), environment.get("hip"))
        if value
    )
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:16px system-ui;background:#f4f4f4;color:#202020;margin:24px auto;padding:0 20px;max-width:1100px}}
h1{{font-size:28px}}h2{{font-size:18px}}p{{line-height:1.5}}article{{background:white;padding:20px;margin:24px 0;border-radius:12px}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:20px}}figure{{margin:0;min-width:0}}
figcaption{{font-weight:600;margin:12px 0}}.main{{width:100%;height:auto}}p img{{vertical-align:middle}}
.criteria{{font-size:14px;color:#555}}select{{padding:8px;font:inherit}}[hidden]{{display:none}}
</style><h1>{html.escape(title)}</h1>
<p>{len(jobs)} matched pairs with identical prompts and seeds. {html.escape(environment_text)}.
This is an unblinded diagnostic gallery; check semantics and small-size readability.</p>
<label>Category <select id="category"><option value="">All categories</option>{options}</select></label>
{''.join(cards)}<script>
document.querySelector('#category').addEventListener('change',event=>{{
 for(const card of document.querySelectorAll('article'))
  card.hidden=Boolean(event.target.value&&card.dataset.category!==event.target.value);
}});</script></html>'''
    destination = output / "evaluation-review.html"
    destination.write_text(page)
    return {
        "path": str(destination),
        "pairs": len(jobs),
        "verified_images": len(rows),
        "html_sha256": sha256(destination),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--title", default="Matched base/adapter evaluation")
    parser.add_argument("--adapted-label", default="Adapted model")
    args = parser.parse_args()
    print(
        json.dumps(
            build(
                args.output.resolve(),
                args.config.resolve(),
                args.title,
                args.adapted_label,
            ),
            indent=2,
        )
    )
