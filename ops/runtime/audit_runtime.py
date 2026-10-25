"""CPU-only image audit. Run only inside the proposed native Linux/amd64 image."""

import importlib.metadata
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

PROTECTED = {"torch", "torchvision", "torchaudio", "triton", "apex"}
TESTS = ("test_render_budget.py", "test_mock_smoke_executor.py", "test_smoke_cleanup.py",
         "test_smoke_export.py", "test_amd_api_smoke_plan.py", "test_amd_runtime_proposal.py")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def inventory():
    rows = {}
    for distribution in importlib.metadata.distributions():
        name = normalized(distribution.metadata["Name"])
        version = distribution.version
        require(re.fullmatch(r"[a-z0-9][a-z0-9-]*", name) is not None
                and re.fullmatch(r"[A-Za-z0-9.+!_-]{1,128}", version) is not None,
                "Unexpected distribution metadata")
        require(name not in rows, "Duplicate installed distribution")
        rows[name] = version
    return dict(sorted(rows.items()))


def validate_inventory(before, after, overlay):
    require(PROTECTED.issubset(before), "Expected base GPU packages missing; review inventory")
    protected = {name for name in before if name in PROTECTED or name.startswith(
        ("torch", "triton", "pytorch-triton", "rocm-", "hip-", "amd-", "nvidia-", "cuda-"))}
    require(not protected.intersection(overlay), "Overlay must not replace GPU packages")
    require(all(after.get(name) == before[name] for name in protected), "Base GPU stack changed")
    require(all(after.get(name) == version for name, version in overlay.items()),
            "Installed overlay differs from lock")
    require(not any(name.startswith(("nvidia-", "cuda-")) for name in after),
            "Unexpected NVIDIA/CUDA distribution")
    require(before["torch"].startswith("2.10.0+rocm7.2")
            and before["torchvision"].startswith("0.25.0"), "Unexpected base Torch versions")
    return sorted(protected)


def save(path, value):
    with path.open("x") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")
    # Public package/version metadata only; retain even when a later build step
    # fails and Docker discards its intermediate layer. No environment dump.
    print("RUNTIME_AUDIT_" + path.stem + "=" + json.dumps(value, sort_keys=True), flush=True)


def run(command, timeout=180):
    subprocess.run(command, check=True, timeout=timeout, cwd="/app")


def main():
    require(len(sys.argv) == 2 and sys.argv[1] in ("base", "verify"), "Use base or verify")
    require(platform.system() == "Linux" and platform.machine() == "x86_64"
            and sys.version_info[:2] == (3, 12), "Native Linux/amd64 Python 3.12 required")
    require(Path("/app/configs/amd-runtime-proposal.json").is_file(), "Staged app missing")
    audit = Path("/audit")
    audit.mkdir(exist_ok=True)
    current = inventory()
    if sys.argv[1] == "base":
        save(audit / "base-packages.json", current)
        return
    # Import only the offline lock parser, never a cloud launcher.
    sys.path.insert(0, "/app/scripts")
    from check_amd_runtime_proposal import check, lock_packages

    check(Path("/app"))
    overlay = lock_packages(Path("/app/configs/amd-overlay-linux-py312.txt").read_text())
    before = json.loads((audit / "base-packages.json").read_text())
    save(audit / "installed-packages.json", current)
    protected = validate_inventory(before, current, overlay)
    run([sys.executable, "-m", "pip", "--isolated", "check"])
    # No model creation/download. This probes imports/native CPU operators only.
    run([sys.executable, "-c", '''
import json
import torch, torchvision, torchaudio, triton, apex
import numpy, PIL, fastapi, uvicorn, httpx, transformers, peft, accelerate, safetensors, sentencepiece
from diffusers import Flux2KleinPipeline
assert torch.version.hip and torch.version.hip.startswith("7.2")
assert torch.version.cuda is None
assert torch.cuda.device_count() == 0, "CPU audit must not have a GPU attached"
value = torch.ones((2, 2), dtype=torch.bfloat16)
assert (value @ value).sum().item() == 8
boxes = torch.tensor([[0., 0., 1., 1.]])
assert torchvision.ops.nms(boxes, torch.tensor([1.]), 0.5).tolist() == [0]
print(json.dumps({"cpu_imports": "passed", "torch": torch.__version__, "hip": torch.version.hip,
                  "gpu_validated": False}))
'''])
    for pattern in TESTS:
        run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-p", pattern])
    run([sys.executable, "-m", "emoji_studio.smoke_http"], timeout=90)
    run([sys.executable, "-m", "emoji_studio.mock_smoke_executor"], timeout=90)
    save(audit / "cpu-verification.json", {
        "status": "cpu_checks_passed", "protected_packages": protected,
        "test_modules": list(TESTS), "http_and_executor_smokes": "passed",
        "gpu_validated": False, "model_loaded": False, "execution_authorized": False,
    })


if __name__ == "__main__":
    main()
