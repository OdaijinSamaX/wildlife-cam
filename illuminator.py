import logging
import os
from contextlib import contextmanager

try:
    import gpiozero
except ImportError:
    gpiozero = None


# BCM18 = 物理12番ピン。100Ω を介して 2SK4017 のゲートへ入れ、
# 12V 側のローサイド(IR投光器の黒線)を断続する。
# ゲート-GND 間の 10kΩ プルダウンは必須で、これが無いと Pi の起動中
# (GPIO がハイインピーダンスの期間)に投光器が勝手に点く。
#
# ⚠️ bench_solenoid.py も同じ GPIO18 を使う。ソレノイドを配線したまま
# このモジュールを有効にすると、録画のたびにソレノイドが発射される。
# 機構を実装する段では、どちらかのピンを必ず変えること。
DEFAULT_IR_PIN = 18


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


class Illuminator:
    """近赤外(850nm)投光器の点消灯。

    投光器側に光量センサーが内蔵されていて、明るい場所では通電しても
    点灯しない。したがって「夜だけ点ける」判定をソフト側に持つ必要はなく、
    録画中は常に通電してよい。

    設計上の約束:
      - 既定は消灯。掴んだ瞬間と手放す瞬間に必ず OFF にする。
      - 例外が飛んでも点きっぱなしにしない(電池を空にしないため)。
      - GPIO が使えない環境ではスタブとして黙って何もしない。録画自体は
        止めない(照明が無くても昼間なら撮れるし、撮り逃しの方が痛い)。
    """

    def __init__(self, pin: int | None = None, warmup: float | None = None):
        self._log = logging.getLogger("wildlife_cam")
        self._pin = DEFAULT_IR_PIN if pin is None else pin
        # 点灯自体は即時だが、カメラの自動露出が暗所→照明ありに追従するまで
        # 数フレームかかる。録画の頭が白飛び/黒つぶれするのを避けるための先行点灯。
        self._warmup = _env_float("WILDLIFE_IR_WARMUP", 0.5) if warmup is None else warmup
        self._device = None

        if os.getenv("WILDLIFE_IR_ENABLED", "1").strip() == "0":
            self._log.info("IR illuminator disabled by WILDLIFE_IR_ENABLED=0")
            return

        if gpiozero is None:
            self._log.warning("gpiozero not available - IR illuminator runs as a stub")
            return

        try:
            self._device = gpiozero.DigitalOutputDevice(self._pin, initial_value=False)
        except Exception:
            # ピンが他プロセスに掴まれている等。照明が無いだけで撮影は続けたい。
            self._log.exception("Failed to claim GPIO%d - IR illuminator disabled", self._pin)
            self._device = None
            return

        self._log.info("IR illuminator ready on GPIO%d (warmup %.2fs)", self._pin, self._warmup)

    @property
    def available(self) -> bool:
        return self._device is not None

    def on(self) -> None:
        if self._device is None:
            return
        try:
            self._device.on()
        except Exception:
            self._log.exception("IR illuminator on() failed")

    def off(self) -> None:
        if self._device is None:
            return
        try:
            self._device.off()
        except Exception:
            self._log.exception("IR illuminator off() failed")

    @contextmanager
    def lit(self):
        """録画のあいだだけ点灯する。

        with を抜けるときは例外経路でも必ず消灯する。
        """
        import time

        self.on()
        if self._device is not None and self._warmup > 0:
            time.sleep(self._warmup)
        try:
            yield self
        finally:
            self.off()

    def close(self) -> None:
        if self._device is None:
            return
        try:
            self._device.off()
            self._device.close()
        except Exception:
            self._log.exception("IR illuminator close failed")
        finally:
            self._device = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
