import logging
import threading
import time


class ArmStateMonitor:
    """arm 状態を背景スレッドで定期取得し、検知ループはメモリ値だけを読む。

    検知待機ループ (sensor.wait_for_sustained_motion) は 0.1 秒ごとに
    should_continue を呼ぶ。ここから毎回ブロッキング HTTP (is_armed) を叩くと、
    LTE で IPv6 がブラックホール化した際に 1 イテレーションで connect timeout 分
    (十数秒〜30 秒) ブロックし、PIR のサンプリング周期が破壊されて
    「1 秒間の継続動体検知」が数学的に成立しなくなる (2026-08-08 障害の本丸)。

    そこで arm 状態の問い合わせを背景スレッドに追い出し、ループ側は
    メモリ上の真偽値のみを読む。is_armed()/state() はブロックしない。

    安全思想: 通信断の既定は「保留 (=作動しない)」。一定時間 (staleness_timeout)
    新しい成功応答が無ければ armed とはみなさない。初回の成功応答が来るまでも
    同様に保留する。判定は time.monotonic() を使い、RTC 無し端末の時計飛びに
    影響されないようにする。
    """

    def __init__(
        self,
        arm_source,
        *,
        poll_interval: float = 5.0,
        staleness_timeout: float = 60.0,
        log: logging.Logger | None = None,
    ):
        # arm_source は .is_armed() を持つオブジェクト (WorkerUploader / ChildLinkClient)。
        self._arm_source = arm_source
        self._poll_interval = poll_interval
        self._staleness_timeout = staleness_timeout
        self._log = log or logging.getLogger("wildlife_cam")
        self._lock = threading.Lock()
        self._armed = False
        self._last_success: float | None = None  # time.monotonic()
        self._last_error: str | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run, name="arm-monitor", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                armed = bool(self._arm_source.is_armed())
                with self._lock:
                    self._armed = armed
                    self._last_success = time.monotonic()
                    self._last_error = None
            except Exception as exc:  # 通信断・タイムアウト等はここで握って保留に倒す
                with self._lock:
                    self._last_error = str(exc)
                self._log.warning("Arm state poll failed: %s", exc)
            # stop 要求に即応しつつ次回まで待つ (time.sleep だと停止が遅れる)。
            self._stop.wait(self._poll_interval)

    def state(self) -> str:
        """"armed" / "disarmed" / "comms_loss" / "starting" のいずれかを返す。

        - starting : 初回の成功応答がまだ無い (=保留)
        - comms_loss: 直近の成功応答が古い (=保留)
        - armed / disarmed: 直近の成功応答が新鮮
        """
        with self._lock:
            armed = self._armed
            last = self._last_success
        if last is None:
            return "starting"
        if (time.monotonic() - last) > self._staleness_timeout:
            return "comms_loss"
        return "armed" if armed else "disarmed"

    def is_armed(self) -> bool:
        """メモリ値のみを読む非ブロッキング判定。通信断/初期状態は False (保留)。"""
        return self.state() == "armed"
