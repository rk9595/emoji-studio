import socket
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from emoji_studio.smoke_http import LocalClient, SmokeFailure, local_path, run_smoke, server


class HttpSmokeTest(unittest.TestCase):
    def test_real_http_with_process_restarts(self):
        receipt = run_smoke()
        self.assertEqual(receipt["status"], "passed")
        self.assertEqual(receipt["gpu_allocations"], 0)
        self.assertEqual(receipt["images_admitted"], 2)
        self.assertEqual(receipt["process_starts"], 3)
        self.assertEqual(len(receipt["checks"]), 11)
        self.assertIn("completed_process_restart", receipt["checks"])
        self.assertIn("smoke_http.py", receipt["source_sha256"])

    def test_nonlocal_paths_rejected_before_request(self):
        for path in ("https://example.com/x", "//example.com/x", "x", "/x#f",
                     "/\\example.com", "/\nx", "/ x"):
            with self.subTest(path=path), self.assertRaises(SmokeFailure):
                local_path(path)
        self.assertEqual(local_path("/v1/generations?limit=2"), "/v1/generations?limit=2")

    def test_expired_deadline_never_opens_connection(self):
        client = LocalClient(1, {}, time.monotonic() - 1)
        with patch("http.client.HTTPConnection") as connection:
            with self.assertRaises(SmokeFailure):
                client.request("GET", "/healthz", user=None)
            connection.assert_not_called()

    def test_redirect_is_not_followed(self):
        client = LocalClient(1, {"alice": "temporary-test-token"}, time.monotonic() + 5)
        with patch("http.client.HTTPConnection") as connection:
            response = connection.return_value.getresponse.return_value
            response.status = 302
            response.read.return_value = b""
            with self.assertRaisesRegex(SmokeFailure, "HTTP status mismatch"):
                client.request("GET", "/v1/me")
            connection.return_value.request.assert_called_once()
            connection.return_value.close.assert_called_once()

    def test_failed_check_reaps_child_and_closes_listener(self):
        real_popen = subprocess.Popen
        children = []

        def capture(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            children.append(process)
            return process

        with tempfile.TemporaryDirectory() as temporary:
            with patch("emoji_studio.smoke_http.subprocess.Popen", side_effect=capture):
                with self.assertRaisesRegex(SmokeFailure, "injected check failure"):
                    with server(Path(temporary) / "jobs.sqlite3",
                                {"alice": "temporary-test-token"}, time.monotonic() + 15,
                                worker_enabled=False) as client:
                        port = client.port
                        raise SmokeFailure("injected check failure")
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll())
            with socket.socket() as connection:
                connection.settimeout(1)
                self.assertNotEqual(connection.connect_ex(("127.0.0.1", port)), 0)

    def test_startup_failure_reaps_child(self):
        real_popen = subprocess.Popen
        children = []

        def capture(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            children.append(process)
            return process

        with tempfile.TemporaryDirectory() as temporary:
            with patch("emoji_studio.smoke_http.subprocess.Popen", side_effect=capture):
                with patch.object(LocalClient, "request", side_effect=SmokeFailure("startup")):
                    with self.assertRaisesRegex(SmokeFailure, "startup"):
                        with server(Path(temporary) / "jobs.sqlite3", {"alice": "test-token"},
                                    time.monotonic() + 15, worker_enabled=False):
                            self.fail("Startup failure was ignored")
            self.assertEqual(len(children), 1)
            self.assertIsNotNone(children[0].poll())
