import hashlib
import io
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import PurePosixPath

from PIL import Image

from .common import digest, now, read_json, write_json


def download(url):
    request = urllib.request.Request(url, headers={"User-Agent": "emoji-studio/0.1"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=40) as response:
                return response.read()
        except (urllib.error.URLError, TimeoutError):
            if attempt == 2:
                raise
            time.sleep(1 + attempt)


def raw_url(source, path):
    encoded = urllib.parse.quote(path, safe="/")
    return (
        f"https://raw.githubusercontent.com/{source['repository']}/{source['revision']}/{encoded}"
    )


def git_blob_sha(payload):
    return hashlib.sha1(b"blob " + str(len(payload)).encode() + b"\0" + payload).hexdigest()


def inventory_tree(tree, source):
    if tree.get("truncated"):
        raise ValueError("GitHub returned a truncated tree; refusing an incomplete inventory")
    rows = []
    for item in tree["tree"]:
        path = PurePosixPath(item["path"])
        if item["type"] != "blob" or path.suffix.lower() != ".png":
            continue
        if len(path.parts) < 4 or path.parts[0] != "assets" or "3D" not in path.parts:
            continue
        if ".." in path.parts or path.is_absolute():
            raise ValueError("Unsafe upstream asset path")
        concept = path.parts[1]
        tone = path.parts[2] if len(path.parts) > 4 else "Default"
        rows.append(
            {
                "id": digest({"repo": source["repository"], "path": str(path)})[:16],
                "concept": concept,
                "concept_family": concept.casefold(),
                "variant": "3D",
                "tone": tone,
                "source_path": str(path),
                "source_blob_sha": item["sha"],
                "source_revision": source["revision"],
                "source_url": raw_url(source, str(path)),
                "bytes": item.get("size"),
                "license": source["license"],
            }
        )
    return sorted(rows, key=lambda row: row["source_path"])


def select_references(inventory, priorities, limit):
    available = {}
    for row in inventory:
        if row["tone"] == "Default":
            available.setdefault(row["concept"].casefold(), row)
    selected = []
    for name in priorities:
        row = available.get(name.casefold())
        if row and row not in selected:
            selected.append(row)
    # Keep the pilot intentional; missing priority assets are reported, not replaced silently.
    return selected[:limit]


def inspect_png(payload):
    with Image.open(io.BytesIO(payload)) as image:
        if image.format != "PNG":
            raise ValueError("Expected PNG asset")
        image.load()
        rgba = image.convert("RGBA")
        alpha = rgba.getchannel("A")
        histogram = alpha.histogram()
        total = rgba.width * rgba.height
        bounds = alpha.getbbox()
        return {
            "width": rgba.width,
            "height": rgba.height,
            "has_transparency": histogram[255] < total,
            "transparent_fraction": round(histogram[0] / total, 4),
            "foreground_bbox": bounds,
            "low_resolution_for_512_training": min(rgba.size) < 512,
        }


def fetch_assets(root, limit=64):
    if limit < 1:
        raise ValueError("limit must be positive")
    source = read_json(root / "configs/source.json")
    cache = root / "data/sources/fluent" / source["revision"]
    cache.mkdir(parents=True, exist_ok=True)
    tree_path = cache / "tree.json"
    if tree_path.exists():
        tree = read_json(tree_path)
    else:
        url = f"https://api.github.com/repos/{source['repository']}/git/trees/{source['revision']}?recursive=1"
        tree = json.loads(download(url))
        write_json(tree_path, tree)
    inventory = inventory_tree(tree, source)
    write_json(root / "data/inventory.json", inventory)
    license_path = cache / "LICENSE"
    if not license_path.exists():
        license_path.write_bytes(download(raw_url(source, "LICENSE")))
    selected = select_references(inventory, source["priority_concepts"], limit)
    if not selected:
        raise ValueError("No preferred default-tone assets found; inspect inventory.json")

    def fetch_one(row):
        output = root / "data/assets" / (row["id"] + ".png")
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = output.read_bytes() if output.exists() else download(row["source_url"])
        if git_blob_sha(payload) != row["source_blob_sha"]:
            raise ValueError(f"Asset checksum mismatch: {row['source_path']}")
        details = inspect_png(payload)
        if not output.exists():
            output.write_bytes(payload)
        metadata_path = cache / "metadata" / (row["id"] + ".json")
        if metadata_path.exists():
            metadata = read_json(metadata_path)
        else:
            metadata = json.loads(
                download(raw_url(source, f"assets/{row['concept']}/metadata.json"))
            )
            write_json(metadata_path, metadata)
        return {
            **row,
            **details,
            "path": output.relative_to(root).as_posix(),
            "sha256": hashlib.sha256(payload).hexdigest(),
            "group": metadata.get("group", "Uncategorized"),
            "keywords": metadata.get("keywords", []),
            "caption": f"{metadata.get('cldr', row['concept'])}, isolated emoji illustration",
            "caption_status": "draft_metadata_only",
            "caption_provenance": "upstream_metadata_plus_template_v1",
            "review_status": "unreviewed",
            "split": "unassigned",
            "training_ready": False,
            "transformations": [],
        }

    with ThreadPoolExecutor(max_workers=4) as pool:
        references = list(pool.map(fetch_one, selected))
    write_json(root / "data/references.json", references)
    found = {row["concept"].casefold() for row in inventory}
    summary = {
        "created_at": now(),
        "source": source,
        "inventory_assets": len(inventory),
        "distinct_concepts": len({row["concept_family"] for row in inventory}),
        "reference_assets": len(references),
        "reference_dimensions": dict(Counter(f"{r['width']}x{r['height']}" for r in references)),
        "low_resolution_references": sum(r["low_resolution_for_512_training"] for r in references),
        "groups": dict(Counter(r["group"] for r in references)),
        "missing_priority_concepts": [
            n for n in source["priority_concepts"] if n.casefold() not in found
        ],
        "training_ready_assets": 0,
        "license_path": license_path.relative_to(root).as_posix(),
        "manifest_hash": digest(references),
    }
    write_json(root / "data/asset-audit.json", summary)
    return summary
