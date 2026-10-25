"""Bounded read-only GHCR checks for the single proposed private runtime image.

Default mode is offline. preflight is publication-gated; verify performs reads
only. No method creates/deletes packages, changes visibility or pushes images.
"""

import argparse
import base64
import datetime as dt
import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

OWNER = "rk9595"
PACKAGE = "emoji-studio-amd-runtime"
NAME = f"{OWNER}/{PACKAGE}"
IMAGE = f"ghcr.io/{NAME}"
ROOT = Path(__file__).resolve().parents[1]
LIMIT = 2 * 1024 * 1024
MANIFEST_TYPES = {"application/vnd.docker.distribution.manifest.v2+json",
                  "application/vnd.oci.image.manifest.v1+json"}
CONFIG_TYPES = {"application/vnd.docker.container.image.v1+json",
                "application/vnd.oci.image.config.v1+json"}
LAYER_TYPES = {"application/vnd.docker.image.rootfs.diff.tar.gzip",
               "application/vnd.oci.image.layer.v1.tar+gzip",
               "application/vnd.oci.image.layer.v1.tar+zstd"}


class Denied(RuntimeError):
    pass


def require(value, message):
    if not value:
        raise Denied(message)


def digest(raw):
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def valid_digest(value):
    return isinstance(value, str) and re.fullmatch(r"sha256:[0-9a-f]{64}", value)


def parse(raw):
    require(type(raw) is bytes and len(raw) <= LIMIT, "invalid_json_size")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result

    try:
        result = json.loads(raw, object_pairs_hook=unique)
        require(type(result) is dict, "expected_json_object")
        return result
    except Denied:
        raise
    except Exception:
        raise Denied("invalid_json") from None


@dataclass(frozen=True)
class Response:
    status: int
    body: bytes
    content_digest: str | None = None


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


def allowed_cdn(url):
    parts = urllib.parse.urlsplit(url)
    return (parts.scheme == "https" and parts.username is None and parts.password is None
            and parts.port in (None, 443) and parts.hostname is not None
            and (parts.hostname == "pkg-containers.githubusercontent.com"
                 or parts.hostname.endswith((".blob.core.windows.net", ".pkg-containers.githubusercontent.com"))))


def get(url, headers, *, config_blob=False):
    """No retries/proxies; only config blobs may follow bounded auth-free CDN hops."""
    parts = urllib.parse.urlsplit(url)
    require(parts.scheme == "https" and parts.netloc in ("api.github.com", "ghcr.io"),
            "untrusted_request_origin")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    deadline = time.monotonic() + 60
    for _ in range(3):
        try:
            request = urllib.request.Request(url, headers=headers, method="GET")
            try:
                response = opener.open(request, timeout=20)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                status = response.code
                if status in (301, 302, 303, 307, 308):
                    target = response.headers.get("Location", "")
                    require(config_blob and allowed_cdn(target), "redirect_denied")
                    url, headers = target, {"Accept": "application/octet-stream"}
                    require(time.monotonic() < deadline, "read_deadline")
                    continue
                chunks, length = [], 0
                while True:
                    require(time.monotonic() < deadline, "read_deadline")
                    chunk = response.read(min(65536, LIMIT + 1 - length))
                    if not chunk:
                        break
                    chunks.append(chunk)
                    length += len(chunk)
                    require(length <= LIMIT, "response_too_large")
                return Response(status, b"".join(chunks), response.headers.get("Docker-Content-Digest"))
        except Denied:
            raise
        except Exception:
            raise Denied("registry_transport_failed") from None
    raise Denied("redirect_limit")


