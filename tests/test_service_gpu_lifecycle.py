import importlib.util
import json
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.common import write_json

PROJECT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = PROJECT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vast = load_script("vast_service_load_test.py")


class ServiceAuthorizationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.auth = {
            "authorization_id": "servicetest1",
            "authorized": True,
            "experiment": vast.EXPERIMENT,
            **vast.locked_hashes(),
            "max_total_dollars": 1.0,
            "max_hourly_dollars": 0.7,
            "max_elapsed_seconds": 2700,
            "expires_epoch": time.time() + 3600,
        }
        self.path = self.root / "authorization.json"
        write_json(self.path, self.auth)
        self.patch = patch.object(vast, "ARTIFACT_ROOT", self.root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def test_exact_single_use_authorization(self):
        self.assertEqual(vast.load_authorization(self.path), self.auth)
        write_json(self.root / "prior/allocation.json", {"authorization_id": "servicetest1"})
        with self.assertRaisesRegex(ValueError, "already used"):
            vast.load_authorization(self.path)

    def test_changed_lock_expiry_or_unsafe_cap_fails(self):
        for key, value in [
            ("service_sha256", "0" * 64),
            ("expires_epoch", time.time() - 1),
            ("max_total_dollars", 1.01),
            ("max_elapsed_seconds", 1799),
        ]:
            changed = dict(self.auth)
            changed[key] = value
            write_json(self.path, changed)
            with self.assertRaises(ValueError):
                vast.load_authorization(self.path)

    def test_offer_filter_accepts_a_reliable_40gb_single_gpu(self):
        offer = {
            "gpu_name": "A100 SXM4",
            "num_gpus": 1,
            "gpu_ram": 40960,
            "cpu_ram": 128000,
            "compute_cap": 800,
            "reliability": 0.999,
            "dph_total": 0.685,
            "inet_down_cost": 0.002,
            "inet_up_cost": 0.002,
        }
        self.assertTrue(vast.service_offer_allowed(offer, 0.7))
        offer["gpu_ram"] = 39999
        self.assertFalse(vast.service_offer_allowed(offer, 0.7))


class ServiceArchiveTest(unittest.TestCase):
    def test_final_archive_requires_successful_locked_report(self):
        report = {
            "status": "completed",
            "checks": {"auth": True, "load": True},
            "serving_config_sha256": vast.locked_hashes()["serving_config_sha256"],
            "adapter_sha256": vast.locked_hashes()["adapter_sha256"],
            "load_test": {
                "requests": 16,
                "concurrency": 4,
                "completed": 16,
                "failed": 0,
            },
        }
        files = {
            "runs/service-gpu-test/report.json": json.dumps(report).encode(),
            "runs/service-gpu-test/service.log": b"ok",
            "runs/service-gpu-test/metrics.prom": b"metrics",
            "runs/service-gpu-test/gpu-samples.json": b"[]",
            "runs/service-gpu-test/load-test.stdout": b"{}",
            "runs/service-gpu-test/smoke-1.png": b"png-one",
            "runs/service-gpu-test/smoke-1.webp": b"webp-one",
            "runs/service-gpu-test/smoke-2.png": b"png-two",
            "runs/service-gpu-test/smoke-2.webp": b"webp-two",
            "service-test.log": b"ok",
            "service-bootstrap.log": b"ok",
            "service.exit": b"0",
        }
        with tempfile.NamedTemporaryFile(suffix=".tar.gz") as target:
            with tarfile.open(target.name, "w:gz") as archive:
                for name, payload in files.items():
                    info = tarfile.TarInfo(name)
                    info.size = len(payload)
                    import io

                    archive.addfile(info, io.BytesIO(payload))
            self.assertEqual(vast.validate_final_archive(Path(target.name))["status"], "completed")


if __name__ == "__main__":
    unittest.main()
