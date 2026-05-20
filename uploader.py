import logging
import os
import time
from datetime import datetime
import requests


class DriveUploader:
    def __init__(self, script_url: str):
        self.script_url = script_url
        self._log = logging.getLogger("wildlife_cam")

    def upload(self, file_path: str) -> bool:
        if not self.script_url:
            self._log.error("script_url is empty - cannot upload")
            return False

        max_attempts = 3
        retry_interval = 30

        for attempt in range(1, max_attempts + 1):
            try:
                with open(file_path, "rb") as f:
                    resp = requests.post(
                        self.script_url,
                        files={"file": (os.path.basename(file_path), f, "video/mp4")},
                        timeout=60,
                    )
                if resp.status_code == 200:
                    body = resp.json()
                    if body.get("status") == "ok":
                        self._log.info(
                            "Upload succeeded: %s (fileId=%s)",
                            file_path,
                            body.get("fileId"),
                        )
                        return True
                    else:
                        self._log.warning(
                            "Upload attempt %d/%d -- unexpected response: %s",
                            attempt,
                            max_attempts,
                            body,
                        )
                else:
                    self._log.warning(
                        "Upload attempt %d/%d -- HTTP %d",
                        attempt,
                        max_attempts,
                        resp.status_code,
                    )
            except Exception as exc:
                self._log.warning(
                    "Upload attempt %d/%d -- exception: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

            if attempt < max_attempts:
                self._log.info("Retrying in %ds...", retry_interval)
                time.sleep(retry_interval)

        self._log.error(
            "Upload failed after %d attempts: %s", max_attempts, file_path
        )
        return False


class WorkerUploader:
    def __init__(self, api_url: str, device_token: str, trap_id: str):
        self.api_url = api_url.rstrip("/")
        self.device_token = device_token
        self.trap_id = trap_id
        self._log = logging.getLogger("wildlife_cam")
        self._cached_arm_state = True
        self._cached_arm_state_at = 0.0

    def is_armed(self, cache_ttl_seconds: float = 10.0) -> bool:
        now = time.time()
        if now - self._cached_arm_state_at < cache_ttl_seconds:
            return self._cached_arm_state

        headers = {"x-device-token": self.device_token}
        response = requests.get(
            f"{self.api_url}/traps/{self.trap_id}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        self._cached_arm_state = bool(body.get("is_armed", True))
        self._cached_arm_state_at = now
        return self._cached_arm_state

    def upload(self, file_path: str) -> bool:
        if not self.api_url or not self.device_token or not self.trap_id:
            self._log.error("WILDLIFE_API_URL, WILDLIFE_DEVICE_TOKEN, and TRAP_ID are required")
            return False

        max_attempts = 3
        retry_interval = 30

        for attempt in range(1, max_attempts + 1):
            try:
                self._upload_once(file_path)
                self._log.info("Upload succeeded: %s", file_path)
                return True
            except Exception as exc:
                self._log.warning(
                    "Upload attempt %d/%d -- exception: %s",
                    attempt,
                    max_attempts,
                    exc,
                )

            if attempt < max_attempts:
                self._log.info("Retrying in %ds...", retry_interval)
                time.sleep(retry_interval)

        self._log.error("Upload failed after %d attempts: %s", max_attempts, file_path)
        return False

    def _upload_once(self, file_path: str) -> None:
        captured_at = datetime.fromtimestamp(os.path.getmtime(file_path)).astimezone().isoformat()
        headers = {"x-device-token": self.device_token}

        upload_url_resp = requests.post(
            f"{self.api_url}/upload-url",
            headers=headers,
            json={
                "trap_id": self.trap_id,
                "captured_at": captured_at,
                "filename": os.path.basename(file_path),
            },
            timeout=30,
        )
        upload_url_resp.raise_for_status()
        upload_info = upload_url_resp.json()

        with open(file_path, "rb") as video:
            put_resp = requests.put(
                upload_info["upload_url"],
                data=video,
                headers={"content-type": "video/mp4"},
                timeout=300,
            )
        put_resp.raise_for_status()

        metadata_resp = requests.post(
            f"{self.api_url}/videos",
            headers=headers,
            json={
                "trap_id": self.trap_id,
                "captured_at": captured_at,
                "r2_key": upload_info["r2_key"],
            },
            timeout=30,
        )
        metadata_resp.raise_for_status()
