#!/usr/bin/env python3
"""wildlife-cam ベータ最小版 IR投光器(850nm 48灯ドーム)の駆動ベンチ検証

配線は 2SK4017 で 12V 側の GND(ロー)側を断続する構成:

    Pi GPIO18(物理12番ピン) --[100Ω]-- ゲート
    ゲート --[10kΩ]-- GND           (プルダウン。これが無いと起動時に勝手に点く)
    ドレイン -- IR投光器の黒(−)
    ソース   -- GND (Pi の GND と 電池BOXの黒 と共通)
    電池BOX 赤(+12V) -- IR投光器の赤(+)

  python3 bench_ir.py blink            # ② 2秒ごとの点滅テスト
  python3 bench_ir.py on --secs 30     # ③ テスターで消費電流を測る用
  python3 bench_ir.py off              # 消し忘れたときの保険
  python3 bench_ir.py pulse --secs 10  # 実運用と同じ10秒点灯を1回

IR は LED なのでフライバックダイオードは不要(SR54F はソレノイド専用)。
ソレノイドと違って連続通電の時間制限は無いが、発熱はするので手で触って確認する。
"""

import argparse
import signal
import sys
import time

from gpiozero import DigitalOutputDevice

# --- ピン割り当て (BCM番号) ---
# BCM18 = 物理12番ピン。bench_solenoid.py もこのピンを使うので、
# ソレノイドと IR を同時に配線してはいけない(今フェーズはソレノイド持ち越しなので問題なし)。
PIN_IR = 18


def make_ir():
    """初期値 OFF で確保する。initial_value=False は「掴んだ瞬間に消す」意味。"""
    return DigitalOutputDevice(PIN_IR, initial_value=False)


def cmd_blink(args):
    ir = make_ir()
    print(f"GPIO{PIN_IR} を {args.secs}秒ごとに ON/OFF します。Ctrl-C で終了。")
    print()
    print("見ること:")
    print("  - 850nm は肉眼でも赤い点の集合として薄く見える(正常)")
    print("  - ON にした瞬間に点くか(遅延ゼロが既定。遅れるなら配線かMOSFETを疑う)")
    print("  - 昼間の明るい部屋では、内蔵の光量センサーが働いて点かないことがある。")
    print("    その場合は投光器を手や布で覆って暗くしてから見る")
    print("  - MOSFET の樹脂/金属タブが熱くなっていないか(そっと触る)")
    print()
    n = 0
    try:
        while True:
            ir.on()
            n += 1
            print(f"  {n:3d}  ON ", flush=True)
            time.sleep(args.secs)
            ir.off()
            print(f"       off", flush=True)
            time.sleep(args.secs)
    except KeyboardInterrupt:
        pass
    finally:
        ir.off()
        print(f"\n終了。ON {n} 回。消灯を確認してください。")


def cmd_on(args):
    """テスターで電流を測るための、長めの点灯。

    測りたいのは2つ:
      - 点灯中の電流 (48灯850nm で 0.4〜0.6A 程度のはず)
      - 消灯中の電流 (0mA でなければ MOSFET が閉じ切っていない)
    """
    ir = make_ir()
    print("まず 5秒間 OFF のままにします。この間にテスターで「待機時の電流」を読んでください。")
    print("  期待値: 0mA。数mA でも流れていたら、10kΩ プルダウンかゲート配線を疑う。")
    for i in range(5, 0, -1):
        print(f"  OFF ... {i}", flush=True)
        time.sleep(1)

    print()
    print(f"ここから {args.secs}秒 点灯します。点灯中の電流を読んでください。")
    print("  期待値: 0.4〜0.6A 前後(48灯850nm・12V)。1A を超えるなら配線を疑う。")
    try:
        ir.on()
        for i in range(args.secs, 0, -1):
            print(f"  ON  ... {i}", flush=True)
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n中断しました。")
    finally:
        ir.off()
        print("\n消灯しました。")
        print()
        print("測った値をメモしておくこと。単3アルカリ(約2000mAh)×8本で、")
        print("  1回10秒点灯 = 電流[A] × 10/3600 [Ah] なので、")
        print("  0.5A なら 1回約1.4mAh → 1000回以上もつ計算になる。")


def cmd_pulse(args):
    """実運用と同じ「録画10秒のあいだ点灯」を1回だけ再現する。"""
    ir = make_ir()
    print(f"3秒後に {args.secs}秒 点灯します(実運用の録画1本と同じ長さ)。")
    time.sleep(3)
    try:
        ir.on()
        t0 = time.monotonic()
        time.sleep(args.secs)
    finally:
        ir.off()
        print(f"消灯。実測 {time.monotonic() - t0:.2f}秒 点灯しました。")


def cmd_off(args):
    """何かの拍子に点きっぱなしになったときの保険。"""
    ir = make_ir()
    ir.off()
    print(f"GPIO{PIN_IR} を OFF にしました。")


def main():
    # kill されても消灯するようにしておく(点きっぱなしで電池を空にしないため)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))

    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = p.add_subparsers(dest="mode", required=True)

    b = sub.add_parser("blink", help="点滅させて配線が正しいか見る")
    b.add_argument("--secs", type=float, default=2.0, help="ON/OFF それぞれの秒数")
    b.set_defaults(func=cmd_blink)

    o = sub.add_parser("on", help="長めに点灯してテスターで電流を測る")
    o.add_argument("--secs", type=int, default=30, help="点灯秒数")
    o.set_defaults(func=cmd_on)

    u = sub.add_parser("pulse", help="録画1本ぶん(既定10秒)だけ点灯する")
    u.add_argument("--secs", type=float, default=10.0, help="点灯秒数")
    u.set_defaults(func=cmd_pulse)

    f = sub.add_parser("off", help="消灯させる(保険)")
    f.set_defaults(func=cmd_off)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
