import logging
import os
import time
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