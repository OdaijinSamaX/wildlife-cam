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
        elapsed = 0.0
        interval = 0.1
        while True:
            if should_continue is not None and not should_continue():
                return False
            if self._sensor.is_active:
                elapsed += interval
                if elapsed >= duration:
                    return True
            else:
                elapsed = 0.0
            time.sleep(interval)
