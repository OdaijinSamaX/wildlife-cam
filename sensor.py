import logging
import time

try:
    import gpiozero
except ImportError:
    gpiozero = None


class MotionSensor:
    def __init__(self, pin: int = 17):
        self._log = logging.getLogger("wildlife_cam")
        if gpiozero is None:
            self._stub = True
            self._log.warning("gpiozero not available - running in stub mode")
        else:
            self._stub = False
            self._sensor = gpiozero.MotionSensor(pin)

    def is_active(self) -> bool:
        if self._stub:
            return False
        return self._sensor.is_active

    def wait_for_sustained_motion(self, duration: float = 1.0, should_continue=None) -> bool:
        if self._stub:
            raise RuntimeError("gpiozero not available - sustained motion detection not supported")
        interval = 0.1
        # 継続時間はサンプル回数 x interval ではなく time.monotonic() の実時間で測る。
        # ループ 1 周が interval より長引いた場合 (旧実装では should_continue が
        # ブロッキング HTTP を呼び、1 周が数十秒に伸びていた) でも、実際に動体が
        # 連続していた実時間で判定する。active_since は連続検知の開始時刻。
        active_since = None
        while True:
            if should_continue is not None and not should_continue():
                return False
            if self._sensor.is_active:
                if active_since is None:
                    active_since = time.monotonic()
                elif time.monotonic() - active_since >= duration:
                    return True
            else:
                active_since = None
            time.sleep(interval)
