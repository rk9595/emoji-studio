import contextlib
import copy
import io
import json
import subprocess
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

golden = load_script("sample_golden_teacher")


class GoldenTeacherTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.output = self.root / golden.OUTPUT
        self.plan = golden.make_plan()
        write_json(self.output / "plan.json", self.plan)

    def report(self, count=8):
        (self.output / "images").mkdir(exist_ok=True)
        rows = []
        for i, job in enumerate(self.plan["jobs"][:count]):
            path = self.output / "images" / f"{job['id']}.png"
            Image.new("RGB", (1328, 1328), (i, 0, 0)).save(path)
            rows.append({"job": job, "image": f"images/{path.name}",
                         "image_sha256": golden.sha256(path), "curation_decision": "pending"})
        write_json(self.output / "report.json", {
            "plan_hash": self.plan["plan_hash"], "status": "completed", "images": rows,
        })

    def test_eight_jobs_four_pairs_and_original_trial_unchanged(self):
        jobs = self.plan["jobs"]
        self.assertEqual(len(jobs), 8)
        self.assertEqual([r["seed"] for r in jobs], [1101, 1102, 1201, 1202, 1301, 1302, 1401, 1402])
        self.assertEqual(len({r["pose_group"] for r in jobs}), 4)
        for i in range(0, 8, 2):
            self.assertEqual(jobs[i]["prompt"], jobs[i + 1]["prompt"])
        self.assertEqual(self.plan["config"]["reference"]["use"],
                         "visual_review_only_not_model_input")
        self.assertEqual(sampler.make_plan()["plan_hash"],
                         "b7b32a23c3fe42b0af036e6bc3616ec6eb69473ae9ad8cfcd73fb620bfb5728c")

    def test_sampler_runs_eight_text_only_jobs_and_records_each_environment(self):
        card = self.root / "README.md"
        card.write_text("test provenance fixture")
        self.plan["config"]["model_card_sha256"] = golden.sha256(card)
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
        pipe = Mock(return_value=SimpleNamespace(images=[Image.new("RGB", (1328, 1328))]))
        factory = Mock()
        factory.from_pretrained.return_value = pipe
        modules = {"torch": torch, "diffusers": SimpleNamespace(QwenImagePipeline=factory),
                   "huggingface_hub": SimpleNamespace(hf_hub_download=Mock(return_value=str(card)))}
        with patch.dict("sys.modules", modules), \
                patch.object(golden, "make_plan", return_value=self.plan):
            golden.sample(self.output, 2400)
        report = golden.validate_report(self.output, self.plan)
        self.assertEqual(len(report["images"]), 8)
        self.assertEqual(pipe.call_count, 8)
        self.assertEqual([c.kwargs["generator"] for c in pipe.call_args_list],
                         [r["seed"] for r in self.plan["jobs"]])
        self.assertTrue(all("image" not in c.kwargs for c in pipe.call_args_list))
        self.assertTrue(all(r["environment"]["gpu"] == "test GPU"
                            and r["curation_decision"] == "pending" for r in report["images"]))

    def test_plan_rejects_duplicate_seeds_reference_rebinding_and_eval_leakage(self):
        original = read_json(ROOT / golden.CONFIG)
        frozen = read_json(ROOT / "benchmarks/high-five-v1.json")["prompts"][0]["prompt"]
        for mutation in ("duplicate", "reference", "leakage"):
            config = copy.deepcopy(original)
            if mutation == "duplicate":
                config["compositions"][0]["seeds"] = [1101, 1101]
            elif mutation == "reference":
                config["reference"]["image_sha256"] = "changed"
            else:
                config["compositions"][0]["description"] = "Render this: " + frozen
            def read(path):
                return config if str(path).endswith(golden.CONFIG) else read_json(path)
            with patch.object(golden, "read_json", side_effect=read):
                with self.assertRaises(ValueError, msg=mutation):
                    golden.make_plan()

    def test_verification_requires_eight_not_four_and_gallery_inherits_no_approvals(self):
        self.report(4)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            golden.validate_report(self.output, self.plan)
        self.report()
        golden.validate_report(self.output, self.plan)
        gallery.build(self.output, self.plan)
        self.assertIn("8/8 verified images", (self.output / "review.html").read_text())
        review = read_json(self.output / "human-review-template.json")
        self.assertEqual(len(review["images"]), 8)
        self.assertTrue(all(r["gesture_correct"] is None and r["style_correct"] is None
                            for r in review["images"]))

    def test_cloud_archive_roundtrip_keeps_trials_isolated(self):
        archive_path = self.root / "upload.tar.gz"
        # Use real sources to prove the uploaded plan can be recomputed on the target.
        with patch.object(cloud, "trial_plan", return_value=self.plan):
            # Only the new local plan is needed; no original images or review answers.
            source_root = self.root / "source"
            names = [n for n in cloud.FILES if n not in (
                remote.TRIALS["pilot"]["config"], f"{sampler.OUTPUT}/plan.json")]
            names += [golden.CONFIG, "scripts/sample_golden_teacher.py"]
            for name in names:
                source = ROOT / name
                if source.is_dir():
                    (source_root / name).mkdir(parents=True)
                    (source_root / name / "fixture.py").write_text("pass")
                else:
                    target = source_root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(source.read_bytes())
            write_json(source_root / golden.OUTPUT / "plan.json", self.plan)
            write_json(source_root / "configs/alpha-users.json", {"private": True})
            with patch.object(cloud, "ROOT", source_root):
                cloud.build_archive(archive_path, "golden")
        extracted = self.root / "extracted"
        with tarfile.open(archive_path) as archive:
            names = archive.getnames()
            self.assertNotIn(remote.TRIALS["pilot"]["config"], names)
            self.assertFalse(any(n.startswith(sampler.OUTPUT) for n in names))
            self.assertNotIn("configs/alpha-users.json", names)
            archive.extractall(extracted, filter="data")
        self.assertEqual(golden.make_plan(extracted), self.plan)

    def test_remote_snapshot_selects_golden_and_never_includes_reference_trial(self):
        self.report(1)
        write_json(self.root / sampler.OUTPUT / "plan.json", {"private": "old trial"})
        stream = io.BytesIO()
        remote.snapshot(stream, self.root, "golden")
        stream.seek(0)
        with tarfile.open(fileobj=stream, mode="r:gz") as archive:
            self.assertTrue(all(n.startswith(golden.OUTPUT) for n in archive.getnames()))

    def test_golden_worker_uses_golden_sampler(self):
        with patch.object(remote, "ROOT", self.root), patch.dict(remote.os.environ), \
                patch.object(remote.subprocess, "run", return_value=Mock(returncode=0)) as run:
            remote.worker(2400, "golden")
        command = run.call_args_list[-1].args[0]
        self.assertEqual(command[1], "scripts/sample_golden_teacher.py")

    def test_authorization_is_trial_bound_and_enforces_new_caps(self):
        auth = {"authorized": True, "experiment": remote.TRIALS["golden"]["experiment"],
                **cloud.locked_inputs("golden"), "authorization_id": "goldentest1",
                "max_total_dollars": 1.25, "max_hourly_dollars": .80,
                "max_elapsed_seconds": 2700, "expires_epoch": time.time() + 600}
        path = self.root / "authorization.json"
        with patch.object(cloud, "artifact_root", return_value=self.root):
            write_json(path, auth)
            self.assertEqual(cloud.load_authorization(path, "golden"), auth)
            for key, value in [("max_total_dollars", 1.26), ("max_elapsed_seconds", 2701),
                               ("experiment", remote.TRIALS["pilot"]["experiment"])]:
                write_json(path, {**auth, key: value})
                with self.assertRaises(ValueError):
                    cloud.load_authorization(path, "golden")
            write_json(path, auth)
            write_json(self.root / "prior/attempt.json", {"authorization_id": "goldentest1"})
            with self.assertRaisesRegex(ValueError, "consumed"):
                cloud.load_authorization(path, "golden")

    def test_wrong_trial_snapshot_rejected_without_overwriting_local_output(self):
        # The local importer must reject a pilot path even if SSH returned success.
        archive_bytes = io.BytesIO()
        with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
            data = json.dumps({"wrong": "trial"}).encode()
            member = tarfile.TarInfo(f"{sampler.OUTPUT}/plan.json")
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
        def download(command, **kwargs):
            kwargs["stdout"].write(archive_bytes.getvalue())
            return subprocess.CompletedProcess(command, 0)
        with patch.object(cloud.subprocess, "run", side_effect=download), \
                patch.object(cloud, "ROOT", self.root):
            with self.assertRaisesRegex(ValueError, "Unexpected result archive"):
                cloud.snapshot(["ssh"], self.root, trial="golden")
        self.assertEqual(read_json(self.output / "plan.json"), self.plan)

    def test_complete_trial_never_makes_another_provider_request(self):
        self.report()
        with patch.object(cloud, "ROOT", self.root), \
                patch.object(cloud, "load_authorization", return_value={}), \
                patch.object(cloud, "trial_plan", return_value=self.plan), \
                patch.object(cloud, "request") as request:
            with self.assertRaisesRegex(ValueError, "unnecessary rental"):
                cloud.run(self.root / "authorization.json", "golden")
        request.assert_not_called()
