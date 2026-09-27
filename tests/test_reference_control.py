import contextlib
import copy
import io
import shutil
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PIL import Image
from test_teacher_pilot import ROOT, cloud, gallery, load_script, remote, sampler

from emoji_studio.common import read_json, write_json

reference = load_script("sample_reference_control")


class ReferenceControlTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / reference.OUTPUT
        self.plan = reference.make_plan()
        write_json(self.output / "plan.json", self.plan)

    def test_four_matched_pairs_and_historical_plans_unchanged(self):
        jobs = self.plan["jobs"]
        self.assertEqual(len(jobs), 8)
        for left, right in zip(jobs[::2], jobs[1::2], strict=True):
            for key in ("prompt", "seed", "pair_id", "lineage", "task", "reference_id"):
                self.assertEqual(left[key], right[key])
            self.assertEqual((left["condition"], right["condition"]), ("text", "image"))
            self.assertIsNone(left["reference_sha256"])
            self.assertEqual(right["reference_sha256"],
                             reference.REFERENCES[right["reference_id"]][1])
        self.assertEqual(sampler.make_plan()["plan_hash"],
                         "b7b32a23c3fe42b0af036e6bc3616ec6eb69473ae9ad8cfcd73fb620bfb5728c")
        self.assertEqual(load_script("sample_golden_teacher").make_plan()["plan_hash"],
                         "6820fb673cc9a80a91b1d1883d932923bdc3dbec5a9bfbe68c8beeb3740958fa")

    def test_rejects_reference_rebinding_tampering_and_frozen_prompt_leak(self):
        original = read_json(ROOT / reference.CONFIG)
        for mutation in ("path", "image_sha256", "lineage", "leak", "seed", "adapter"):
            config = copy.deepcopy(original)
            if mutation in ("path", "image_sha256", "lineage"):
                config["references"][0][mutation] = "changed"
            elif mutation == "leak":
                config["style"] = read_json(ROOT / "benchmarks/high-five-v1.json")["prompts"][0]["prompt"]
            elif mutation == "seed":
                config["tasks"][1]["seed_offset"] = 0
            else:
                config["adapter"] = "unreviewed"
            def read(path):
                return config if str(path).endswith(reference.CONFIG) else read_json(path)
            with patch.object(reference, "read_json", side_effect=read):
                with self.assertRaises(ValueError, msg=mutation):
                    reference.make_plan()
        with patch.object(reference, "sha256", return_value="corrupted"):
            with self.assertRaisesRegex(ValueError, "checksum"):
                reference.make_plan()

    def fake_modules(self):
        card = self.root / "README.md"
        card.write_text("fixture provenance")
        self.plan["config"]["model_card_sha256"] = reference.sha256(card)
        write_json(self.output / "plan.json", self.plan)
        generator = Mock()
        generator.manual_seed.side_effect = lambda seed: seed
        cuda = Mock()
        cuda.device_count.return_value = 1
        cuda.get_device_properties.return_value = SimpleNamespace(total_memory=48 * 1024**3)
        cuda.get_device_name.return_value = "test GPU"
        cuda.max_memory_allocated.return_value = 123
        torch = SimpleNamespace(cuda=cuda, bfloat16="bf16", __version__="test",
                                no_grad=contextlib.nullcontext,
                                Generator=Mock(return_value=generator))
        pipe = Mock(return_value=SimpleNamespace(images=[Image.new("RGB", (1024, 1024))]))
        factory = Mock()
        factory.from_pretrained.return_value = pipe
        modules = {"torch": torch, "diffusers": SimpleNamespace(Flux2KleinPipeline=factory),
                   "huggingface_hub": SimpleNamespace(hf_hub_download=Mock(return_value=str(card)))}
        return modules, pipe, factory

    def test_real_image_argument_only_in_conditioned_pairs_and_no_inherited_approval(self):
        modules, pipe, factory = self.fake_modules()
        with patch.dict("sys.modules", modules), \
                patch.object(reference, "make_plan", return_value=self.plan):
            reference.sample(self.output, 2400)
            # Completed work must not load weights or produce new images on resume.
            reference.sample(self.output, 2400)
        self.assertEqual(pipe.call_count, 8)
        factory.from_pretrained.assert_called_once_with(
            self.plan["config"]["model_id"], revision=self.plan["config"]["model_revision"],
            torch_dtype="bf16", use_safetensors=True)
        pipe.load_lora_weights.assert_not_called()
        for call, job in zip(pipe.call_args_list, self.plan["jobs"], strict=True):
            self.assertEqual(call.kwargs["generator"], job["seed"])
            if job["condition"] == "text":
                self.assertNotIn("image", call.kwargs)
            else:
                actual = call.kwargs["image"]
                self.assertEqual(actual.size, (1024, 1024))
                with Image.open(ROOT / reference.REFERENCES[job["reference_id"]][0]) as source:
                    expected = source.convert("RGB").resize((1024, 1024), Image.Resampling.LANCZOS)
                self.assertEqual(actual.tobytes(), expected.tobytes())
        report = reference.validate_report(self.output, self.plan)
        self.assertTrue(all(r["curation_decision"] == "pending" for r in report["images"]))
        gallery.build(self.output, self.plan)
        page = (self.output / "review.html").read_text()
        self.assertEqual(page.count('<div class="pair">'), 4)
        self.assertIn('Original 004', page)
        self.assertIn('Original 1401', page)
        review = read_json(self.output / "human-review-template.json")
        self.assertTrue(all(r["gesture_correct"] is None for r in review["images"]))

    def test_partial_failure_resumes_only_missing_jobs(self):
        modules, pipe, _ = self.fake_modules()
        result = SimpleNamespace(images=[Image.new("RGB", (1024, 1024))])
        pipe.side_effect = [result, RuntimeError("test interruption")]
        with patch.dict("sys.modules", modules), \
                patch.object(reference, "make_plan", return_value=self.plan):
            with self.assertRaises(RuntimeError):
                reference.sample(self.output, 2400)
            partial = reference.validate_report(self.output, self.plan, require_complete=False)
            self.assertEqual(len(partial["images"]), 1)
            self.assertEqual(partial["status"], "failed")
            pipe.reset_mock(side_effect=True)
            pipe.return_value = result
            reference.sample(self.output, 2400)
        self.assertEqual(pipe.call_count, 7)
        reference.validate_report(self.output, self.plan)

    def test_actual_archive_recomputes_plan_and_only_includes_two_references(self):
        source = self.root / "source"
        names = [n for n in cloud.FILES if n not in (
            remote.TRIALS["pilot"]["config"], f"{sampler.OUTPUT}/plan.json")]
        names += [reference.CONFIG, "scripts/sample_reference_control.py"]
        names += [r["path"] for r in self.plan["config"]["references"]]
        for name in names:
            target = source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            if (ROOT / name).is_dir():
                shutil.copytree(ROOT / name, target, ignore=shutil.ignore_patterns("__pycache__"))
            else:
                shutil.copyfile(ROOT / name, target)
        write_json(source / reference.OUTPUT / "plan.json", self.plan)
        write_json(source / "configs/alpha-users.json", {"secret": "not uploaded"})
        archive_path = self.root / "upload.tar.gz"
        with patch.object(cloud, "ROOT", source):
            cloud.build_archive(archive_path, "reference")
        extracted = self.root / "extracted"
        with tarfile.open(archive_path) as archive:
            archived = archive.getnames()
            self.assertEqual(sorted(n for n in archived if n.endswith(".png")),
                             sorted(r["path"] for r in self.plan["config"]["references"]))
            self.assertNotIn("configs/alpha-users.json", archived)
            self.assertNotIn(remote.TRIALS["golden"]["config"], archived)
            archive.extractall(extracted, filter="data")
        self.assertEqual(reference.make_plan(extracted), self.plan)
        stream = io.BytesIO()
        remote.snapshot(stream, source, "reference")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:gz") as archive:
            self.assertEqual(archive.getnames(), [f"{reference.OUTPUT}/plan.json"])

    def test_trial_budget_and_worker_are_isolated(self):
        auth = {"authorized": True, "experiment": remote.TRIALS["reference"]["experiment"],
                **cloud.locked_inputs("reference"), "authorization_id": "referencetest1",
                "max_total_dollars": 1.25, "max_hourly_dollars": .80,
                "max_elapsed_seconds": 2700, "expires_epoch": time.time() + 600}
        path = self.root / "authorization.json"
        with patch.object(cloud, "artifact_root", return_value=self.root):
            write_json(path, auth)
            self.assertEqual(cloud.load_authorization(path, "reference"), auth)
            for key, value in [("max_total_dollars", 1.26), ("max_hourly_dollars", .81),
                               ("max_elapsed_seconds", 2701),
                               ("experiment", remote.TRIALS["golden"]["experiment"])]:
                write_json(path, {**auth, key: value})
                with self.assertRaises(ValueError):
                    cloud.load_authorization(path, "reference")
        with patch.object(remote, "ROOT", self.root), patch.dict(remote.os.environ), \
                patch.object(remote.subprocess, "run", return_value=Mock(returncode=0)) as run:
            remote.worker(2400, "reference")
        self.assertEqual(run.call_args_list[-1].args[0][1], "scripts/sample_reference_control.py")
