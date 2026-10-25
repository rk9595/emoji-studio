import importlib.util
import io
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("ghcr_verifier", ROOT / "scripts/verify_ghcr_retention.py")
v = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = v
spec.loader.exec_module(v)


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def package(*, visibility="private", count=1):
    return v.Response(200, encode({"name": v.PACKAGE, "package_type": "container",
                                  "owner": {"login": v.OWNER}, "visibility": visibility,
                                  "version_count": count}))


class FakeRegistry:
    def __init__(self):
        self.config_body = encode({"architecture": "amd64", "os": "linux",
                                   "rootfs": {"type": "layers", "diff_ids": ["sha256:" + "a" * 64]}})
        self.config_digest = v.digest(self.config_body)
        self.manifest_value = {
            "schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
            "config": {"mediaType": "application/vnd.docker.container.image.v1+json",
                       "digest": self.config_digest, "size": len(self.config_body)},
            "layers": [{"mediaType": "application/vnd.docker.image.rootfs.diff.tar.gzip",
                        "digest": "sha256:" + "b" * 64, "size": 1024}],
        }
        self.rehash()
        self.package_responses = [package(), package()]
        self.anonymous_token = None
        self.anonymous_status = 403
        self.calls = []

    def rehash(self):
        self.manifest_body = encode(self.manifest_value)
        self.manifest_digest = v.digest(self.manifest_body)
        self.header_digest = self.manifest_digest

    def package(self):
        self.calls.append("package")
        return self.package_responses.pop(0)

    def pull_token(self, *, anonymous=False):
        self.calls.append("anonymous_token" if anonymous else "authenticated_token")
        return self.anonymous_token if anonymous else "auth-token"

    def manifest(self, reference, token):
        self.calls.append(("manifest", reference, token))
        if token != "auth-token":
            return v.Response(self.anonymous_status, b"")
        return v.Response(200, self.manifest_body, self.header_digest)

    def config(self, checksum, token):
        self.calls.append(("config", checksum, token))
        return v.Response(200, self.config_body)


