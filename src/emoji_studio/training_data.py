"""Deterministic, caption-aware exports. This module never launches training."""

import hashlib
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import PIL
from PIL import Image, ImageOps

from .common import digest, read_json, write_json
from .curation import training_preflight


def export_training(root, curation_path, config_path, output):
    root, output = root.resolve(), output.resolve()
    if not output.is_relative_to(root) or output == root:
        raise ValueError("Training export must be inside the project")
    if output.exists():
        raise ValueError("Export already exists; use a new directory to preserve provenance")
    check = training_preflight(root, curation_path, config_path)
    if not check["data_ready"]:
        raise ValueError(f"Training data is not ready: {check['blocking_issues']}")
    config = read_json(config_path)
    resolution = config["resolution"]
    if type(resolution) is not int or not 16 <= resolution <= 4096:
        raise ValueError("Export resolution must be an integer between 16 and 4096")
    references = {row["id"]: row for row in read_json(root / "data/references.json")}
    document = read_json(curation_path)
    if digest(document) != check["curation_hash"]:
        raise ValueError("Curation changed during preflight")
    rows, metadata = [], defaultdict(list)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Publish only a complete export; failures leave no apparently usable dataset.
    with tempfile.TemporaryDirectory(prefix=".export-", dir=output.parent) as temporary:
        staging = Path(temporary) / "dataset"
        staging.mkdir()
        for review in sorted(document["rows"], key=lambda row: row["asset_id"]):
            if review["decision"] != "keep":
                continue
            source = references[review["asset_id"]]
            source_path = (root / source["path"]).resolve()
            if not source_path.is_relative_to(root):
                raise ValueError("Source path escapes the project")
            if hashlib.sha256(source_path.read_bytes()).hexdigest() != source["sha256"]:
                raise ValueError("Source changed during export")
            split = review["split"]
            # Hash-derived filenames never interpolate external IDs into paths.
            name = f"{digest(source['id'])}.png"
            target = staging / split / name
            target.parent.mkdir(exist_ok=True)
            with Image.open(source_path) as original:
                image = ImageOps.exif_transpose(original).convert("RGBA")
                native_size = list(image.size)
                background = Image.new("RGBA", image.size, "white")
                rgb = Image.alpha_composite(background, image).convert("RGB")
                rgb = ImageOps.pad(
                    rgb,
                    (resolution, resolution),
                    method=Image.Resampling.LANCZOS,
                    color="white",
                    centering=(0.5, 0.5),
                )
                rgb.save(target, format="PNG", optimize=False, compress_level=9)
            caption = review["caption"].strip()
            metadata[split].append({"file_name": name, "text": caption})
            rows.append(
                {
                    "asset_id": source["id"],
                    "concept": source["concept"],
                    "split": split,
                    "path": f"{split}/{name}",
                    "caption": caption,
                    "reviewer": review["reviewer"],
                    "source": source,
                    "native_size": native_size,
                    "allow_low_resolution": review["allow_low_resolution"],
                    "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                }
            )
        for split, records in metadata.items():
            (staging / split / "metadata.jsonl").write_text(
                "".join(json.dumps(row, sort_keys=True) + "\n" for row in records),
                encoding="utf-8",
            )
        audit = read_json(root / "data/asset-audit.json")
        notice = (root / audit["license_path"]).resolve()
        if not notice.is_relative_to(root):
            raise ValueError("License path escapes the project")
        shutil.copyfile(notice, staging / "LICENSE.source.txt")
        manifest = {
            "schema_version": 1,
            "training_authorized": False,
            "curation_hash": check["curation_hash"],
            "reference_manifest_hash": check["reference_manifest_hash"],
            "config_hash": digest(config),
            "pillow_version": PIL.__version__,
            "preprocessing": {
                "resolution": resolution,
                "mode": "RGB",
                "background": "#ffffff",
                "resize": "lanczos_contain_center_pad",
                "alpha": "composite_before_resize",
                "augmentation": "none",
            },
            "counts": {split: len(records) for split, records in sorted(metadata.items())},
            "files": {
                path.relative_to(staging).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(staging.rglob("*"))
                if path.is_file()
            },
            "rows": rows,
        }
        manifest["export_hash"] = digest(manifest)
        write_json(staging / "manifest.json", manifest)
        staging.rename(output)
    return {
        "path": str(output),
        "export_hash": manifest["export_hash"],
        "counts": manifest["counts"],
        "training_authorized": False,
    }


def verify_export(path):
    path = path.resolve()
    manifest = read_json(path / "manifest.json")
    payload = {key: value for key, value in manifest.items() if key != "export_hash"}
    if digest(payload) != manifest["export_hash"]:
        raise ValueError("Export manifest checksum failed")
    expected = set(manifest["files"]) | {"manifest.json"}
    actual = {item.relative_to(path).as_posix() for item in path.rglob("*") if item.is_file()}
    if actual != expected:
        raise ValueError("Export contains missing or unexpected files")
    for relative, checksum in manifest["files"].items():
        item = (path / relative).resolve()
        if not item.is_relative_to(path):
            raise ValueError("Export path escapes its directory")
        if hashlib.sha256(item.read_bytes()).hexdigest() != checksum:
            raise ValueError(f"Export checksum failed: {relative}")
    return manifest