class Registry:
    def __init__(self, token, actor, fetch=get):
        require(bool(token) and re.fullmatch(r"[A-Za-z0-9-]{1,100}", actor), "credentials_missing")
        self.token, self.actor, self.fetch = token, actor, fetch

    def package(self):
        return self.fetch(f"https://api.github.com/users/{OWNER}/packages/container/{PACKAGE}",
                          {"Authorization": "Bearer " + self.token,
                           "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})

    def pull_token(self, *, anonymous=False):
        headers = {"Accept": "application/json"}
        if not anonymous:
            credential = base64.b64encode(f"{self.actor}:{self.token}".encode()).decode()
            headers["Authorization"] = "Basic " + credential
        query = urllib.parse.urlencode({"service": "ghcr.io", "scope": f"repository:{NAME}:pull"})
        response = self.fetch("https://ghcr.io/token?" + query, headers)
        if anonymous and response.status in (401, 403):
            return None
        require(response.status == 200, "token_request_failed")
        token = parse(response.body).get("token")
        require(isinstance(token, str) and 0 < len(token) <= 65536, "invalid_registry_token")
        return token

    def manifest(self, reference, token):
        require(valid_digest(reference) or re.fullmatch(r"cpu-[0-9a-f]{40}-[1-9][0-9]{0,19}", reference),
                "invalid_manifest_reference")
        return self.fetch(f"https://ghcr.io/v2/{NAME}/manifests/{reference}",
                          {"Authorization": "Bearer " + token, "Accept": ", ".join(sorted(MANIFEST_TYPES))})

    def config(self, checksum, token):
        require(valid_digest(checksum), "invalid_config_digest")
        return self.fetch(f"https://ghcr.io/v2/{NAME}/blobs/{checksum}",
                          {"Authorization": "Bearer " + token}, config_blob=True)


def private_package(response, *, empty=False):
    require(response.status == 200, "package_lookup_failed")
    package = parse(response.body)
    require(package.get("name") == PACKAGE and package.get("package_type") == "container"
            and package.get("owner", {}).get("login") == OWNER
            and package.get("visibility") == "private", "private_package_identity_mismatch")
    require(type(package.get("version_count")) is int
            and package["version_count"] == (0 if empty else 1), "unexpected_package_versions")
    return package


def preflight(client):
    response = client.package()
    if response.status == 404:
        # Only the one fixed owner/name is allowed. 404 may hide missing access;
        # it does not establish working publication credentials. Push can fail.
        return {"status": "new_package_candidate", "image": IMAGE}
    private_package(response, empty=True)
    return {"status": "empty_private_package", "image": IMAGE}


def descriptor(value, media_types, max_size):
    require(type(value) is dict and value.get("mediaType") in media_types
            and valid_digest(value.get("digest")) and type(value.get("size")) is int
            and 0 < value["size"] <= max_size and "urls" not in value, "invalid_descriptor")


def verify_remote(client, manifest_digest, config_digest):
    require(valid_digest(manifest_digest) and valid_digest(config_digest), "invalid_expected_digest")
    private_package(client.package())
    token = client.pull_token()
    response = client.manifest(manifest_digest, token)
    require(response.status == 200 and digest(response.body) == manifest_digest
            and response.content_digest == manifest_digest, "manifest_digest_mismatch")
    manifest = parse(response.body)
    require(type(manifest.get("schemaVersion")) is int and manifest["schemaVersion"] == 2
            and manifest.get("mediaType") in MANIFEST_TYPES, "unsupported_manifest")
    descriptor(manifest.get("config"), CONFIG_TYPES, LIMIT)
    require(manifest["config"]["digest"] == config_digest, "config_identity_mismatch")
    layers = manifest.get("layers")
    require(type(layers) is list and 1 <= len(layers) <= 32, "invalid_layers")
    for layer in layers:
        descriptor(layer, LAYER_TYPES, 20 * 1024**3)
    require(sum(layer["size"] for layer in layers) <= 20 * 1024**3, "image_size_exceeded")
    config_response = client.config(config_digest, token)
    require(config_response.status == 200 and digest(config_response.body) == config_digest
            and len(config_response.body) == manifest["config"]["size"], "config_digest_mismatch")
    config = parse(config_response.body)
    require(config.get("os") == "linux" and config.get("architecture") == "amd64", "wrong_platform")
    rootfs = config.get("rootfs", {})
    require(rootfs.get("type") == "layers" and type(rootfs.get("diff_ids")) is list
            and len(rootfs["diff_ids"]) == len(layers)
            and all(valid_digest(value) for value in rootfs["diff_ids"]), "invalid_rootfs")
    # Public registries also challenge anonymous requests. Follow the anonymous
    # token flow; only its denial or subsequent manifest denial establishes this
    # check. Never reuse authenticated headers/tokens for the anonymous probe.
    anonymous = client.pull_token(anonymous=True)
    if anonymous is not None:
        denied = client.manifest(manifest_digest, anonymous)
        require(denied.status in (401, 403), "anonymous_access_not_denied")
    private_package(client.package())
    return {"status": "remote_manifest_verified", "image": IMAGE,
            "manifest_digest": manifest_digest, "config_digest": config_digest,
            "platform": "linux/amd64", "visibility": "private", "anonymous_access_denied": True,
            "compressed_layer_bytes": sum(layer["size"] for layer in layers),
            "fresh_pull_verified": False, "gpu_validated": False}


def proposal(root=ROOT):
    value = parse((Path(root) / "configs/amd-image-retention-proposal.json").read_bytes())
    require(value["recommended_destination"] == IMAGE and value["required_visibility"] == "private"
            and value["required_platform"] == "linux/amd64"
            and value["gpu_execution_authorized"] is False and value["paid_execution_authorized"] is False,
            "retention_scope_changed")
    require(value["retention_limits"] == {
        "new_package_names": 1, "new_versions": 1, "mutable_latest_tag": False,
        "overwrite_existing_tag": False, "delete_existing_versions": False,
        "automatic_rebuild_or_push_retries": 0, "paid_fallback": False,
    }, "retention_limits_changed")
    return value


def publication_tag(value, environment, today=None):
    require(value["publication_authorized"] is True, "publication_not_authorized")
    today = today or dt.datetime.now(dt.UTC).date().isoformat()
    require(value.get("pricing_checked_on") == today, "pricing_recheck_required")
    head = environment.get("GITHUB_SHA", "")
    run_id = environment.get("GITHUB_RUN_ID", "")
    require(re.fullmatch(r"[0-9a-f]{40}", head) and re.fullmatch(r"[1-9][0-9]{0,19}", run_id)
            and environment.get("APPROVED_SOURCE") == head
            and environment.get("GITHUB_REPOSITORY") == "rk9595/emoji-studio"
            and environment.get("GITHUB_RUN_ATTEMPT") == "1", "unapproved_run_identity")
    return f"cpu-{head}-{run_id}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "preflight", "verify"), nargs="?", default="check")
    parser.add_argument("--manifest-digest")
    parser.add_argument("--config-digest")
    args = parser.parse_args()
    try:
        value = proposal()
        if args.command == "check":
            result = {"status": "publication_ready" if value["publication_authorized"] else "prepared_only",
                      "publication_authorized": value["publication_authorized"],
                      "image": IMAGE, "network_calls": 0}
        else:
            tag = publication_tag(value, os.environ) if args.command == "preflight" else None
            client = Registry(os.environ.get("GH_TOKEN", ""), os.environ.get("GITHUB_ACTOR", ""))
            if args.command == "preflight":
                result = {**preflight(client), "tag": tag}
            else:
                result = verify_remote(client, args.manifest_digest, args.config_digest)
        print(json.dumps(result, sort_keys=True))
    except Exception as error:
        # Deliberately omit URLs, response bodies, exceptions and token values.
        print(json.dumps({"status": "failed", "code": str(error) if isinstance(error, Denied)
                          else "retention_check_failed"}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