class MetadataTest(unittest.TestCase):
    def verify(self, client):
        return v.verify_remote(client, client.manifest_digest, client.config_digest)

    def test_exact_private_single_platform_manifest_and_config(self):
        client = FakeRegistry()
        result = self.verify(client)
        self.assertEqual(result["status"], "remote_manifest_verified")
        self.assertEqual(result["config_digest"], client.config_digest)
        self.assertEqual(result["compressed_layer_bytes"], 1024)
        self.assertFalse(result["fresh_pull_verified"])
        self.assertFalse(result["gpu_validated"])
        self.assertEqual(client.calls[-1], "package")
        self.assertIn("anonymous_token", client.calls)

    def test_public_wrong_owner_wrong_name_and_version_counts_fail(self):
        changes = ({"visibility": "public"}, {"visibility": "internal"},
                   {"owner": {"login": "other"}}, {"name": "other"},
                   {"package_type": "npm"}, {"version_count": 0},
                   {"version_count": 2}, {"version_count": True})
        for change in changes:
            with self.subTest(change=change):
                client = FakeRegistry()
                row = json.loads(package().body)
                client.package_responses = [v.Response(200, encode({**row, **change}))]
                with self.assertRaises(v.Denied):
                    self.verify(client)
                self.assertEqual(client.calls, ["package"])

    def test_manifest_bytes_and_digest_header_are_both_checked(self):
        for field, value in (("manifest_body", b"changed"), ("header_digest", None),
                             ("header_digest", "sha256:" + "f" * 64)):
            with self.subTest(field=field):
                client = FakeRegistry()
                setattr(client, field, value)
                with self.assertRaisesRegex(v.Denied, "manifest_digest"):
                    self.verify(client)

    def test_config_bytes_length_and_identity_must_match(self):
        for change in ("bytes", "size", "identity"):
            with self.subTest(change=change):
                client = FakeRegistry()
                if change == "bytes":
                    client.config_body += b" "
                elif change == "size":
                    client.manifest_value["config"]["size"] += 1
                    client.rehash()
                else:
                    client.manifest_value["config"]["digest"] = "sha256:" + "c" * 64
                    client.rehash()
                with self.assertRaises(v.Denied):
                    self.verify(client)

    def test_wrong_platform_and_rootfs_fail_even_with_matching_hashes(self):
        for change in ({"os": "windows"}, {"architecture": "arm64"},
                       {"rootfs": {"type": "layers", "diff_ids": []}},
                       {"rootfs": {"type": "layers", "diff_ids": ["invalid"]}}):
            with self.subTest(change=change):
                client = FakeRegistry()
                client.config_body = encode({**json.loads(client.config_body), **change})
                client.config_digest = v.digest(client.config_body)
                client.manifest_value["config"].update(digest=client.config_digest, size=len(client.config_body))
                client.rehash()
                with self.assertRaises(v.Denied):
                    self.verify(client)

    def test_indexes_foreign_layers_bad_sizes_and_schema_fail(self):
        for change in ("index", "foreign", "zero", "too_large", "bool", "layers", "urls"):
            with self.subTest(change=change):
                client = FakeRegistry()
                if change == "index":
                    client.manifest_value["mediaType"] = "application/vnd.oci.image.index.v1+json"
                elif change == "foreign":
                    client.manifest_value["layers"][0]["mediaType"] = "foreign"
                elif change == "zero":
                    client.manifest_value["layers"][0]["size"] = 0
                elif change == "too_large":
                    client.manifest_value["layers"][0]["size"] = 21 * 1024**3
                elif change == "bool":
                    client.manifest_value["schemaVersion"] = True
                elif change == "layers":
                    client.manifest_value["layers"] = []
                else:
                    client.manifest_value["layers"][0]["urls"] = ["https://example.invalid"]
                client.rehash()
                with self.assertRaises(v.Denied):
                    self.verify(client)

    def test_anonymous_token_success_is_followed_by_actual_manifest_probe(self):
        client = FakeRegistry()
        client.anonymous_token = "anonymous-token"
        self.assertTrue(self.verify(client)["anonymous_access_denied"])
        self.assertIn(("manifest", client.manifest_digest, "anonymous-token"), client.calls)

    def test_public_access_or_ambiguous_anonymous_result_never_passes(self):
        for status in (200, 302, 404, 429, 500):
            with self.subTest(status=status):
                client = FakeRegistry()
                client.anonymous_token, client.anonymous_status = "anonymous-token", status
                with self.assertRaisesRegex(v.Denied, "anonymous_access"):
                    self.verify(client)

    def test_privacy_is_rechecked_after_verification(self):
        client = FakeRegistry()
        client.package_responses = [package(), package(visibility="public")]
        with self.assertRaises(v.Denied):
            self.verify(client)

    def test_preflight_refuses_existing_versions_and_uncertain_lookup_errors(self):
        for response in (package(), package(count=2), package(visibility="public", count=0),
                         v.Response(401, b""), v.Response(403, b""), v.Response(500, b"")):
            with self.subTest(status=response.status):
                client = FakeRegistry()
                client.package_responses = [response]
                with self.assertRaises(v.Denied):
                    v.preflight(client)
                self.assertEqual(client.calls, ["package"])
        for response in (v.Response(404, b""), package(count=0)):
            client = FakeRegistry()
            client.package_responses = [response]
            self.assertEqual(v.preflight(client)["image"], v.IMAGE)

    def test_duplicate_json_and_oversized_data_fail(self):
        for raw in (b'{"a":1,"a":2}', b"[]", b"broken", b" " * (v.LIMIT + 1)):
            with self.subTest(size=len(raw)), self.assertRaises(v.Denied):
                v.parse(raw)


class FakeHTTP(io.BytesIO):
    def __init__(self, status=200, body=b"{}", headers=None):
        super().__init__(body)
        self.code, self.headers = status, headers or {}


