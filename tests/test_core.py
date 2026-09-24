import copy
import hashlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from emoji_studio.assets import git_blob_sha, inspect_png, inventory_tree, select_references
from emoji_studio.benchmark import create_plan, render_prompt, validate_benchmark
from emoji_studio.common import digest, read_json, write_json
from emoji_studio.report import build_report
from emoji_studio.runner import (
    completed_job,
    execute_jobs,
    generate,
    validate_plan,
    validate_token_lengths,
)

PROJECT = Path(__file__).resolve().parents[1]


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ["configs", "benchmarks"]:
            shutil.copytree(PROJECT / name, self.root / name)

    def plan(self, **kwargs):
        return create_plan(
            self.root, self.root / "runs/test/plan.json", "sdxl", ["brief"], [0], limit=2, **kwargs
        )

    def test_benchmark_has_40_unique_prompts_with_criteria(self):
        data = validate_benchmark(read_json(self.root / "benchmarks/development.json"))
        self.assertEqual(len(data["prompts"]), 40)
        self.assertEqual(len({p["category"] for p in data["prompts"]}), 4)
        data["prompts"].append(data["prompts"][0])
        with self.assertRaises(ValueError):
            validate_benchmark(data)

    def test_raw_and_brief_are_distinct(self):
        row = read_json(self.root / "benchmarks/development.json")["prompts"][0]
        self.assertEqual(render_prompt(row, "raw"), row["prompt"])
        self.assertTrue(render_prompt(row, "brief").startswith(row["prompt"]))
        self.assertNotEqual(render_prompt(row, "raw"), render_prompt(row, "brief"))

    def test_plan_is_stable_and_does_not_overwrite(self):
        plan = self.plan()
        self.assertEqual(validate_plan(plan), self.plan())
        with self.assertRaises(ValueError):
            self.plan(resolution=768)

    def test_plan_tampering_is_rejected(self):
        plan = copy.deepcopy(self.plan())
        plan["jobs"][0]["seed"] = 123
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_token_preflight_rejects_truncation(self):
        class Tokenizer:
            model_max_length = 77

            def __call__(self, prompt, truncation):
                self.assert_no_truncation = not truncation
                return {"input_ids": list(range(int(prompt)))}

        tokenizer = Tokenizer()
        plan = {"jobs": [{"id": "test", "prompt_id": "gesture", "prompt": "77"}]}
        self.assertEqual(validate_token_lengths(plan, [tokenizer, tokenizer]), {"test": [77, 77]})
        self.assertTrue(tokenizer.assert_no_truncation)
        plan["jobs"][0]["prompt"] = "78"
        with self.assertRaisesRegex(ValueError, "Refusing truncation"):
            validate_token_lengths(plan, [tokenizer])

    def test_full_comparison_count(self):
        plan = create_plan(
            self.root, self.root / "runs/full/plan.json", "klein", ["raw", "brief"], [0, 1, 2, 3]
        )
        self.assertEqual(plan["job_count"], 320)
        self.assertEqual(len({j["id"] for j in plan["jobs"]}), 320)

    def test_control_benchmark_is_separate_and_hashed(self):
        plan = create_plan(
            self.root,
            self.root / "runs/control/plan.json",
            "sdxl",
            ["raw", "brief"],
            [0],
            resolution=1024,
            benchmark_path=self.root / "benchmarks/sanity.json",
        )
        self.assertEqual(plan["job_count"], 8)
        self.assertEqual(plan["jobs"][0]["prompt_id"], "dev-control-01")
        self.assertTrue(all(j["resolution"] == 1024 for j in plan["jobs"]))
        self.assertNotEqual(plan["benchmark_hash"], self.plan()["benchmark_hash"])

    def test_invalid_parameters(self):
        for seeds, resolution in [([0, 0], 512), ([-1], 512), ([0], 513)]:
            with self.assertRaises(ValueError):
                create_plan(
                    self.root,
                    self.root / "bad.json",
                    "sdxl",
                    ["brief"],
                    seeds,
                    resolution=resolution,
                )

    def test_resume_verifies_receipts_and_corrupt_images(self):
        plan = self.plan()
        folder = self.root / "runs/test"
        calls = []

        def render(job, deadline):
            calls.append(job["id"])
            return Image.new("RGB", (8, 8), "white"), {"test_fixture": True}

        result = execute_jobs(plan, folder, render, deadline=100, clock=lambda: 0)
        self.assertEqual(result["remaining"], 0)
        result = execute_jobs(plan, folder, render, deadline=100, clock=lambda: 0)
        self.assertEqual(result["previously_completed"], 2)
        self.assertEqual(len(calls), 2)
        job = plan["jobs"][0]
        (folder / "images" / f"{job['id']}.png").write_bytes(b"corrupt")
        self.assertFalse(completed_job(folder, job))
        execute_jobs(plan, folder, render, deadline=100, clock=lambda: 0)
        self.assertEqual(len(calls), 3)
        self.assertTrue(completed_job(folder, job))
        self.assertFalse(generate(folder / "plan.json")["model_loaded"])

    def test_failure_stops_paid_loop(self):
        calls = []

        def fail(job, deadline):
            calls.append(job["id"])
            raise RuntimeError("simulated OOM")

        result = execute_jobs(self.plan(), self.root / "runs/test", fail, 100, clock=lambda: 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["remaining"], 2)
        self.assertEqual(result["failed_this_session"], 1)

    def test_deadline_stops_before_render(self):
        def fail_if_called(*args):
            self.fail("Rendering must not begin after deadline")

        result = execute_jobs(
            self.plan(), self.root / "runs/test", fail_if_called, 100, clock=lambda: 101
        )
        self.assertTrue(result["stopped_at_deadline"])
        self.assertEqual(result["remaining"], 2)

    def test_report_has_no_fake_generations_and_escapes_data(self):
        self.plan()
        write_json(
            self.root / "runs/test/review.json",
            {"valid_for_quality_comparison": False, "reason": "Diagnostic fixture"},
        )
        data = read_json(self.root / "benchmarks/development.json")
        data["prompts"][0]["prompt"] = "</script><script>alert('x')</script>"
        write_json(self.root / "benchmarks/development.json", data)
        result = build_report(self.root)
        self.assertEqual(result["completed_images"], 0)
        html = (self.root / "index.html").read_text()
        self.assertNotIn("</script><script>alert", html)
        payload = html.split('<script id="dataset" type="application/json">')[1].split("</script>")[
            0
        ]
        self.assertEqual(
            json.loads(payload)["benchmark"]["prompts"][0]["prompt"], data["prompts"][0]["prompt"]
        )
        self.assertFalse(json.loads(payload)["runs"][0]["review"]["valid_for_quality_comparison"])

    def test_report_ignores_stale_curation(self):
        write_json(
            self.root / "data/curation.json", {"reference_manifest_hash": digest([]), "rows": []}
        )
        build_report(self.root)
        html = (self.root / "index.html").read_text()
        self.assertIn('"curation": {', html)
        write_json(
            self.root / "data/curation.json", {"reference_manifest_hash": "stale", "rows": []}
        )
        build_report(self.root)
        self.assertIn('"curation": null', (self.root / "index.html").read_text())


