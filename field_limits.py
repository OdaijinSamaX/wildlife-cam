"""現地の LTE 従量課金対策: 送信量だけに上限をかけ、撮影は絞らない。

屋久島は povo(従量) で、実地テストでは 23 分で 271MB を送っていた。枝や熱源への
PIR 誤検知でフル画質動画を送り続けたのが原因。

本人の方針（撮り逃しを作らないことが最優先）:
  「5 分の撮影制限をかけるのではなく、通信上限を 1 時間あたり 250MB に設定し、
    それ以上の撮影は SD カードに保存する形なら、夜間 12 時間で最大でも 3GB で足りる」

したがって:
  - 撮影は制限しない（クールダウンは既定 0＝無効。将来必要になれば本人が上げられる）。
  - サーキットブレーカー(一定本数で自動休止)は既定 OFF。撮り続けたい方針と矛盾するため、
    コードは予備として残すが既定では絶対に発火しない。
  - ★本体＝送信量の上限: 直近 1 時間で実送信したバイト数が
    WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR (既定 250MB) を超えたら「送信のみ」止め、録画は続ける。
    予算が回復し次第、SD の貯まった分から順次送る。LTE のときだけ数える。WiFi は無制限。

状態は永続化 (WILDLIFE_STATE_DIR。既定 /var/lib/wildlife-cam、書けなければ app_home/state)。
サービス再起動でも予算カウンタが継続する。
"""

import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from app_paths import get_app_home

MIB = 1024 * 1024
WINDOW_SEC = 3600  # 送信予算のローリングウィンドウ幅(1時間)


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


def _env_flag(name: str, default: bool) -> bool:
    val = os.getenv(name, "").strip().lower()
    if val == "":
        return default
    return val not in ("0", "false", "no", "off")


