import hashlib
import hmac
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from .common import read_json

USER_ID = re.compile(r"[a-z0-9][a-z0-9_-]{1,47}")
SHA256 = re.compile(r"[0-9a-f]{64}")


@dataclass(frozen=True)
class AlphaUser:
    id: str
    token_sha256: str
    daily_image_quota: int
    requests_per_minute: int
    admin: bool = False


class AccessPolicy:
    def __init__(self, users):
        self.users = tuple(users)
        if not self.users:
            raise ValueError("At least one alpha user is required")
        self._requests = defaultdict(deque)
        self._lock = threading.Lock()

    @classmethod
    def from_file(cls, path):
        data = read_json(Path(path))
        if set(data) != {"schema_version", "users"} or data["schema_version"] != 1:
            raise ValueError("Alpha users file has an unsupported schema")
        users = []
        seen = set()
        for row in data["users"]:
            required = {
                "id",
                "token_sha256",
                "daily_image_quota",
                "requests_per_minute",
                "admin",
            }
            if set(row) != required:
                raise ValueError("Alpha user has unexpected or missing fields")
            if not isinstance(row["id"], str) or not USER_ID.fullmatch(row["id"]):
                raise ValueError("Alpha user ID is invalid")
            if row["id"] in seen:
                raise ValueError("Alpha user IDs must be unique")
            if not isinstance(row["token_sha256"], str) or not SHA256.fullmatch(
                row["token_sha256"]
            ):
                raise ValueError("Alpha user token hash is invalid")
            if (
                type(row["daily_image_quota"]) is not int
                or not 1 <= row["daily_image_quota"] <= 1000
            ):
                raise ValueError("Daily image quota must be between 1 and 1000")
            if (
                type(row["requests_per_minute"]) is not int
                or not 1 <= row["requests_per_minute"] <= 120
            ):
                raise ValueError("Requests per minute must be between 1 and 120")
            if type(row["admin"]) is not bool:
                raise ValueError("Alpha user admin flag must be boolean")
            users.append(AlphaUser(**row))
            seen.add(row["id"])
        return cls(users)

    @classmethod
    def single_key(cls, token, *, daily_image_quota=1000, requests_per_minute=120):
        if not token:
            raise ValueError("A non-empty API key is required")
        return cls(
            [
                AlphaUser(
                    id="default-admin",
                    token_sha256=hashlib.sha256(token.encode()).hexdigest(),
                    daily_image_quota=daily_image_quota,
                    requests_per_minute=requests_per_minute,
                    admin=True,
                )
            ]
        )

    def authenticate(self, authorization):
        if not authorization or not authorization.startswith("Bearer "):
            return None
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        for user in self.users:
            if hmac.compare_digest(digest, user.token_sha256):
                return user
        return None

    def allow_request(self, user, clock=time.monotonic):
        current = clock()
        with self._lock:
            requests = self._requests[user.id]
            while requests and requests[0] <= current - 60:
                requests.popleft()
            if len(requests) >= user.requests_per_minute:
                retry_after = max(1, round(60 - (current - requests[0])))
                return False, retry_after
            requests.append(current)
        return True, 0
