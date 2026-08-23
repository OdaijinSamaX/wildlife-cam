"""SD 容量の監視・回収要請通知・満杯時の録画停止ゲート。

方針 (ユーザー決定 2026-08-12):
  - 使用率 80% (WILDLIFE_STORAGE_NOTIFY_PCT) で回収要請を Telegram に通知 (24hに1回まで)
  - 使用率 95% (WILDLIFE_STORAGE_STOP_PCT) で録画を停止しデータを守る (緊急通知)
  - held/ の保留動画は自動削除しない。回収されるまで保全するのが目的。
通知は ZeroClaw の Telegram チャンネル経由 (未設定なら journal ログのみ)。
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path

from field_limits import state_dir

ZEROCLAW_BIN = Path(os.getenv(
    "WILDLIFE_ZEROCLAW_BIN",
    str(Path.home() / "zeroclaw-bin" / "zeroclaw"),
))
NOTIFY_COOLDOWN_SEC = 24 * 3600


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


class StorageGuard:
    def __init__(self, log, videos_dir: str, trap_id: str):
        self.log = log
        self.videos_dir = videos_dir
        self.trap_id = trap_id
        self.notify_pct = _env_int("WILDLIFE_STORAGE_NOTIFY_PCT", 80)
        self.stop_pct = _env_int("WILDLIFE_STORAGE_STOP_PCT", 95)
        self._state_file = state_dir() / "storage_guard.json"
        try:
            self._state = json.loads(self._state_file.read_text())
        except (OSError, ValueError):
            self._state = {}

    def used_pct(self) -> int:
        try:
            usage = shutil.disk_usage(self.videos_dir)
            return int(usage.used * 100 / usage.total)
        except OSError:
            return -1  # 判定不能なら止めない側に倒す (録画継続が既定の安全方針)

    def held_summary(self) -> tuple[int, float]:
        held = Path(self.videos_dir) / "held"
        if not held.is_dir():
            return 0, 0.0
        # check() はメインループが毎周回呼ぶ。通知文に載せる集計値のために
        # 例外を上げてループを落とさない (ファイルが消える競合など)。
        count, total_bytes = 0, 0
        try:
            for path in held.glob("*.mp4"):
                try:
                    total_bytes += path.stat().st_size
                    count += 1
                except OSError:
                    continue
        except OSError as exc:
            self.log.warning("held/ summary failed: %s", exc)
        return count, round(total_bytes / 1048576, 1)

    def _notify(self, level: str, message: str) -> None:
        """Telegram へ通知 (ZeroClaw channel send)。失敗しても運用は続ける。"""
        last = self._state.get(f"notified_{level}", 0)
        if time.time() - last < NOTIFY_COOLDOWN_SEC:
            return
        self.log.warning("Storage %s: %s", level, message)
        if ZEROCLAW_BIN.exists():
            try:
                subprocess.run(
                    [str(ZEROCLAW_BIN), "channel", "send", message,
                     "--channel-id", "telegram"],
                    capture_output=True, timeout=60,
                )
            except (OSError, subprocess.SubprocessError) as exc:
                self.log.warning("Storage notify failed (telegram): %s", exc)
        self._state[f"notified_{level}"] = time.time()
        try:
            tmp = self._state_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self._state))
            os.replace(tmp, self._state_file)
        except OSError:
            pass

    def check(self) -> tuple[int, bool]:
        """(使用率%, 録画してよいか) を返す。ループ先頭で毎回呼ぶ想定 (statvfsは安価)。"""
        pct = self.used_pct()
        if pct < 0:
            return pct, True

        held_count, held_mb = self.held_summary()

        if pct >= self.stop_pct:
            self._notify(
                "stop",
                f"🚨【{self.trap_id}】SD使用率{pct}%が上限{self.stop_pct}%に到達。"
                f"データ保全のため録画を停止しました。至急SDカードの回収をお願いします。"
                f"(保留動画 {held_count}本 / {held_mb}MB)",
            )
            return pct, False

        if pct >= self.notify_pct:
            self._notify(
                "pickup",
                f"📦【{self.trap_id}】SD使用率が{pct}%になりました (回収目安 {self.notify_pct}%)。"
                f"保留動画 {held_count}本 / {held_mb}MB。次回の巡回でSDカードの回収をお願いします。"
                f"{self.stop_pct}%に達すると録画を停止します。",
            )
        else:
            # 回収でしきい値を下回ったら通知状態をリセット (次回の80%で再通知できるように)
            if self._state.pop("notified_pickup", None) is not None or \
               self._state.pop("notified_stop", None) is not None:
                try:
                    tmp = self._state_file.with_suffix(".tmp")
                    tmp.write_text(json.dumps(self._state))
                    os.replace(tmp, self._state_file)
                except OSError:
                    pass

        return pct, True
