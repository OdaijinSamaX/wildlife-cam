import logging
import os
import time
from datetime import datetime
import requests


class DriveUploader:
    def __init__(self, script_url: str):
        self.script_url = script_url
        self._log = logging.getLogger("wildlife_cam")

    def upload(
        self,
        file_path: str,
        *,
        trap_id: str | None = None,
        captured_at: str | None = None,
        source_filename: str | None = None,
    ) -> bool:
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
        self.trap_id = trap_id.strip()
        self._log = logging.getLogger("wildlife_cam")
        self._cached_arm_states: dict[str, tuple[bool, float]] = {}

    def is_armed(self, trap_id: str | None = None, cache_ttl_seconds: float = 10.0) -> bool:
        resolved_trap_id = (trap_id or self.trap_id).strip()
        if not resolved_trap_id:
            raise RuntimeError("TRAP_ID is required to fetch arm state")

        now = time.time()
        cached = self._cached_arm_states.get(resolved_trap_id)
        if cached and now - cached[1] < cache_ttl_seconds:
            return cached[0]

        headers = {"x-device-token": self.device_token}
        response = requests.get(
            f"{self.api_url}/traps/{resolved_trap_id}",
            headers=headers,
            timeout=15,
        )
        response.raise_for_status()
        body = response.json()
        is_armed = bool(body.get("is_armed", True))
        self._cached_arm_states[resolved_trap_id] = (is_armed, now)
        return is_armed

    def upload(
        self,
        file_path: str,
        *,
        trap_id: str | None = None,
        captured_at: str | None = None,
        source_filename: str | None = None,
    ) -> bool:
        if not self.api_url or not self.device_token:
            self._log.error("WILDLIFE_API_URL and WILDLIFE_DEVICE_TOKEN are required")
            return False

        max_attempts = 3
        retry_interval = 30

        for attempt in range(1, max_attempts + 1):
            try:
                self._upload_once(
                    file_path,
                    trap_id=trap_id,
                    captured_at=captured_at,
                    source_filename=source_filename,
                )
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

    def _upload_once(
        self,
        file_path: str,
        *,
        trap_id: str | None = None,
        captured_at: str | None = None,
        source_filename: str | None = None,
    ) -> None:
        captured_at = (
            captured_at
            or datetime.fromtimestamp(os.path.getmtime(file_path)).astimezone().isoformat()
        )
        resolved_trap_id = (trap_id or self.trap_id).strip()
        if not resolved_trap_id:
            raise RuntimeError("TRAP_ID is required to upload a video")
        resolved_filename = source_filename or os.path.basename(file_path)
        headers = {"x-device-token": self.device_token}

        upload_url_resp = requests.post(
            f"{self.api_url}/upload-url",
            headers=headers,
            json={
                "trap_id": resolved_trap_id,
                "captured_at": captured_at,
                "filename": resolved_filename,
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
                "trap_id": resolved_trap_id,
                "captured_at": captured_at,
                "r2_key": upload_info["r2_key"],
            },
            timeout=30,
        )
        metadata_resp.raise_for_status()
