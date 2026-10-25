import dataclasses
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, PngImagePlugin

from emoji_studio.durable_worker import render_pack
from emoji_studio.service import MockRenderer
from emoji_studio.smoke_cleanup import Binding, CleanupLedger, Lookup
from emoji_studio.smoke_export import (
    IMAGE_LIMIT,
    MANIFEST_LIMIT,
    REPOSITORY,
    TIMEOUT,
    Bundle,
    Destination,
    ExportBinding,
    ExportError,
    Ticket,
    canonical,
    digest,
    export_ticket,
    prepare_export,
    transfer_and_verify,
    upload_export,
    verify_export,
)

BINDING = ExportBinding("a" * 32, "b" * 64, "c" * 64)


class Storage:
    def __init__(self):
        self.objects = {}
        self.scope = Destination(REPOSITORY, BINDING.prefix, True)


class FakeWriter:
    def __init__(self, storage):
        self.storage = storage
        self.calls = []

    def destination(self, *, timeout_seconds):
        assert timeout_seconds == TIMEOUT
        return self.storage.scope

    def put_if_absent(self, name, content, *, sha256, timeout_seconds):
        assert timeout_seconds == TIMEOUT and digest(content) == sha256
        self.calls.append(name)
        if name in self.storage.objects and self.storage.objects[name] != content:
            raise RuntimeError("existing object differs")
        self.storage.objects[name] = content


class FakeReader:
    def __init__(self, storage):
        self.storage = storage
        self.calls = []

    def destination(self, *, timeout_seconds):
        assert timeout_seconds == TIMEOUT
        return self.storage.scope

    def read(self, name, *, max_bytes, timeout_seconds):
        assert timeout_seconds == TIMEOUT
        self.calls.append((name, max_bytes))
        return self.storage.objects[name]


class ExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        lease = SimpleNamespace(payload={"prompts": ["a cheerful red apple sticker"], "seeds": [7]},
                                job_id="mock-job")
        outputs, _ = render_pack(MockRenderer(), lease)
        cls.pair = {ext: outputs[f"00-7.{ext}"] for ext in ("png", "webp")}

    def setUp(self):
        self.storage = Storage()
        self.writer = FakeWriter(self.storage)
        self.reader = FakeReader(self.storage)
        self.bundle = prepare_export(BINDING, {1: self.pair}, renderer="MockRenderer")

    def test_mock_worker_exports_roundtrip_with_manifest_last_and_fresh_reads(self):
        result = transfer_and_verify(self.bundle, self.writer, self.reader)
        self.assertEqual(result["status"], "export_verified")
        self.assertEqual(result["artifact_count"], 2)
        self.assertEqual(result["renderer"], "MockRenderer")
        self.assertFalse(result["cleanup_verified"])
        self.assertFalse(result["smoke_accepted"])
        self.assertEqual(self.writer.calls, ["image-1.png", "image-1.webp", "manifest.json"])
        self.assertEqual(self.reader.calls[0], ("manifest.json", MANIFEST_LIMIT))
        self.assertEqual(len(self.reader.calls), 3)

    def test_two_image_pairs_are_supported_in_stable_order(self):
        bundle = prepare_export(BINDING, {1: self.pair, 0: self.pair}, renderer="MockRenderer")
        result = transfer_and_verify(bundle, self.writer, self.reader)
        self.assertEqual(result["artifact_count"], 4)
        self.assertEqual(self.writer.calls, ["image-0.png", "image-0.webp", "image-1.png",
                                             "image-1.webp", "manifest.json"])

    def test_fresh_verifier_only_needs_retained_ticket(self):
        ticket = upload_export(self.bundle, self.writer)
        self.assertEqual(self.reader.calls, [])
        serialized = json.loads(json.dumps(dataclasses.asdict(ticket)))
        restored = Ticket(ExportBinding(**serialized["binding"]), serialized["manifest_sha256"])
        self.bundle = None
        result = verify_export(restored, FakeReader(self.storage))
        self.assertEqual(result["status"], "export_verified")

    def test_upload_ack_does_not_prove_any_object_was_saved(self):
        class LyingWriter(FakeWriter):
            def put_if_absent(self, *args, **kwargs):
                pass

        ticket = upload_export(self.bundle, LyingWriter(self.storage))
        with self.assertRaisesRegex(ExportError, "storage_read_failed"):
            verify_export(ticket, self.reader)

    def test_lost_upload_ack_recovers_by_download_without_reupload(self):
        ticket = export_ticket(self.bundle)

        class LostAckWriter(FakeWriter):
            def put_if_absent(self, name, *args, **kwargs):
                super().put_if_absent(name, *args, **kwargs)
                if name == "manifest.json":
                    raise TimeoutError("secret-provider-detail")

        writer = LostAckWriter(self.storage)
        with self.assertRaisesRegex(ExportError, "^storage_write_failed$"):
            upload_export(self.bundle, writer)
        self.assertEqual(verify_export(ticket, self.reader)["status"], "export_verified")
        self.assertEqual(len(writer.calls), 3)

    def test_partial_upload_has_no_manifest_and_no_automatic_retry(self):
        ticket = export_ticket(self.bundle)

        class PartialWriter(FakeWriter):
            def put_if_absent(self, name, *args, **kwargs):
                super().put_if_absent(name, *args, **kwargs)
                raise TimeoutError("secret")

        writer = PartialWriter(self.storage)
        with self.assertRaisesRegex(ExportError, "^storage_write_failed$"):
            upload_export(self.bundle, writer)
        self.assertEqual(writer.calls, ["image-1.png"])
        self.assertNotIn("manifest.json", self.storage.objects)
        with self.assertRaises(ExportError):
            verify_export(ticket, self.reader)

    def test_existing_conflicting_bytes_are_not_overwritten(self):
        self.storage.objects["image-1.png"] = b"prior bytes"
        with self.assertRaises(ExportError):
            upload_export(self.bundle, self.writer)
        self.assertEqual(self.storage.objects["image-1.png"], b"prior bytes")
        self.assertNotIn("manifest.json", self.storage.objects)

    def test_identical_explicit_upload_is_safe_but_still_requires_verification(self):
        ticket = upload_export(self.bundle, self.writer)
        self.assertEqual(upload_export(self.bundle, self.writer), ticket)
        self.assertEqual(verify_export(ticket, self.reader)["status"], "export_verified")

    def test_public_wrong_repository_and_old_campaign_scopes_reject_before_upload(self):
        for scope in (Destination(REPOSITORY, BINDING.prefix, False),
                      Destination(REPOSITORY, BINDING.prefix, "true"),
                      Destination("rk9595/emoji-studio", BINDING.prefix, True),
                      Destination(REPOSITORY, "amd-comparison-v1", True),
                      Destination(REPOSITORY, "amd-api-smoke-v1/" + "d" * 32, True)):
            with self.subTest(scope=scope):
                self.storage.scope = scope
                with self.assertRaisesRegex(ExportError, "private_destination_mismatch"):
                    transfer_and_verify(self.bundle, self.writer, self.reader)
                self.assertEqual(self.writer.calls, [])

    def test_reader_must_be_distinct_and_private(self):
        with self.assertRaisesRegex(ExportError, "separate_download"):
            transfer_and_verify(self.bundle, self.writer, self.writer)
        unsafe = Storage()
        unsafe.scope = Destination(REPOSITORY, BINDING.prefix, False)
        with self.assertRaises(ExportError):
            transfer_and_verify(self.bundle, self.writer, FakeReader(unsafe))
        self.assertEqual(self.writer.calls, [])

    def test_privacy_change_mid_upload_stops_before_next_write(self):
        class ScopeChangingWriter(FakeWriter):
            def put_if_absent(self, *args, **kwargs):
                super().put_if_absent(*args, **kwargs)
                self.storage.scope = Destination(REPOSITORY, BINDING.prefix, False)

        writer = ScopeChangingWriter(self.storage)
        with self.assertRaises(ExportError):
            upload_export(self.bundle, writer)
        self.assertEqual(writer.calls, ["image-1.png"])
        self.assertNotIn("manifest.json", self.storage.objects)

    def test_privacy_change_during_download_prevents_verification(self):
        ticket = upload_export(self.bundle, self.writer)

        class ScopeChangingReader(FakeReader):
            def read(self, *args, **kwargs):
                content = super().read(*args, **kwargs)
                self.storage.scope = Destination(REPOSITORY, BINDING.prefix, False)
                return content

        with self.assertRaises(ExportError):
            verify_export(ticket, ScopeChangingReader(self.storage))

    def test_missing_corrupt_truncated_or_oversized_download_never_verifies(self):
        ticket = upload_export(self.bundle, self.writer)
        original = self.storage.objects.copy()
        for name in original:
            for content in (None, b"corrupt", original[name][:-1], original[name] + b"extra"):
                with self.subTest(name=name, content_length=None if content is None else len(content)):
                    self.storage.objects = original.copy()
                    if content is None:
                        del self.storage.objects[name]
                    else:
                        self.storage.objects[name] = content
                    with self.assertRaises(ExportError):
                        verify_export(ticket, FakeReader(self.storage))

    def test_ticket_binding_and_manifest_pin_cannot_be_substituted(self):
        ticket = upload_export(self.bundle, self.writer)
        with self.assertRaisesRegex(ExportError, "manifest_hash"):
            verify_export(Ticket(BINDING, "f" * 64), self.reader)
        changed = dataclasses.replace(BINDING, plan_sha256="d" * 64)
        with self.assertRaisesRegex(ExportError, "download_binding"):
            verify_export(Ticket(changed, ticket.manifest_sha256), self.reader)

    def test_secret_image_metadata_is_removed_and_source_hash_preserved(self):
        with Image.open(io.BytesIO(self.pair["png"])) as original:
            info = PngImagePlugin.PngInfo()
            info.add_text("Authorization", "secret-token")
            buffer = io.BytesIO()
            original.save(buffer, format="PNG", pnginfo=info)
        source = buffer.getvalue() + b"secret-trailing-data"
        bundle = prepare_export(BINDING, {0: {**self.pair, "png": source}}, renderer="MockRenderer")
        row = json.loads(bundle.manifest)["artifacts"][0]
        self.assertEqual(row["source_sha256"], digest(source))
        self.assertNotEqual(row["sha256"], row["source_sha256"])
        for _, content in bundle.artifacts:
            self.assertNotIn(b"secret", content)
        self.assertNotIn(b"Authorization", bundle.manifest)
        with Image.open(io.BytesIO(bundle.artifacts[0][1])) as clean:
            self.assertEqual(clean.info, {})
            self.assertEqual(clean.size, (512, 512))
        export_ticket(bundle)

    def test_arbitrary_metadata_paths_and_missing_pairs_are_rejected(self):
        for images in ({}, {2: self.pair}, {True: self.pair}, {"../token": self.pair},
                       {0: {"png": self.pair["png"]}}, {0: {**self.pair, "token": "secret"}}):
            with self.subTest(indices=list(images)), self.assertRaises(ExportError):
                prepare_export(BINDING, images, renderer="MockRenderer")
        with self.assertRaises(ExportError):
            prepare_export(BINDING, {0: self.pair}, renderer="secret-token")

    def test_bad_image_inputs_are_rejected_before_storage(self):
        for raw in (b"", b"not an image", b"x" * (IMAGE_LIMIT + 1), self.pair["webp"]):
            with self.subTest(size=len(raw)), self.assertRaises(ExportError):
                prepare_export(BINDING, {0: {**self.pair, "png": raw}}, renderer="MockRenderer")
        for size, mode in (((32, 32), "RGBA"), ((512, 512), "RGB"), ((512, 512), "RGBA")):
            buffer = io.BytesIO()
            Image.new(mode, size, "red").save(buffer, format="PNG")
            with self.subTest(size=size, mode=mode), self.assertRaises(ExportError):
                prepare_export(BINDING, {0: {**self.pair, "png": buffer.getvalue()}},
                               renderer="MockRenderer")
        self.assertEqual(self.writer.calls, [])

    def test_bundle_tampering_is_rejected_before_write(self):
        for bundle in (Bundle(self.bundle.manifest, ()),
                       Bundle(self.bundle.manifest, (("../token", b"bad"), *self.bundle.artifacts[1:])),
                       Bundle(self.bundle.manifest, (("image-1.png", b"bad"), *self.bundle.artifacts[1:]))):
            with self.subTest(bundle_count=len(bundle.artifacts)), self.assertRaises(ExportError):
                upload_export(bundle, self.writer)
        self.assertEqual(self.writer.calls, [])

    def test_strict_manifest_rejects_extra_fields_duplicates_and_path_traversal(self):
        original = json.loads(self.bundle.manifest)
        variants = [{**original, "Authorization": "secret"}, {**original, "version": True},
                    {**original, "campaign": "amd-comparison-v1"},
                    {**original, "artifacts": [{**original["artifacts"][0], "name": "../token"},
                                              original["artifacts"][1]]},
                    {**original, "artifacts": original["artifacts"] * 2}]
        raws = [canonical(value) for value in variants]
        raws.extend([self.bundle.manifest[:-1] + b',"seed":7}', b"x" * (MANIFEST_LIMIT + 1)])
        for raw in raws:
            with self.subTest(size=len(raw)), self.assertRaises(ExportError):
                upload_export(Bundle(raw, self.bundle.artifacts), self.writer)
        self.assertEqual(self.writer.calls, [])

    def test_errors_do_not_expose_provider_secrets(self):
        class FailingReader(FakeReader):
            def read(self, *args, **kwargs):
                raise RuntimeError("secret-token")

        ticket = upload_export(self.bundle, self.writer)
        with self.assertRaisesRegex(ExportError, "^storage_read_failed$"):
            verify_export(ticket, FailingReader(self.storage))

    def test_export_failure_does_not_prevent_independent_cleanup(self):
        class AbsentProvider:
            provider = "amd-devcloud"
            account_id = "mock-account"

            def lookup(self, resource_id):
                return Lookup(404)

        with tempfile.TemporaryDirectory() as temporary:
            binding = Binding("amd-devcloud", "mock-account", BINDING.allocation_id,
                              "12345", BINDING.plan_sha256, 1000)
            cleanup = CleanupLedger.create(Path(temporary).resolve() / "cleanup.sqlite", binding)
            ticket = export_ticket(self.bundle)
            with self.assertRaises(ExportError):
                verify_export(ticket, self.reader)
            result = cleanup.reconcile(AbsentProvider(), now=2500)
            self.assertEqual(result["status"], "complete")
            self.assertEqual(self.storage.objects, {})


if __name__ == "__main__":
    unittest.main()
