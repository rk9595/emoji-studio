"""Bounded training images rendered from the OFL-licensed Noto 3D font.

The raw 3D PNG tree is not an input. These are graphical documents drawn from
the font, which OFL keeps under a different rule from the font software itself.
The font file is not copied into the training export.
"""

import hashlib
import io
import json
import os
import struct
import unicodedata
from pathlib import Path

import PIL
from PIL import Image, ImageOps

from .common import digest, read_json, write_json

FONT_SHA256 = "0fdfec3dbefb214750465b5c17ac8f7c47286fc0c88d8605c12cd45e86613f7c"
FONT_BYTES = 140952312
LICENSE_SHA256 = "6a73f9541c2de74158c0e7cf6b0a58ef774f5a780bf191f2d7ec9cc53efe2bf2"
SUBSET_COUNT = 128
CAPTION_STATUS = "metadata_checked_visual_details_not_individually_reviewed"
RESOLUTION = 512


def emoji_codepoint(codepoint):
    """Emoji blocks in this 3D font. Excludes punctuation and Arabic presentation forms."""
    return 0x2600 <= codepoint <= 0x27BF or 0x1F000 <= codepoint <= 0x1FAFF


def evenly_spaced(values, count):
    if type(count) is not int or count < 2:
        raise ValueError("Subset count must be an integer of at least 2")
    if len(values) < count:
        raise ValueError("Font exposes fewer glyphs than the bounded subset")
    chosen = []
    previous = None
    for index in range(count):
        item = values[(index * (len(values) - 1)) // (count - 1)]
        if item == previous:
            raise ValueError("Subset collapsed")
        chosen.append(item)
        previous = item
    return chosen


def _tables(data):
    if data[:4] not in (b"\x00\x01\x00\x00", b"OTTO"):
        raise ValueError("Not an SFNT font")
    count = struct.unpack(">H", data[4:6])[0]
    tables = {}
    offset = 12
    for _ in range(count):
        tag, _checksum, start, length = struct.unpack(">4sIII", data[offset:offset + 16])
        tables[tag.decode("ascii")] = data[start:start + length]
        offset += 16
    return tables


def _codepoints(cmap):
    subtables = struct.unpack(">H", cmap[2:4])[0]
    groups = None
    for index in range(subtables):
        _platform, _encoding, offset = struct.unpack(">HHI", cmap[4 + 8 * index:12 + 8 * index])
        if struct.unpack(">H", cmap[offset:offset + 2])[0] != 12:
            continue
        total = struct.unpack(">I", cmap[offset + 12:offset + 16])[0]
        groups = []
        cursor = offset + 16
        for _ in range(total):
            groups.append(struct.unpack(">III", cmap[cursor:cursor + 12]))
            cursor += 12
    if not groups:
        raise ValueError("Font has no Unicode cmap")
    found = []
    for start, end, glyph in groups:
        for codepoint in range(start, end + 1):
            if codepoint < 32 or 0xE000 <= codepoint <= 0xF8FF:
                continue
            found.append((codepoint, glyph + (codepoint - start)))
    return found


def _largest_strike(sbix, glyphs):
    strikes = struct.unpack(">I", sbix[4:8])[0]
    offsets = struct.unpack(f">{strikes}I", sbix[8:8 + 4 * strikes])
    chosen = None
    for offset in offsets:
        ppem = struct.unpack(">H", sbix[offset:offset + 2])[0]
        glyph_offsets = struct.unpack(f">{glyphs + 1}I", sbix[offset + 4:offset + 4 + 4 * (glyphs + 1)])
        if chosen is None or ppem > chosen[0]:
            chosen = (ppem, offset, glyph_offsets)
    if chosen is None:
        raise ValueError("Font has no bitmap strike")
    return chosen


def rendered_glyphs(font_path, license_path):
    font_bytes = Path(font_path).read_bytes()
    license_bytes = Path(license_path).read_bytes()
    if (hashlib.sha256(font_bytes).hexdigest() != FONT_SHA256 or len(font_bytes) != FONT_BYTES
            or hashlib.sha256(license_bytes).hexdigest() != LICENSE_SHA256):
        raise ValueError("Noto 3D font or OFL text differs from the pinned revision")
    tables = _tables(font_bytes)
    codepoints = _codepoints(tables["cmap"])
    glyphs = struct.unpack(">H", tables["maxp"][4:6])[0]
    ppem, strike, offsets = _largest_strike(tables["sbix"], glyphs)
    available = []
    images = {}
    for codepoint, glyph_id in codepoints:
        if not 0 <= glyph_id < glyphs:
            continue
        start, end = offsets[glyph_id], offsets[glyph_id + 1]
        if end - start <= 8:
            continue
        record = tables["sbix"][strike + start:strike + end]
        kind = record[4:8]
        if kind != b"png ":
            continue
        if not emoji_codepoint(codepoint):
            continue
        available.append(codepoint)
        images[codepoint] = record[8:]
    selected = evenly_spaced(available, SUBSET_COUNT)
    rows = []
    for codepoint in selected:
        name = unicodedata.name(chr(codepoint), f"U+{codepoint:04X}")
        rows.append({
            "codepoint": codepoint,
            "name": name,
            "ppem": ppem,
            "png": images[codepoint],
        })
    return rows, license_bytes


def _rgb(png):
    with Image.open(io.BytesIO(png)) as original:
        image = ImageOps.exif_transpose(original).convert("RGBA")
        if image.size != (128, 128):
            raise ValueError("Noto bitmap is not 128px")
        flat = Image.alpha_composite(Image.new("RGBA", image.size, "white"), image).convert("RGB")
        return ImageOps.pad(flat, (RESOLUTION, RESOLUTION), method=Image.Resampling.LANCZOS,
                            color="white", centering=(0.5, 0.5))


def export_subset(font_path, license_path, output):
    output = Path(output)
    if output.exists():
        raise ValueError("Noto export already exists")
    glyphs, license_bytes = rendered_glyphs(font_path, license_path)
    rows, metadata, files = [], [], {}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging_parent = output.parent
    temporary = staging_parent / f".noto-{os.getpid()}"
    if temporary.exists():
        raise ValueError("Noto staging directory already exists")
    try:
        train = temporary / "train"
        train.mkdir(parents=True)
        for glyph in glyphs:
            image = _rgb(glyph["png"])
            buffer = io.BytesIO()
            image.save(buffer, format="PNG", optimize=False, compress_level=9)
            payload = buffer.getvalue()
            name = hashlib.sha256(payload).hexdigest() + ".png"
            (train / name).write_bytes(payload)
            codepoint = glyph["codepoint"]
            asset_id = hashlib.sha256(f"noto-3d-128:{codepoint:x}".encode()).hexdigest()[:16]
            caption = glyph["name"].lower() + ", noto 3D emoji illustration"
            metadata.append({"asset_id": asset_id, "file_name": name, "text": caption})
            rows.append({
                "asset_id": asset_id,
                "concept": "Noto " + glyph["name"].lower(),
                "tone": "Default",
                "family_id": f"noto-{codepoint:05x}",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "pixel_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                "source_sha256": hashlib.sha256(glyph["png"]).hexdigest(),
                "split": "train",
                "caption": caption,
                "caption_status": CAPTION_STATUS,
                "included": True,
                "path": f"train/{name}",
                "codepoint": codepoint,
            })
        (train / "metadata.jsonl").write_text(
            "".join(json.dumps(row, sort_keys=True) + "\n" for row in metadata), encoding="utf-8")
        (temporary / "LICENSE.noto-ofl.txt").write_bytes(license_bytes)
        for path in sorted(temporary.rglob("*")):
            if path.is_file():
                files[path.relative_to(temporary).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
        manifest = {
            "schema_version": 1,
            "training_authorized": False,
            "source": "googlefonts/noto-emoji 3D/fonts/Noto-3D-128-noflags.ttf",
            "font_sha256": FONT_SHA256,
            "license": "SIL-OFL-1.1",
            "license_sha256": LICENSE_SHA256,
            "pillow_version": PIL.__version__,
            "subset_count": SUBSET_COUNT,
            "subset_policy": "evenly-spaced-unicode-codepoints-v1",
            "preprocessing": {
                "resolution": RESOLUTION, "mode": "RGB", "background": "#ffffff",
                "resize": "lanczos_contain_center_pad", "alpha": "composite_before_resize",
                "augmentation": "none",
            },
            "counts": {"train": len(rows)},
            "files": files,
            "rows": rows,
        }
        manifest["export_hash"] = digest(manifest)
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(output)
    except Exception:
        if temporary.exists():
            for path in sorted(temporary.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
        raise
    return manifest


def combine_exports(fluent, noto, output):
    """Hardlink the frozen Fluent export and add the Noto training rows."""
    fluent, noto, output = Path(fluent), Path(noto), Path(output)
    if output.exists():
        raise ValueError("Combined export already exists")
    fluent_manifest = read_json(fluent / "manifest.json")
    noto_manifest = read_json(noto / "manifest.json")
    if noto_manifest.get("font_sha256") != FONT_SHA256 or noto_manifest["counts"]["train"] != SUBSET_COUNT:
        raise ValueError("Unexpected Noto export")
    fluent_ids = {row["asset_id"] for row in fluent_manifest["rows"]}
    fluent_families = {row["family_id"] for row in fluent_manifest["rows"]}
    noto_rows = [row for row in noto_manifest["rows"] if row["included"] and row["split"] == "train"]
    if len(noto_rows) != SUBSET_COUNT:
        raise ValueError("Noto training rows differ")
    if any(row["asset_id"] in fluent_ids or row["family_id"] in fluent_families for row in noto_rows):
        raise ValueError("Noto identity collides with Fluent")
    output.parent.mkdir(parents=True, exist_ok=True)
    for relative in fluent_manifest["files"]:
        if relative == "train/metadata.jsonl":
            continue
        source = fluent / relative
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        os.link(source, target)
    files = dict(fluent_manifest["files"])
    for row in noto_rows:
        source = noto / row["path"]
        target = output / row["path"]
        if target.exists():
            raise ValueError("Noto filename collides with Fluent")
        os.link(source, target)
        files[row["path"]] = hashlib.sha256(target.read_bytes()).hexdigest()
    license_target = output / "LICENSE.noto-ofl.txt"
    os.link(noto / "LICENSE.noto-ofl.txt", license_target)
    files["LICENSE.noto-ofl.txt"] = hashlib.sha256(license_target.read_bytes()).hexdigest()
    metadata = output / "train" / "metadata.jsonl"
    noto_meta = (noto / "train" / "metadata.jsonl").read_text(encoding="utf-8")
    metadata.write_text((fluent / "train" / "metadata.jsonl").read_text(encoding="utf-8") + noto_meta,
                        encoding="utf-8")
    files["train/metadata.jsonl"] = hashlib.sha256(metadata.read_bytes()).hexdigest()
    rows = list(fluent_manifest["rows"]) + noto_rows
    manifest = {
        "schema_version": 1,
        "training_authorized": False,
        "base_export_hash": fluent_manifest["export_hash"],
        "noto_export_hash": noto_manifest["export_hash"],
        "font_sha256": FONT_SHA256,
        "pillow_version": PIL.__version__,
        "preprocessing": fluent_manifest["preprocessing"],
        "counts": {
            "train": sum(row["split"] == "train" and row["included"] for row in rows),
            "validation": sum(row["split"] == "validation" and row["included"] for row in rows),
        },
        "files": files,
        "rows": rows,
    }
    if manifest["counts"]["train"] != fluent_manifest["counts"]["train"] + SUBSET_COUNT:
        raise ValueError("Combined training count differs")
    manifest["export_hash"] = digest({key: value for key, value in manifest.items()})
    write_json(output / "manifest.json", manifest)
    return manifest
