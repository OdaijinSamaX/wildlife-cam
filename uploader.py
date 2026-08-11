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
        # 直近の /traps/:id 応答から得た録画設定 (record_seconds / cooldown_seconds)。
        # arm ポーリング (ArmStateMonitor 経由) のついでに更新され、検知ループが
        # trap_config() で参照する。dict の差し替えは GIL 下で原子的。
        self._last_trap_config: dict = {}
        # LTE では毎回の TCP/TLS ハンドシェイクが高くつくので接続を使い回す。
        self._session = requests.Session()
        # arm 確認の timeout は (connect, read) タプルで短く固定する。
        # v6 ブラックホール時に既定の 15s 単一値では 1 本あたり最長 15s ブロックし、
        # AAAA 2 件で 30s に達していた (2026-08-08 障害)。connect を 3s に絞り、
        # gai.conf の v4 優先と併せて素早く v4 へ倒す。
        self._arm_timeout: tuple[float, float] = (3.0, 10.0)

    def is_armed(self, trap_id: str | None = None, cache_ttl_seconds: float = 10.0) -> bool:
        resolved_trap_id = (trap_id or self.trap_id).strip()
        if not resolved_trap_id:
            raise RuntimeError("TRAP_ID is required to fetch arm state")

        # キャッシュの新鮮さは経過時間の比較なので time.monotonic() を使う。
        # RTC 無し端末で NTP 同期時に time.time() が飛ぶと、time.time() 基準では
        # キャッシュが一気に失効/永続化しうる。
        now = time.monotonic()
        cached = self._cached_arm_states.get(resolved_trap_id)
        if cached and now - cached[1] < cache_ttl_seconds:
            return cached[0]

        headers = {"x-device-token": self.device_token}
        response = self._session.get(
            f"{self.api_url}/traps/{resolved_trap_id}",
            headers=headers,
            timeout=self._arm_timeout,
        )
        response.raise_for_status()
        body = response.json()
        is_armed = bool(body.get("is_armed", True))
        # 録画設定は arm ポーリングに同乗して届く。応答に無いキーは None (未設定) 扱い。
        self._last_trap_config = {
            "record_seconds": body.get("record_seconds"),
            "cooldown_seconds": body.get("cooldown_seconds"),
        }
        # 格納時刻はレスポンス受領後に取り直す。リクエスト開始前の時刻を使うと、
        # 呼び出しが TTL を超えた瞬間に保存したキャッシュが失効済みになり、
        # キャッシュが永久に効かなくなる (2026-08-08 障害の一因)。
        self._cached_arm_states[resolved_trap_id] = (is_armed, time.monotonic())
        return is_armed

    def trap_config(self) -> dict:
        """直近の /traps/:id 応答から得た録画設定。未取得なら空 dict を返す。"""
        return dict(self._last_trap_config)

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

        upload_url_resp = self._session.post(
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
            put_resp = self._session.put(
                upload_info["upload_url"],
                data=video,
                headers={"content-type": "video/mp4"},
                timeout=300,
            )
        put_resp.raise_for_status()

        metadata_resp = self._session.post(
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
