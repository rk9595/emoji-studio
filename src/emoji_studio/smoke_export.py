"""Bounded private export prototype. No network adapter or cloud entry point."""

import hashlib
import io
import json
import re
from dataclasses import asdict, dataclass
from typing import Protocol

from PIL import Image

CAMPAIGN = "amd-api-smoke-v1"
REPOSITORY = "rk9595/emoji-studio-ops"
IMAGE_LIMIT = 4 * 1024 * 1024
MANIFEST_LIMIT = 16384
TIMEOUT = 10


class ExportError(RuntimeError):
    pass


def digest(content):
    return hashlib.sha256(content).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def require(condition, message):
    if not condition:
        raise ExportError(message)


def fingerprint(value, length=64):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{" + str(length) + r"}", value)


@dataclass(frozen=True)
class ExportBinding:
    allocation_id: str
    plan_sha256: str
    serving_sha256: str

    def __post_init__(self):
        require(bool(fingerprint(self.allocation_id, 32)
                     and fingerprint(self.plan_sha256) and fingerprint(self.serving_sha256)),
                "invalid_export_binding")

    @property
    def prefix(self):
        return f"{CAMPAIGN}/{self.allocation_id}"


@dataclass(frozen=True)
class Destination:
    repository: str
    prefix: str
    private: bool


class Reader(Protocol):
    """Future adapter must use authenticated fresh reads, not its upload cache."""

    def destination(self, *, timeout_seconds: int) -> Destination: ...

    def read(self, name: str, *, max_bytes: int, timeout_seconds: int) -> bytes: ...


class Writer(Protocol):
    def destination(self, *, timeout_seconds: int) -> Destination: ...

    def put_if_absent(self, name: str, content: bytes, *, sha256: str,
                      timeout_seconds: int) -> None:
        """Atomically create private object; existing bytes must match or fail.

        No overwrite, public link, implicit destination creation or write retry.
        """
        ...


@dataclass(frozen=True)
class Bundle:
    manifest: bytes
    artifacts: tuple[tuple[str, bytes], ...]


@dataclass(frozen=True)
class Ticket:
    """Persist outside the GPU before upload; not evidence of successful export."""

    binding: ExportBinding
    manifest_sha256: str

    def __post_init__(self):
        require(isinstance(self.binding, ExportBinding) and bool(fingerprint(self.manifest_sha256)),
                "invalid_export_ticket")


def _sanitize(content, extension):
    require(type(content) is bytes and 0 < len(content) <= IMAGE_LIMIT, "invalid_image_size")
    try:
        with Image.open(io.BytesIO(content)) as image:
            require(image.format == extension.upper() and image.size == (512, 512)
                    and image.mode == "RGBA" and getattr(image, "n_frames", 1) == 1,
                    "invalid_image_format")
            image.load()
            require(image.getchannel("A").getextrema()[0] == 0, "missing_transparency")
            # New pixel-only image: never propagate EXIF, text, ICC, XMP or tails.
            clean = Image.frombytes("RGBA", image.size, image.tobytes())
        buffer = io.BytesIO()
        clean.save(buffer, format=extension.upper(), lossless=True)
        result = buffer.getvalue()
        require(len(result) <= IMAGE_LIMIT, "invalid_image_size")
        return result
    except ExportError:
        raise
    except Exception:
        raise ExportError("image_decode_failed") from None


def prepare_export(binding: ExportBinding, images: dict, *, renderer: str) -> Bundle:
    """One/two surviving seed-7 image pairs; only fixed fields enter the manifest.

    Keys are original image indices 0/1, values exactly {'png': bytes, 'webp': bytes}.
    Raw prompts, job metadata, owner IDs, tokens, logs and DB files are not accepted.
    Sanitized hashes may differ from original hashes, both recorded for provenance.
    """
    require(isinstance(binding, ExportBinding), "invalid_export_binding")
    require(renderer in ("MockRenderer", "FluxRenderer"), "invalid_renderer")
    require(type(images) is dict and 1 <= len(images) <= 2
            and all(type(i) is int and i in (0, 1) for i in images), "invalid_image_indices")
    artifacts, rows = [], []
    for index, pair in sorted(images.items()):
        require(type(pair) is dict and set(pair) == {"png", "webp"}, "invalid_image_pair")
        for extension in ("png", "webp"):
            source = pair[extension]
            clean = _sanitize(source, extension)
            name = f"image-{index}.{extension}"
            artifacts.append((name, clean))
            rows.append({"name": name, "size": len(clean), "sha256": digest(clean),
                         "source_sha256": digest(source)})
    manifest = canonical({"version": 1, "campaign": CAMPAIGN, "binding": asdict(binding),
                          "renderer": renderer, "seed": 7, "artifacts": rows})
    return Bundle(manifest, tuple(artifacts))


