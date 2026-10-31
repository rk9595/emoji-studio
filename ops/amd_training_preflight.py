"""Read-only compatibility check against the provider's retained packages.

Run inside the provider container before installing a future training overlay.
This does not replace the post-install pip check or validate GPU kernels.
"""

import argparse
import importlib.metadata
import json
import re
from pathlib import Path

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version


def overlay_versions(text):
    result = {}
    for line in text.replace("\\\n", " ").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        match = re.fullmatch(r"([a-z0-9-]+)==([A-Za-z0-9.+!-]+)", fields[0])
        if not match or len(fields) < 2 or any(
            not re.fullmatch(r"--hash=sha256:[0-9a-f]{64}", value) for value in fields[1:]
        ):
            raise ValueError("Expected an exact hash-pinned overlay")
        name, version = match.groups()
        if name in result or name.startswith(("torch", "triton", "pytorch-triton", "rocm-", "hip-", "nvidia-", "cuda-")) or name == "apex":
            raise ValueError("Duplicate or protected GPU package")
        Version(version)
        result[name] = version
    if not result:
        raise ValueError("Empty overlay")
    return result


def audit(records, overlay, environment=None):
    retained = {}
    for record in records:
        name = canonicalize_name(record["name"])
        if name in retained:
            raise ValueError("Duplicate installed distribution")
        retained[name] = record
    planned = {name: record["version"] for name, record in retained.items()} | overlay
    marker_environment = {**default_environment(), **(environment or {}), "extra": ""}
    conflicts = []
    for name, record in sorted(retained.items()):
        if name in overlay:
            continue  # Old metadata is replaced by the overlay wheel.
        for text in record.get("requires", []):
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate(marker_environment):
                continue
            target = canonicalize_name(requirement.name)
            version = planned.get(target)
            if version is None or not requirement.specifier.contains(version, prereleases=True):
                conflicts.append({"package": name, "requirement": text, "planned_version": version})
    return {"status": "blocked" if conflicts else "retained_requirements_passed",
            "installed_packages": len(retained), "overlay_packages": len(overlay),
            "conflicts": conflicts, "installation_performed": False,
            "limitations": ["Overlay wheel metadata still requires post-install pip check",
                            "No import, native ABI or GPU validation"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    records = [{"name": dist.metadata["Name"], "version": dist.version,
                "requires": list(dist.requires or [])} for dist in importlib.metadata.distributions()]
    report = audit(records, overlay_versions(args.lock.read_text()))
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    raise SystemExit(bool(report["conflicts"]))


if __name__ == "__main__":
    main()
