"""Read-only draft integrity check. No credentials, network, GPU imports or writes.

A passing result means prepared-only, NEVER executable. Deliberately cannot
accept an authorization or relock changed files; those require a separate review.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

PLAN = "configs/amd-api-smoke-plan.json"
FILES = {
    "configs/serving.json", "pyproject.toml", "uv.lock", "reports/local-http-smoke.json",
    "reports/mock-smoke-executor.json",
    *(f"src/emoji_studio/{name}" for name in (
        "__init__.py", "alpha.py", "api.py", "common.py", "durable_api.py",
        "durable_worker.py", "service.py", "smoke_http.py", "studio.html", "worker_queue.py",
        "render_budget.py", "mock_smoke_executor.py",
    )),
    *(f"tests/{name}" for name in (
        "test_smoke_http.py", "test_durable_api.py", "test_worker_queue.py",
        "test_worker_admission.py",
        "test_render_budget.py", "test_mock_smoke_executor.py",
    )),
}
BLOCKERS = [
    "new_explicit_spend_allowance_and_current_price_check",
    "immutable_rocm_runtime_and_amd_dependency_lock",
    "dedicated_smoke_executor_with_physical_render_budget",
    "independent_cloud_expiry_reaper_and_deletion_receipts",
    "private_export_destination_and_checksum_verification",
]
DRAFT = {
    "schema_version": 1,
    "plan_id": "amd-api-smoke-v1",
    "status": "prepared_only",
    "execution_authorized": False,
    "approved_allowance_usd": None,
    "proposed_limits": {
        "allocations": 1, "concurrent_gpus": 1, "admitted_images": 2,
        "physical_render_calls": 2, "replacement_allocations": 0,
        "automatic_post_retries": 0, "allocation_lifetime_seconds": 1800,
        "cleanup_reserve_seconds": 300,
    },
    "runtime": {"status": "unresolved", "oci_digest": None, "amd_python_lock_sha256": None},
    "requests": [{"prompt": "a cheerful red apple sticker", "seed": 7}] * 2,
    "network": {"bind": "127.0.0.1", "access": "private_ssh_tunnel", "public_endpoint": False},
    "blockers": BLOCKERS,
}
SERVING_KEYS = {
    "model_id", "model_revision", "adapter_path", "adapter_sha256", "selected_step",
    "resolution", "steps", "guidance_scale",
}
ADAPTER = "runs/lora-quality-pilot/adapters/step-25.safetensors"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def safe_path(root, relative):
    path = Path(relative)
    require(not path.is_absolute() and ".." not in path.parts, "Unsafe lock path")
    current = root
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), "Symlinks are not allowed in locked paths")
    require(current.resolve().is_relative_to(root), "Lock path escapes root")
    return current


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(), object_pairs_hook=unique)


def check_plan(root):
    root = Path(root).resolve()
    plan_path = safe_path(root, PLAN)
    plan = read_json(plan_path)
    require(set(plan) == set(DRAFT) | {"source_baseline_commit", "serving", "source_sha256"},
            "Unexpected plan fields")
    for key, expected in DRAFT.items():
        # JSON serialization distinguishes boolean true from integer 1.
        require(json.dumps(plan[key], sort_keys=True) == json.dumps(expected, sort_keys=True),
                f"Prepared-only constraint changed: {key}")
    require(isinstance(plan["source_baseline_commit"], str)
            and re.fullmatch(r"[0-9a-f]{40}", plan["source_baseline_commit"]),
            "Missing source baseline commit")
    locks = plan["source_sha256"]
    require(set(locks) == FILES, "Locked file inventory differs")
    for relative, expected in locks.items():
        require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected),
                "Invalid source hash")
        require(digest(safe_path(root, relative)) == expected, f"Locked file drift: {relative}")

    config = read_json(safe_path(root, "configs/serving.json"))
    require(set(plan["serving"]) == SERVING_KEYS, "Serving lock fields differ")
    require(plan["serving"] == {key: config[key] for key in SERVING_KEYS}, "Serving identity differs")
    require(config["adapter_path"] == ADAPTER and config["selected_step"] == 25,
            "Serving promotion is outside this plan")
    receipt = read_json(safe_path(root, "reports/local-http-smoke.json"))
    require(receipt["status"] == "passed" and receipt["renderer"] == "MockRenderer"
            and receipt["gpu_allocations"] == 0, "Local smoke evidence differs")
    for name, expected in receipt["source_sha256"].items():
        require(locks.get("src/emoji_studio/" + name) == expected, "Local smoke source drift")
    mock = read_json(safe_path(root, "reports/mock-smoke-executor.json"))
    require(mock["status"] == "passed" and mock["renderer"] == "MockRenderer"
            and mock["gpu_allocations"] == 0 and mock["execution_authorized"] is False
            and mock["jobs_published"] == 2 and mock["render_calls_consumed"] == 2
            and mock["third_call_denied"] is True, "Mock executor evidence differs")
    for name, expected in mock["source_sha256"].items():
        require(locks.get("src/emoji_studio/" + name) == expected, "Mock executor source drift")
    adapter = safe_path(root, ADAPTER)
    adapter_state = "missing_private_artifact"
    if adapter.exists():
        require(digest(adapter) == config["adapter_sha256"], "Private adapter checksum differs")
        adapter_state = "verified"
    return {
        "status": "prepared_only", "execution_authorized": False,
        "plan_sha256": digest(plan_path), "locked_files_verified": len(locks),
        "adapter": adapter_state, "blockers": BLOCKERS,
        "note": "Draft integrity only; no cloud readiness or spending authorization.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        result = check_plan(args.root)
    except (ValueError, OSError, KeyError, TypeError):
        # Do not print file contents, secret paths, or arbitrary exception text.
        print(json.dumps({"status": "invalid", "execution_authorized": False}))
        raise SystemExit(1) from None
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
