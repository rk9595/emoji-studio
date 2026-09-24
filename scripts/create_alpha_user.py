"""Create an alpha access token and store only its SHA-256 digest."""

import argparse
import hashlib
import json
import os
import re
import secrets
from pathlib import Path

from emoji_studio.alpha import AccessPolicy
from emoji_studio.common import read_json, write_json

PROJECT = Path(__file__).resolve().parents[1]


def create_user(path, user_id, daily_quota, requests_per_minute, admin=False):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,47}", user_id):
        raise ValueError(
            "User ID must use 2-48 lowercase letters, numbers, underscores, or hyphens"
        )
    if path.exists():
        data = read_json(path)
        AccessPolicy.from_file(path)
    else:
        data = {"schema_version": 1, "users": []}
    if any(row["id"] == user_id for row in data["users"]):
        raise ValueError("User ID already exists")
    token = secrets.token_urlsafe(32)
    data["users"].append(
        {
            "id": user_id,
            "token_sha256": hashlib.sha256(token.encode()).hexdigest(),
            "daily_image_quota": daily_quota,
            "requests_per_minute": requests_per_minute,
            "admin": admin,
        }
    )
    write_json(path, data)
    os.chmod(path, 0o600)
    AccessPolicy.from_file(path)
    return {"id": user_id, "token": token, "users_file": str(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("user_id")
    parser.add_argument("--output", type=Path, default=PROJECT / "configs/alpha-users.json")
    parser.add_argument("--daily-quota", type=int, default=20)
    parser.add_argument("--requests-per-minute", type=int, default=4)
    parser.add_argument("--admin", action="store_true")
    args = parser.parse_args()
    try:
        result = create_user(
            args.output.resolve(),
            args.user_id,
            args.daily_quota,
            args.requests_per_minute,
            args.admin,
        )
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Error: {error}\n")
    print(json.dumps(result, indent=2))
    print("Save the token now; only its SHA-256 digest is stored.")


if __name__ == "__main__":
    main()