def state_dir() -> Path:
    """永続状態の置き場所。/var/lib を優先し、書けなければ app_home 配下へ退避する。"""
    configured = os.getenv("WILDLIFE_STATE_DIR", "").strip()
    candidates = [configured] if configured else ["/var/lib/wildlife-cam"]
    candidates.append(os.path.join(get_app_home(), "state"))
    for cand in candidates:
        if not cand:
            continue
        try:
            path = Path(cand)
            path.mkdir(parents=True, exist_ok=True)
            probe = path / ".write_test"
            probe.write_text("ok", encoding="ascii")
            probe.unlink()
            return path
        except OSError:
            continue
    fallback = Path(os.path.join(get_app_home(), "state"))
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _atomic_write(path: Path, text: str) -> None:
    """電源断でも 0 バイトにならないよう temp+rename で書く。"""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def on_lte() -> bool:
    """default route が wwan0 なら LTE と判定する。

    判定規則は scripts/net-status.sh と同じ（default route の dev を見る）。
    bash と Python で実装言語が違うため関数自体は共有できないが、規則は一致させている。
    """
    try:
        out = subprocess.run(
            ["ip", "-o", "route", "show", "default"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    for line in out.splitlines():
        toks = line.split()
        for i, tok in enumerate(toks):
            if tok == "dev" and i + 1 < len(toks):
                return toks[i + 1] == "wwan0"
    return False


class FieldLimiter:
    def __init__(self, log):
        self.log = log
        self.dir = state_dir()

        # 送信予算(本体)
        self.budget_bytes = _env_int("WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR", 250) * MIB
        # バックログがこの本数を超えたら「新しい順」で送る(実演で最新を優先)
        self.newest_first_backlog = _env_int("WILDLIFE_UPLOAD_NEWEST_FIRST_BACKLOG", 10)

        # 撮影クールダウン(既定 0=無効)
        self.cooldown_sec = _env_int("WILDLIFE_MOTION_COOLDOWN_SEC", 0)
        # サーキットブレーカー(既定 OFF)
        self.breaker_enabled = _env_flag("WILDLIFE_BURST_PAUSE_ENABLED", False)
        self.burst_threshold = _env_int("WILDLIFE_BURST_THRESHOLD", 6)
        self.burst_window = _env_int("WILDLIFE_BURST_WINDOW_SEC", 1800)
        self.burst_pause = _env_int("WILDLIFE_BURST_PAUSE_SEC", 3600)

        self.uploads_file = self.dir / "uploads"      # "epoch bytes" 行の送信履歴
        self.recordings_file = self.dir / "recordings"  # 録画時刻(直近1時間表示・ブレーカー用)
        self.breaker_file = self.dir / "breaker_until"
        self.status_file = self.dir / "status"

        self._skip_count = 0
        self._last_skip_log = 0.0
        self._last_budget_log = 0.0

        self.log.info(
            "Field limiter: upload_budget=%dMB/h newest_first_backlog=%d cooldown=%ds "
            "breaker=%s state=%s",
            self.budget_bytes // MIB,
            self.newest_first_backlog,
            self.cooldown_sec,
            "on" if self.breaker_enabled else "off",
            self.dir,
        )

    # ================= 送信予算(本体) =================
    def _read_uploads(self) -> list[tuple[float, int]]:
        events = []
        try:
            for line in self.uploads_file.read_text().splitlines():
                parts = line.split()
                if len(parts) == 2:
                    events.append((float(parts[0]), int(parts[1])))
        except (OSError, ValueError):
            return []
        return events

    def _write_uploads(self, events: list[tuple[float, int]]) -> None:
        _atomic_write(
            self.uploads_file,
            "".join(f"{e:.0f} {b}\n" for e, b in events),
        )

    def _events_in_window(self, now: float | None = None) -> list[tuple[float, int]]:
        now = now if now is not None else time.time()
        cutoff = now - WINDOW_SEC
        return [(e, b) for e, b in self._read_uploads() if e >= cutoff]

    def budget_used_bytes(self) -> int:
        return sum(b for _, b in self._events_in_window())

    def budget_remaining_bytes(self) -> int:
        return max(0, self.budget_bytes - self.budget_used_bytes())

    def upload_blocked_by_budget(self, is_lte: bool) -> bool:
        """LTE 経由でかつ直近 1 時間の送信量が上限に達していれば送信を止める。WiFi は無制限。"""
        if not is_lte or not self.budget_bytes:
            return False
        return self.budget_used_bytes() >= self.budget_bytes

    def note_uploaded(self, nbytes: int, is_lte: bool) -> None:
        """送信成功時、LTE 経由なら送信履歴に (時刻, バイト数) を記録する。"""
        if not is_lte or nbytes <= 0:
            return
        now = time.time()
        events = self._events_in_window(now)  # 同時に古い履歴を掃除
        events.append((now, nbytes))
        self._write_uploads(events)

    def next_budget_resume_epoch(self) -> float:
        """予算超過中、最古のイベントが窓から抜けて予算が空く時刻の目安。"""
        events = sorted(self._events_in_window())
        if not events:
            return 0.0
        return events[0][0] + WINDOW_SEC

    def note_budget_log(self) -> None:
        now = time.time()
        if now - self._last_budget_log >= 600:
            resume = self.next_budget_resume_epoch()
            resume_hm = datetime.fromtimestamp(resume).astimezone().strftime("%H:%M") if resume else "?"
            self.log.warning(
                "直近1時間の LTE 送信量が上限に到達 (%dMB/%dMB) -- 送信を一時停止し録画は継続。"
                "SD に貯めて %s 頃から順次再開",
                self.budget_used_bytes() // MIB,
                self.budget_bytes // MIB,
                resume_hm,
            )
            self._last_budget_log = now

    def prefer_newest_first(self, backlog_count: int) -> bool:
        """バックログが閾値を超えたら新しい順で送る（実演で最新を優先）。"""
        return self.newest_first_backlog > 0 and backlog_count > self.newest_first_backlog

    # ================= 録画履歴(表示・ブレーカー用) =================
    def _read_epochs(self) -> list[float]:
        try:
            return [float(x) for x in self.recordings_file.read_text().split() if x]
        except (OSError, ValueError):
            return []

    def _write_epochs(self, epochs: list[float]) -> None:
        _atomic_write(self.recordings_file, "\n".join(f"{e:.0f}" for e in epochs) + "\n")

    def note_recording(self) -> None:
        """1 本録画した後に呼ぶ。表示用の履歴更新と、(有効時のみ)ブレーカー判定。"""
        now = time.time()
        epochs = self._read_epochs()
        epochs.append(now)
        horizon = now - max(self.burst_window, 3600)
        epochs = [e for e in epochs if e >= horizon]
        self._write_epochs(epochs)

        if not self.breaker_enabled or not self.burst_threshold:
            return
        window_start = now - self.burst_window
        in_window = [e for e in epochs if e >= window_start]
        if len(in_window) >= self.burst_threshold and self.breaker_remaining() <= 0:
            until = now + self.burst_pause
            _atomic_write(self.breaker_file, f"{until:.0f}\n")
            resume = datetime.fromtimestamp(until).astimezone().strftime("%H:%M")
            self.log.warning(
                "誤検知とみられる連続録画を検出 (%d本/%d分) -- 録画を%d分休止。再開予定 %s",
                len(in_window), self.burst_window // 60, self.burst_pause // 60, resume,
            )

    def recordings_last_hour(self) -> int:
        cutoff = time.time() - 3600
        return len([e for e in self._read_epochs() if e >= cutoff])

    # ================= クールダウン / ブレーカー(既定OFF) =================
    def cooldown_remaining(self) -> float:
        if self.cooldown_sec <= 0:
            return 0.0
        epochs = self._read_epochs()
        last = max(epochs) if epochs else 0.0
        return max(0.0, self.cooldown_sec - (time.time() - last))

    def breaker_until(self) -> float:
        try:
            return float(self.breaker_file.read_text().strip() or 0)
        except (OSError, ValueError):
            return 0.0

    def breaker_remaining(self) -> float:
        return max(0.0, self.breaker_until() - time.time())

    def maybe_resume_breaker(self) -> None:
        until = self.breaker_until()
        if until and time.time() >= until:
            try:
                self.breaker_file.unlink(missing_ok=True)
            except OSError:
                pass
            self.log.info("自動休止が明けました -- 撮影を再開します")

    def record_block_reason(self) -> str | None:
        """録画してよいか。良ければ None。既定設定では常に None（撮影を絞らない）。"""
        if self.breaker_enabled and self.breaker_remaining() > 0:
            return "paused"
        if self.cooldown_remaining() > 0:
            return "cooldown"
        return None

    def note_skip(self, reason: str) -> None:
        self._skip_count += 1
        now = time.time()
        if now - self._last_skip_log >= 300:
            self.log.info(
                "撮影抑制中に PIR 検知を %d 回スキップ (直近, 理由=%s)", self._skip_count, reason
            )
            self._last_skip_log = now
            self._skip_count = 0

    # ================= 見える化 =================
    def write_status(self, mode: str, is_lte: bool, storage_pct: int | None = None) -> None:
        """field-status.sh が読む key=value スナップショット。"""
        blocked = self.upload_blocked_by_budget(is_lte)
        resume = self.next_budget_resume_epoch() if blocked else 0.0
        lines = [
            f"mode={mode}",
            f"on_lte={1 if is_lte else 0}",
            f"budget_used_bytes={self.budget_used_bytes()}",
            f"budget_cap_bytes={self.budget_bytes}",
            f"budget_blocked={1 if blocked else 0}",
            f"budget_resume_epoch={int(resume)}",
            f"recordings_last_hour={self.recordings_last_hour()}",
            f"cooldown_remaining={int(self.cooldown_remaining())}",
            f"breaker_remaining={int(self.breaker_remaining())}",
            f"updated_at={int(time.time())}",
        ]
        if storage_pct is not None and storage_pct >= 0:
            lines.insert(-1, f"storage_pct={storage_pct}")
        try:
            _atomic_write(self.status_file, "\n".join(lines) + "\n")
        except OSError:
            pass
