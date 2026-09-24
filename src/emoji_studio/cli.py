import argparse
import json
from pathlib import Path

from .assets import fetch_assets
from .benchmark import create_plan, validate_benchmark
from .common import read_json
from .curation import create_curation, training_preflight
from .report import build_report
from .runner import generate
from .training_data import export_training


def main():
    parser = argparse.ArgumentParser(description="Emoji dataset and baseline workbench")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    assets = commands.add_parser(
        "assets", help="Inventory pinned Fluent assets and download references"
    )
    assets.add_argument("--limit", type=int, default=64)
    commands.add_parser("validate", help="Validate the development benchmark")
    commands.add_parser("report", help="Build the offline visual workbench")
    curate = commands.add_parser(
        "curation-template",
        help="Create pending review records without approving any training data",
    )
    curate.add_argument("--output", type=Path, default=Path("data/curation.json"))
    preflight = commands.add_parser(
        "training-preflight",
        help="Check reviewed data without loading models or launching training",
    )
    preflight.add_argument("--curation", type=Path, default=Path("data/curation.json"))
    preflight.add_argument("--config", type=Path, default=Path("configs/lora-pilot.json"))
    export = commands.add_parser("export-training", help="Export reviewed RGB images and captions")
    export.add_argument("--curation", type=Path, default=Path("data/curation.json"))
    export.add_argument("--config", type=Path, default=Path("configs/lora-pilot.json"))
    export.add_argument("--output", type=Path, required=True)
    plan = commands.add_parser("plan", help="Create a baseline manifest without loading any models")
    plan.add_argument("--model", required=True, choices=["klein", "sdxl"])
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--conditions", nargs="+", choices=["raw", "brief"], default=["brief"])
    plan.add_argument("--seeds", nargs="+", type=int, default=[0, 1, 2, 3])
    plan.add_argument("--limit", type=int)
    plan.add_argument("--resolution", type=int, default=512)
    plan.add_argument("--benchmark", type=Path)
    run = commands.add_parser("generate", help="Execute a saved plan on a CUDA machine")
    run.add_argument("--plan", type=Path, required=True)
    run.add_argument("--max-seconds", type=int, default=900)
    run.add_argument("--cpu-offload", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    try:
        if args.command == "assets":
            result = fetch_assets(root, args.limit)
        elif args.command == "validate":
            data = validate_benchmark(read_json(root / "benchmarks/development.json"))
            result = {"valid": True, "split": data["split"], "prompts": len(data["prompts"])}
        elif args.command == "report":
            result = build_report(root)
        elif args.command == "curation-template":
            result = create_curation(root, root / args.output)
        elif args.command == "training-preflight":
            result = training_preflight(root, root / args.curation, root / args.config)
        elif args.command == "export-training":
            result = export_training(
                root, root / args.curation, root / args.config, root / args.output
            )
        elif args.command == "plan":
            output = args.output if args.output.is_absolute() else root / args.output
            plan = create_plan(
                root,
                output,
                args.model,
                args.conditions,
                args.seeds,
                args.limit,
                args.resolution,
                (root / args.benchmark) if args.benchmark else None,
            )
            result = {
                "path": str(output),
                "jobs": plan["job_count"],
                "experiment_hash": plan["experiment_hash"],
            }
        else:
            path = args.plan if args.plan.is_absolute() else root / args.plan
            result = generate(path, args.max_seconds, args.cpu_offload)
        print(json.dumps(result, indent=2))
        if args.command == "training-preflight" and not result["data_ready"]:
            parser.exit(2, "Training data is not ready; no training was started.\n")
        if args.command == "generate" and result.get("status") != "completed":
            parser.exit(
                2, "Run incomplete; inspect the summary and per-image receipts before resuming.\n"
            )
    except (ValueError, OSError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
