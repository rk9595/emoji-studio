import json
import time
import urllib.error
import urllib.request


class EmojiStudioError(RuntimeError):
    pass


class EmojiStudioClient:
    """Small dependency-free client for the Emoji Studio HTTP API."""

    def __init__(self, base_url, api_key, timeout=30):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout

    def _request(self, method, path, payload=None):
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            try:
                detail = json.load(error).get("detail", error.reason)
            except (ValueError, AttributeError):
                detail = error.reason
            raise EmojiStudioError(f"Emoji Studio returned HTTP {error.code}: {detail}") from error
        except urllib.error.URLError as error:
            raise EmojiStudioError(f"Could not reach Emoji Studio: {error.reason}") from error

    def generate(self, prompt, *, variations=1, seed=None):
        payload = {"prompt": prompt, "variations": variations}
        if seed is not None:
            payload["seed"] = seed
        return self._request("POST", "/v1/generations", payload)

    def generate_pack(self, prompts, *, seed=None):
        payload = {"prompts": list(prompts)}
        if seed is not None:
            payload["seed"] = seed
        return self._request("POST", "/v1/generations", payload)

    def get(self, job_id):
        return self._request("GET", f"/v1/generations/{job_id}")

    def wait(self, job_id, *, poll_seconds=1, timeout=900):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            job = self.get(job_id)
            if job["status"] == "succeeded":
                return job
            if job["status"] == "failed":
                raise EmojiStudioError(job.get("error", "Generation failed"))
            time.sleep(poll_seconds)
        raise TimeoutError(f"Generation {job_id} did not finish within {timeout} seconds")

    def download(self, artifact_url):
        request = urllib.request.Request(
            self.base_url + artifact_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.read()
        except urllib.error.URLError as error:
            raise EmojiStudioError(f"Could not download artifact: {error.reason}") from error