class AssetTest(unittest.TestCase):
    def test_alpha_and_native_resolution_are_preserved(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (32, 32), (255, 255, 0, 0)).save(buffer, format="PNG")
        details = inspect_png(buffer.getvalue())
        self.assertTrue(details["has_transparency"])
        self.assertTrue(details["low_resolution_for_512_training"])
        self.assertEqual(details["width"], 32)

    def test_git_checksum(self):
        self.assertEqual(git_blob_sha(b"abc"), hashlib.sha1(b"blob 3\0abc").hexdigest())

    def test_concept_variants_remain_in_same_family(self):
        source = {"repository": "microsoft/fluentui-emoji", "revision": "a" * 40, "license": "MIT"}
        paths = [
            "assets/Clapping hands/Default/3D/a.png",
            "assets/Clapping hands/Dark/3D/b.png",
            "assets/Brain/3D/c.png",
            "assets/Brain/Color/c.svg",
        ]
        tree = {"tree": [{"type": "blob", "path": p, "sha": "x"} for p in paths]}
        rows = inventory_tree(tree, source)
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({r["concept_family"] for r in rows}), 2)
        selected = select_references(rows, ["Clapping hands", "Missing"], 4)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["tone"], "Default")
        self.assertIn("Clapping%20hands", selected[0]["source_url"])
        with self.assertRaises(ValueError):
            inventory_tree({"truncated": True}, source)


if __name__ == "__main__":
    unittest.main()
