"""arm 確認が検知ループをブロックしないことの自動検証。

2026-08-08 障害の本丸: LTE で v6 がブラックホール化すると is_armed() が 1 回
最長 ~30 秒ブロックし、それを PIR 待機ループ(0.1s 周期)から毎周呼ぶために
サンプリング周期が壊れ、sustained motion が数学的に成立しなくなっていた。

ここでは「is_armed が長時間ブロックしても」
  1. 検知ループが読む arm 判定 (ArmStateMonitor.is_armed) は即座に返る
  2. sensor.wait_for_sustained_motion のサンプリング周期(=実時間)が保たれる
  3. 通信断/初期状態では「保留(False)」に倒れる (安全思想)
ことを、フェイク uploader で確認する。

実機不要・stdlib のみ。実行:
    python3 -m unittest tests.test_arm_gate_nonblocking
    (または) python3 tests/test_arm_gate_nonblocking.py
"""

import logging
import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from arm_monitor import ArmStateMonitor  # noqa: E402
from sensor import MotionSensor  # noqa: E402

# テスト中の警告ログは黙らせる (poll 失敗を意図的に起こすため)。
logging.getLogger("wildlife_cam").addHandler(logging.NullHandler())
logging.getLogger("wildlife_cam").propagate = False


class BlockingArmSource:
    """is_armed() が block 秒だけブロックするフェイク (v6 ブラックホール相当)。"""

    def __init__(self, block: float, armed: bool = True, fail: bool = False):
        self.block = block
        self.armed = armed
        self.fail = fail
        self.calls = 0

    def is_armed(self) -> bool:
        self.calls += 1
        time.sleep(self.block)
        if self.fail:
            raise RuntimeError("simulated comms loss")
        return self.armed


class _FakeSensor:
    def __init__(self, active: bool):
        self.is_active = active


def _make_sensor(active: bool) -> MotionSensor:
    # gpiozero を触らずに MotionSensor を組み立てる。
    sensor = MotionSensor.__new__(MotionSensor)
    sensor._log = logging.getLogger("wildlife_cam")
    sensor._stub = False
    sensor._sensor = _FakeSensor(active)
    return sensor


class ArmGateNonBlockingTest(unittest.TestCase):
    def test_monitor_read_is_nonblocking_even_with_30s_source(self):
        # 30 秒級のブロックを 1.5 秒で代表させる (テストを速く保つ)。
        source = BlockingArmSource(block=1.5, armed=True)
        monitor = ArmStateMonitor(
            source, poll_interval=0.01, staleness_timeout=100.0
        )
        monitor.start()
        try:
            # 検知ループが読む is_armed() は、背景 poll がブロック中でも即返る。
            worst = 0.0
            for _ in range(200):
                t0 = time.monotonic()
                monitor.is_armed()
                worst = max(worst, time.monotonic() - t0)
            self.assertLess(
                worst,
                0.05,
                f"loop-side is_armed() blocked for {worst:.3f}s (source block=1.5s)",
            )
        finally:
            monitor.stop()

    def test_sampling_period_is_preserved(self):
        # 背景 arm 源が毎回 1.5 秒ブロックしても、sustained motion の判定時間は
        # duration(0.5s) 前後で完了する (旧実装では ~数十秒に伸びていた)。
        source = BlockingArmSource(block=1.5, armed=True)
        monitor = ArmStateMonitor(
            source, poll_interval=0.01, staleness_timeout=100.0
        )
        monitor.start()
        try:
            # 初回の成功応答(=armed)を待つ。
            deadline = time.monotonic() + 5.0
            while monitor.state() != "armed" and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertEqual(monitor.state(), "armed", "monitor never became armed")

            sensor = _make_sensor(active=True)
            t0 = time.monotonic()
            detected = sensor.wait_for_sustained_motion(
                0.5, should_continue=monitor.is_armed
            )
            elapsed = time.monotonic() - t0
            self.assertTrue(detected)
            # 0.5s の連続検知が 1.0s 以内に成立すること (孤立した arm ブロックに
            # 引きずられていない)。旧実装なら 1.5s+ に伸びていた。
            self.assertLess(
                elapsed, 1.0, f"sustained-motion took {elapsed:.3f}s (expected ~0.5s)"
            )
        finally:
            monitor.stop()

    def test_hold_before_first_success_and_on_comms_loss(self):
        # 初回成功前は "starting"(=保留)。
        source = BlockingArmSource(block=10.0, armed=True)
        monitor = ArmStateMonitor(source, poll_interval=0.01, staleness_timeout=100.0)
        monitor.start()
        try:
            self.assertEqual(monitor.state(), "starting")
            self.assertFalse(monitor.is_armed())
        finally:
            monitor.stop()

        # poll が失敗し続ける間も保留(False)を返し、例外は外へ漏らさない。
        failing = BlockingArmSource(block=0.0, fail=True)
        monitor2 = ArmStateMonitor(failing, poll_interval=0.01, staleness_timeout=100.0)
        monitor2.start()
        try:
            time.sleep(0.1)
            self.assertFalse(monitor2.is_armed())
            self.assertGreater(failing.calls, 0)
        finally:
            monitor2.stop()

    def test_stale_success_falls_back_to_hold(self):
        # 一度 armed になっても、応答が staleness を超えて古くなれば保留に倒れる。
        source = BlockingArmSource(block=0.0, armed=True)
        monitor = ArmStateMonitor(source, poll_interval=0.01, staleness_timeout=0.2)
        monitor.start()
        try:
            deadline = time.monotonic() + 2.0
            while monitor.state() != "armed" and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertEqual(monitor.state(), "armed")
            # poll を止めて応答を古くする。
            monitor.stop()
            time.sleep(0.3)
            self.assertEqual(monitor.state(), "comms_loss")
            self.assertFalse(monitor.is_armed())
        finally:
            monitor.stop()


if __name__ == "__main__":
    unittest.main(verbosity=2)
