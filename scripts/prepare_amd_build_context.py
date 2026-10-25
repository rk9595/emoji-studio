"""Stage a reviewed, hash-locked public CPU build context. Never builds/pulls."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RECIPE = "configs/amd-builder-proposal.json"
EXTRA_APP = {
    "configs/amd-api-smoke-plan.json", "configs/amd-runtime-proposal.json",
    "scripts/check_amd_api_smoke_plan.py", "scripts/check_amd_runtime_proposal.py",
    "scripts/prepare_amd_build_context.py",
    "tests/test_amd_api_smoke_plan.py", "tests/test_amd_runtime_proposal.py",
    "src/emoji_studio/smoke_cleanup.py", "src/emoji_studio/smoke_export.py",
    "tests/test_smoke_cleanup.py", "tests/test_smoke_export.py",
}
RECIPE_FILES = {"ops/runtime/Dockerfile", "ops/runtime/audit_runtime.py"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(root, relative):
    path = root
    for part in Path(relative).parts:
        require(part not in ("..", "/"), "Unsafe path")
        path /= part
        require(not path.is_symlink(), "Symlinked input")
    require(path.is_file(), "Missing regular input")
    return path.read_bytes()


def inputs(root=ROOT):
    root = Path(root).resolve()
    plan = json.loads(read(root, "configs/amd-api-smoke-plan.json"))
    runtime = json.loads(read(root, "configs/amd-runtime-proposal.json"))
    app = set(plan["source_sha256"]) | set(runtime["files_sha256"]) | EXTRA_APP
    # No private adapters, images, logs, environment or Git metadata can enter.
    for name in app:
        require(name.startswith(("src/emoji_studio/", "configs/", "tests/", "scripts/", "reports/"))
                or name in ("pyproject.toml", "uv.lock"), "Unexpected input location")
    return app


def verify(root=ROOT):
    root = Path(root).resolve()
    proposal = json.loads(read(root, RECIPE))
    require(proposal["status"] == "prepared_only" and proposal["paid_execution_authorized"] is False
            and proposal["gpu_execution_authorized"] is False, "Builder authority changed")
    require(proposal["target"] == "linux/amd64" and proposal["max_minutes"] == 45
            and proposal["minimum_free_gib"] == 60, "Builder bounds changed")
    app = inputs(root)
    require(set(proposal["files_sha256"]) == app | RECIPE_FILES, "Input inventory changed")
    raw = {name: read(root, name) for name in sorted(app | RECIPE_FILES)}
    for name, content in raw.items():
        require(hashlib.sha256(content).hexdigest() == proposal["files_sha256"][name],
                f"Reviewed builder input changed: {name}")
    return proposal, app, raw


def stage(output, root=ROOT):
    proposal, app, raw = verify(root)
    output = Path(output).absolute()
    require(not any(p.is_symlink() for p in (output, *output.parents)), "Symlinked output")
    output.mkdir(mode=0o700, exist_ok=False)
    # All input bytes were validated before creating anything. Partial failure
    # leaves the new context for inspection; never overwrites or resets it.
    for name in sorted(app):
        destination = output / "app" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(raw[name])
    for name in RECIPE_FILES:
        (output / Path(name).name).write_bytes(raw[name])
    (output / "builder-proposal.json").write_text(json.dumps(proposal, indent=2) + "\n")
    return {"status": "staged_only", "app_files": len(app), "image_built": False,
            "gpu_execution_authorized": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.output is None:
        _, app, _ = verify()
        print(json.dumps({"status": "prepared_only", "app_files": len(app), "image_built": False}))
    else:
        print(json.dumps(stage(args.output)))


if __name__ == "__main__":
    main()