class TransportTest(unittest.TestCase):
    def test_anonymous_auth_has_no_credentials_and_denial_is_not_404(self):
        for status in (401, 403, 404, 429, 500, 200):
            calls = []

            def fetch(url, headers):
                calls.append((url, headers))
                return v.Response(status, b'{"token":"anonymous"}')

            client = v.Registry("secret-token", "rk9595", fetch=fetch)
            if status in (401, 403):
                self.assertIsNone(client.pull_token(anonymous=True))
            elif status == 200:
                self.assertEqual(client.pull_token(anonymous=True), "anonymous")
            else:
                with self.assertRaises(v.Denied):
                    client.pull_token(anonymous=True)
            self.assertNotIn("Authorization", calls[0][1])
            self.assertNotIn("secret-token", str(calls))

    def test_blob_cdn_redirect_strips_authorization(self):
        responses = [FakeHTTP(307, headers={"Location": "https://pkg-containers.githubusercontent.com/blob?sig=private"}),
                     FakeHTTP(200, body=b"config")]
        with patch.object(v.urllib.request, "build_opener") as factory:
            opener = factory.return_value
            opener.open.side_effect = responses
            result = v.get("https://ghcr.io/v2/x/blobs/sha256:abc", {"Authorization": "Bearer secret"},
                           config_blob=True)
            self.assertEqual(result.body, b"config")
            request = opener.open.call_args_list[1].args[0]
            self.assertIsNone(request.get_header("Authorization"))
            self.assertEqual(opener.open.call_count, 2)

    def test_redirects_cannot_change_manifest_token_origin_or_use_arbitrary_hosts(self):
        for target, blob in (("https://evil.invalid/", True),
                             ("http://pkg-containers.githubusercontent.com/blob", True),
                             ("https://user:secret@pkg-containers.githubusercontent.com/blob", True),
                             ("https://pkg-containers.githubusercontent.com/blob", False)):
            with self.subTest(target=target), patch.object(v.urllib.request, "build_opener") as factory:
                factory.return_value.open.return_value = FakeHTTP(307, headers={"Location": target})
                with self.assertRaisesRegex(v.Denied, "redirect_denied"):
                    v.get("https://ghcr.io/token", {}, config_blob=blob)
                self.assertEqual(factory.return_value.open.call_count, 1)

    def test_oversized_body_and_timeout_are_sanitized_without_retry(self):
        with patch.object(v.urllib.request, "build_opener") as factory:
            factory.return_value.open.return_value = FakeHTTP(body=b"x" * (v.LIMIT + 1))
            with self.assertRaisesRegex(v.Denied, "response_too_large"):
                v.get("https://ghcr.io/token", {})
            self.assertEqual(factory.return_value.open.call_count, 1)
        with patch.object(v.urllib.request, "build_opener") as factory:
            factory.return_value.open.side_effect = TimeoutError("secret signed URL")
            with self.assertRaisesRegex(v.Denied, "^registry_transport_failed$"):
                v.get("https://ghcr.io/token", {})
            self.assertEqual(factory.return_value.open.call_count, 1)


class GateTest(unittest.TestCase):
    def setUp(self):
        self.value = v.proposal()
        self.env = {"GITHUB_SHA": "a" * 40, "APPROVED_SOURCE": "a" * 40,
                    "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1",
                    "GITHUB_REPOSITORY": "rk9595/emoji-studio"}

    def test_false_publication_gate_cannot_be_bypassed(self):
        self.assertIs(type(self.value["publication_authorized"]), bool)
        with self.assertRaisesRegex(v.Denied, "publication_not_authorized"):
            v.publication_tag({**self.value, "publication_authorized": False}, self.env)

    def test_explicit_matching_gate_has_unique_source_run_tag(self):
        value = {**self.value, "publication_authorized": True}
        tag = v.publication_tag(value, self.env, today=value["pricing_checked_on"])
        self.assertEqual(tag, "cpu-" + "a" * 40 + "-123")

    def test_rerun_wrong_source_repo_and_stale_price_check_fail(self):
        value = {**self.value, "publication_authorized": True}
        for change in ({"GITHUB_RUN_ATTEMPT": "2"}, {"APPROVED_SOURCE": "b" * 40},
                       {"GITHUB_REPOSITORY": "other/repo"}, {"GITHUB_RUN_ID": "../1"}):
            with self.subTest(change=change), self.assertRaises(v.Denied):
                v.publication_tag(value, {**self.env, **change}, today=value["pricing_checked_on"])
        with self.assertRaisesRegex(v.Denied, "pricing_recheck"):
            v.publication_tag(value, self.env, today="2000-01-01")

    def test_gated_cli_never_constructs_network_client(self):
        with patch.object(sys, "argv", ["verify", "preflight"]), \
                patch.object(v, "proposal", return_value={**self.value, "publication_authorized": False}), \
                patch.object(v, "Registry") as registry, patch("sys.stdout", new=io.StringIO()):
            with self.assertRaises(SystemExit):
                v.main()
            registry.assert_not_called()


if __name__ == "__main__":
    unittest.main()
