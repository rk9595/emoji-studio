import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

from emoji_studio.alpha import AccessPolicy
from emoji_studio.common import read_json, write_json

PROJECT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = PROJECT / "scripts" / name
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


creator = load_script("create_alpha_user.py")


class AlphaPolicyTest(unittest.TestCase):
    def policy_file(self, directory):
        path = Path(directory) / "users.json"
        write_json(
            path,
            {
                "schema_version": 1,
                "users": [
                    {
                        "id": "tester-one",
                        "token_sha256": hashlib.sha256(b"secret-one").hexdigest(),
                        "daily_image_quota": 3,
                        "requests_per_minute": 2,
                        "admin": False,
                    }
                ],
            },
        )
        return path

    def test_hashed_authentication_and_rate_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            policy = AccessPolicy.from_file(self.policy_file(directory))
            user = policy.authenticate("Bearer secret-one")
            self.assertEqual(user.id, "tester-one")
            self.assertIsNone(policy.authenticate("Bearer wrong"))
            self.assertEqual(policy.allow_request(user, clock=lambda: 100), (True, 0))
            self.assertEqual(policy.allow_request(user, clock=lambda: 101), (True, 0))
            allowed, retry = policy.allow_request(user, clock=lambda: 102)
            self.assertFalse(allowed)
            self.assertGreater(retry, 0)

    def test_invalid_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.policy_file(directory)
            data = read_json(path)
            data["users"][0]["daily_image_quota"] = 0
            write_json(path, data)
            with self.assertRaises(ValueError):
                AccessPolicy.from_file(path)

    def test_creator_stores_hash_not_token_and_rejects_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "users.json"
            result = creator.create_user(path, "tester-two", 20, 4)
            stored = read_json(path)
            self.assertNotIn(result["token"], path.read_text())
            self.assertEqual(
                stored["users"][0]["token_sha256"],
                hashlib.sha256(result["token"].encode()).hexdigest(),
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                creator.create_user(path, "tester-two", 20, 4)


if __name__ == "__main__":
    unittest.main()