def _parse_manifest(raw):
    require(type(raw) is bytes and 0 < len(raw) <= MANIFEST_LIMIT, "invalid_manifest_size")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_manifest_key")
            result[key] = value
        return result

    try:
        manifest = json.loads(raw, object_pairs_hook=unique)
        require(type(manifest) is dict and set(manifest) == {
            "version", "campaign", "binding", "renderer", "seed", "artifacts"
        }, "invalid_manifest_fields")
        require(type(manifest["version"]) is int and manifest["version"] == 1
                and manifest["campaign"] == CAMPAIGN
                and manifest["renderer"] in ("MockRenderer", "FluxRenderer")
                and type(manifest["seed"]) is int and manifest["seed"] == 7,
                "invalid_manifest_identity")
        binding = ExportBinding(**manifest["binding"])
        rows = manifest["artifacts"]
        require(type(rows) is list and len(rows) in (2, 4), "invalid_manifest_artifacts")
        names = []
        for row in rows:
            require(type(row) is dict and set(row) == {"name", "size", "sha256", "source_sha256"},
                    "invalid_artifact_fields")
            require(isinstance(row["name"], str)
                    and re.fullmatch(r"image-[01]\.(png|webp)", row["name"])
                    and type(row["size"]) is int and 0 < row["size"] <= IMAGE_LIMIT
                    and fingerprint(row["sha256"]) and fingerprint(row["source_sha256"]),
                    "invalid_artifact_descriptor")
            names.append(row["name"])
        require(names in (["image-0.png", "image-0.webp"], ["image-1.png", "image-1.webp"],
                          ["image-0.png", "image-0.webp", "image-1.png", "image-1.webp"]),
                "invalid_artifact_pairs")
        require(canonical(manifest) == raw, "manifest_not_canonical")
        return manifest, binding
    except ExportError:
        raise
    except Exception:
        raise ExportError("invalid_manifest") from None


def export_ticket(bundle: Bundle) -> Ticket:
    """Validate all bytes before any upload; return a restartable verification pin."""
    manifest, binding = _parse_manifest(bundle.manifest)
    rows = manifest["artifacts"]
    require(len(bundle.artifacts) == len(rows), "bundle_count_mismatch")
    for (name, content), row in zip(bundle.artifacts, rows, strict=True):
        require(name == row["name"] and type(content) is bytes and len(content) == row["size"]
                and digest(content) == row["sha256"], "bundle_hash_mismatch")
        # Re-encoding must reproduce pixel-only artifacts prepared in this runtime.
        require(_sanitize(content, name.rsplit(".", 1)[1]) == content, "bundle_not_sanitized")
    return Ticket(binding, digest(bundle.manifest))


def _scope(adapter, binding):
    try:
        target = adapter.destination(timeout_seconds=TIMEOUT)
    except Exception:
        raise ExportError("destination_lookup_failed") from None
    require(isinstance(target, Destination) and target.repository == REPOSITORY
            and target.prefix == binding.prefix and target.private is True,
            "private_destination_mismatch")


def upload_export(bundle: Bundle, writer: Writer) -> Ticket:
    """Upload once, manifest last. The returned ticket is still unverified."""
    ticket = export_ticket(bundle)
    _scope(writer, ticket.binding)
    for name, content in (*bundle.artifacts, ("manifest.json", bundle.manifest)):
        # Recheck private scope before each write, including after partial uploads.
        _scope(writer, ticket.binding)
        try:
            writer.put_if_absent(name, content, sha256=digest(content), timeout_seconds=TIMEOUT)
        except Exception:
            raise ExportError("storage_write_failed") from None
    return ticket


def _read(reader, name, limit):
    try:
        content = reader.read(name, max_bytes=limit, timeout_seconds=TIMEOUT)
    except Exception:
        raise ExportError("storage_read_failed") from None
    require(type(content) is bytes and len(content) <= limit, "invalid_download_size")
    return content


def verify_export(ticket: Ticket, reader: Reader):
    """Fresh verifier needs only the externally retained ticket, not local images."""
    _scope(reader, ticket.binding)
    raw = _read(reader, "manifest.json", MANIFEST_LIMIT)
    require(digest(raw) == ticket.manifest_sha256, "manifest_hash_mismatch")
    manifest, binding = _parse_manifest(raw)
    require(binding == ticket.binding, "download_binding_mismatch")
    for row in manifest["artifacts"]:
        _scope(reader, binding)
        content = _read(reader, row["name"], row["size"])
        require(len(content) == row["size"] and digest(content) == row["sha256"],
                "artifact_hash_mismatch")
    _scope(reader, binding)
    return {"status": "export_verified", "campaign": CAMPAIGN, "binding": asdict(binding),
            "repository": REPOSITORY, "prefix": binding.prefix,
            "manifest_sha256": ticket.manifest_sha256,
            "artifact_count": len(manifest["artifacts"]), "renderer": manifest["renderer"],
            "cleanup_verified": False, "smoke_accepted": False}


def transfer_and_verify(bundle: Bundle, writer: Writer, reader: Reader):
    require(writer is not reader, "separate_download_client_required")
    _, binding = _parse_manifest(bundle.manifest)
    _scope(reader, binding)  # Reject an unsafe reader scope before any writes.
    return verify_export(upload_export(bundle, writer), reader)
