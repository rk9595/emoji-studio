"""Summarize private-alpha usage, feedback, failures, and measured generation cost."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.alpha_report import markdown_report, summarize_alpha  # noqa: E402
from emoji_studio.common import read_json, write_json  # noqa: E402


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--jobs", type=Path, default=ROOT / "var/jobs")
    parser.add_argument("--config", type=Path, default=ROOT / "configs/alpha.json")
    parser.add_argument("--json-output", type=Path, default=ROOT / "reports/private-alpha.json")
    parser.add_argument("--markdown-output", type=Path, default=ROOT / "reports/private-alpha.md")
    args = parser.parse_args()
    report = summarize_alpha(args.jobs, read_json(args.config))
    write_json(args.json_output, report)
    args.markdown_output.parent.mkdir(parents=True, exist_ok=True)
    args.markdown_output.write_text(markdown_report(report))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
