"""Reuse matching heavy packages from the pinned PyTorch image."""

import argparse
import importlib.metadata
import json
import subprocess
import sys
import tomllib
from pathlib import Path

import torch

parser = argparse.ArgumentParser()
parser.add_argument("--training", action="store_true")
args = parser.parse_args()

assert torch.__version__.split("+")[0] == "2.10.0", torch.__version__
assert torch.version.cuda == "12.8", torch.version.cuda
lock = tomllib.loads(Path("uv.lock").read_text())
reused = {}
for package in lock["package"]:
    name = package["name"]
    if name not in {"torch", "triton"} and not name.startswith("nvidia-"):
        continue
    try:
        installed = importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        continue
    if installed == package["version"] or (name == "torch" and installed.split("+")[0] == "2.10.0"):
        reused[name] = installed
subprocess.run(
    ["uv", "venv", "--system-site-packages", "--python", sys.executable, ".venv"], check=True
)
command = ["uv", "sync", "--extra", "gpu", "--no-dev", "--frozen"]
if args.training:
    command.extend(["--group", "training"])
for name in reused:
    command.extend(["--no-install-package", name])
print("Reusing pinned image packages:", json.dumps(reused), flush=True)
subprocess.run(command, check=True)
Path("runs/base-environment.json").write_text(
    json.dumps({"reused": reused, "python": sys.version, "training": args.training}, indent=2)
)
