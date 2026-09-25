"""Check candidate data without launching training or spending GPU credit."""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from emoji_studio.common import write_json  # noqa: E402
from emoji_studio.interactions import interaction_preflight  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=ROOT / "configs/high-five-curation.json")
    args = parser.parse_args()
    report = interaction_preflight(ROOT, args.manifest)
    write_json(ROOT / "reports/high-five-data-preflight.json", report)
    print(f"Data ready: {report['data_ready']}; accepted: {report['accepted_counts']}")
    for issue in report["blocking_issues"]:
        print(f"  {issue['id']}: {', '.join(issue['reasons'])}")
    return 0 if report["data_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
