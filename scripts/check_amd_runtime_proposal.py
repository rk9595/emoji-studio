"""Check an offline AMD runtime proposal; --registry reads public metadata only."""

import argparse
import hashlib
import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAG = "rocm7.2_ubuntu24.04_py3.12_pytorch_release_2.10.0"
MANIFEST = "sha256:bcb2efa1d43f66cc59fa45a1975d621a50b2b06d21a2abdfa2ba821ab32763e4"
CONFIG = "sha256:701f42ee1596bdb69351147d27496b45613016b1072024229064eb756524906c"
BASE_PROVIDED = {"torch", "torchvision", "torchaudio", "triton", "apex"}
FILES = {"configs/amd-overlay.in", "configs/amd-base-provided.in",
         "configs/amd-overlay-linux-py312.txt", "reports/amd-runtime-registry.json"}
BLOCKERS = ["base_and_overlay_install_inventory_not_verified",
            "derived_image_not_built_or_digest_pinned", "hip_gpu_and_model_smoke_not_run",
            "independent_cleanup_and_export_not_ready", "new_bounded_spend_allowance_missing"]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def verify_registry(receipt):
    require(receipt["repository"] == "docker.io/rocm/pytorch" and receipt["observed_tag"] == TAG,
            "Registry identity differs")
    raw_manifest = receipt["manifest_json"].encode()
    raw_config = receipt["config_json"].encode()
    require("sha256:" + digest(raw_manifest) == MANIFEST, "Manifest digest differs")
    require("sha256:" + digest(raw_config) == CONFIG, "Config digest differs")
    manifest, config = read_json(raw_manifest), read_json(raw_config)
    require(manifest["schemaVersion"] == 2 and manifest["config"]["digest"] == CONFIG,
            "Manifest/config binding differs")
    require(manifest["config"]["size"] == len(raw_config), "Config size differs")
    require(config["os"] == "linux" and config["architecture"] == "amd64", "Wrong base platform")
    size = 0
    for layer in manifest["layers"]:
        require(re.fullmatch(r"sha256:[0-9a-f]{64}", layer["digest"])
                and type(layer["size"]) is int and layer["size"] > 0, "Invalid layer descriptor")
        size += layer["size"]
    return {"manifest_digest": MANIFEST, "config_digest": CONFIG, "platform": "linux/amd64",
            "compressed_layer_bytes": size, "layer_count": len(manifest["layers"]),
            "created": config.get("created"), "layers_downloaded": False}


def inspect_registry():
    def get(url, headers=None):
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=20) as response:
            raw = response.read(2 * 1024 * 1024 + 1)
            require(len(raw) <= 2 * 1024 * 1024, "Metadata exceeds size bound")
            return raw
    # Anonymous repository-read token lives only in memory, never in receipts.
    token = read_json(get("https://auth.docker.io/token?service=registry.docker.io&scope=repository:rocm/pytorch:pull"))["token"]
    headers = {"Authorization": "Bearer " + token,
               "Accept": "application/vnd.docker.distribution.manifest.v2+json"}
    manifest = get(f"https://registry-1.docker.io/v2/rocm/pytorch/manifests/{TAG}", headers)
    require("sha256:" + digest(manifest) == MANIFEST, "Tag moved; explicit review required")
    config = get(f"https://registry-1.docker.io/v2/rocm/pytorch/blobs/{CONFIG}", headers)
    receipt = {"repository": "docker.io/rocm/pytorch", "observed_tag": TAG,
               "manifest_json": manifest.decode(), "config_json": config.decode()}
    receipt["verified"] = verify_registry(receipt)
    return receipt


def lock_packages(text):
    result = {}
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        match = re.fullmatch(r"([a-z0-9][a-z0-9-]*)==([A-Za-z0-9.+!-]+)", fields[0])
        require(match is not None, "Only exact package pins allowed")
        name, version = match.groups()
        require(name not in result, "Duplicate package")
        require(name not in BASE_PROVIDED and not name.startswith(("nvidia-", "cuda-", "rocm-")),
                "GPU stack must remain base-provided")
        require(len(fields) > 1 and all(re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", value)
                                       for value in fields[1:]), "Missing or invalid distribution hash")
        result[name] = version
    require(bool(result), "Empty overlay")
    return result


def check(root=ROOT):
    root = Path(root).resolve()
    proposal = read_json((root / "configs/amd-runtime-proposal.json").read_text())
    require(type(proposal["schema_version"]) is int and proposal["schema_version"] == 1,
            "Unsupported runtime proposal schema")
    require(proposal["status"] == "prepared_only" and proposal["execution_authorized"] is False
            and proposal["runtime_validated"] is False and proposal["approved_allowance_usd"] is None
            and proposal["derived_image_digest"] is None, "Runtime authority gate differs")
    require(proposal["blockers"] == BLOCKERS, "Runtime prerequisites changed")
    require(proposal["base_image"] == "docker.io/rocm/pytorch@" + MANIFEST, "Base image differs")
    require(proposal["target"] == {"os": "linux", "architecture": "amd64", "python": "3.12",
                                   "resolver_platform": "x86_64-manylinux_2_39"}, "Target differs")
    require(set(proposal["files_sha256"]) == FILES, "Runtime file inventory differs")
    for relative, expected in proposal["files_sha256"].items():
        path = root
        for part in Path(relative).parts:
            path /= part
            require(not path.is_symlink(), "Symlinked input")
        require(digest(path.read_bytes()) == expected, "Runtime input drift")
    registry = read_json((root / "reports/amd-runtime-registry.json").read_text())
    verified = verify_registry(registry)
    require(verified == registry["verified"], "Registry summary differs")
    packages = lock_packages((root / "configs/amd-overlay-linux-py312.txt").read_text())
    require(proposal["overlay"]["installed"] is False
            and proposal["base_stack_expected_from_tag"]["inventory_verified"] is False,
            "Unverified installation claim")
    require(proposal["overlay"]["packages"] == len(packages)
            and set(proposal["overlay"]["base_provided_exclusions"]) == BASE_PROVIDED,
            "Overlay inventory differs")
    excluded = {line.strip() for line in (root / "configs/amd-base-provided.in").read_text().splitlines()
                if line.strip() and not line.startswith("#")}
    require(excluded == BASE_PROVIDED, "Base exclusions differ")
    for line in (root / "configs/amd-overlay.in").read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            name, version = line.split("==")
            require(packages.get(name) == version, "Direct dependency pin differs")
    return {"status": "prepared_only", "execution_authorized": False, "runtime_validated": False,
            "overlay_packages": len(packages), "base": verified, "blockers": BLOCKERS,
            "note": "Metadata integrity and conditional overlay resolution only; not a validated runtime."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", action="store_true", help="Read fixed public image metadata; no layers/pulls")
    args = parser.parse_args()
    try:
        print(json.dumps(inspect_registry() if args.registry else check(), indent=2, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError):
        print(json.dumps({"status": "invalid", "execution_authorized": False}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
