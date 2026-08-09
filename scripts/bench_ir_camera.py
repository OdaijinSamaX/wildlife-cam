#!/usr/bin/env python3
"""IR投光器が「カメラから見て」効いているかを測る。

⚠️ 輝度の平均では判定できない。自動露出が明るさを打ち消すので、IRを点けると
   むしろ平均輝度は下がる(実測: OFF 130 -> ON 64)。**見るべきは露出時間**で、
   IRが光を足した分だけ露出が短くなる(実測: 27,255us -> 240us = 113倍の光量)。

測るもの:
  ① 露出時間の比 (OFF / ON) = IR が実際に足した光量の倍率
  ② 露出時間が落ち着くまでの時間 = WILDLIFE_IR_WARMUP が足りているかの判定
  ③ 白飛び画素の割合 = **投光器がカメラの画角に入っていないか**の自動検出
     画角に入るとカメラは光源に露出を合わせ、被写体が真っ黒になる。
     2026-07-30 の昼の測定でこれを踏んだので、機械的に弾く。

Pi Zero 2 W(実メモリ424MB)向けに raw=None / YUV420。
create_still_configuration はセンサ解像度のバッファを取るので使わない。

  python3 bench_ir_camera.py            # 測定
  python3 bench_ir_camera.py --keep     # 画像も /tmp に PGM で残す
"""

import argparse
import time

import numpy as np
from gpiozero import DigitalOutputDevice
from picamera2 import Picamera2

PIN_IR = 18
WIDTH, HEIGHT = 1920, 1080

# IR ON 後、この時刻(秒)で測る。既定 warmup 0.5s の前後を挟む。
RAMP_POINTS = [0.0, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0]

# Y >= この値を白飛びとみなす
SAT_LEVEL = 250
# 白飛び画素がこの割合を超えたら「光源が画角に入っている」と判定
SAT_WARN_FRACTION = 0.01


def grab(cam):
    """Y平面(輝度)から 平均・白飛び率 と、露出設定を返す。"""
    arr = cam.capture_array("main")
    y = arr[:HEIGHT, :WIDTH]
    md = cam.capture_metadata()
    return {
        "mean": float(y.mean()),
        "sat": float((y >= SAT_LEVEL).mean()),
        "exp": md.get("ExposureTime") or 0,
        "gain": md.get("AnalogueGain") or 0.0,
    }


def save_pgm(path, cam):
    arr = cam.capture_array("main")
    with open(path, "wb") as f:
        f.write(f"P5\n{WIDTH} {HEIGHT}\n255\n".encode())
        f.write(arr[:HEIGHT, :WIDTH].tobytes())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="PGM画像を /tmp に残す")
    ap.add_argument("--settle", type=float, default=5.0, help="測定前のAE安定待ち秒数")
    args = ap.parse_args()

    ir = DigitalOutputDevice(PIN_IR, initial_value=False)
    cam = Picamera2()
    cam.configure(cam.create_video_configuration(
        main={"size": (WIDTH, HEIGHT), "format": "YUV420"}, raw=None, buffer_count=3))
    cam.start()

    try:
        print(f"IR OFF のまま自動露出を安定させています ({args.settle:.0f}秒)...", flush=True)
        time.sleep(args.settle)

        off = grab(cam)
        print(f"\nIR OFF   露出 {off['exp']:>8}us  ゲイン {off['gain']:.2f}  "
              f"輝度 {off['mean']:6.2f}  白飛び {off['sat']*100:5.2f}%")
        if args.keep:
            save_pgm("/tmp/ir_off.pgm", cam)

        print("\nIR ON — 露出の追い込みを追跡 (露出が短くなるほど IR が効いている)")
        print(f"  {'経過':>6}  {'露出us':>8}  {'OFF比':>7}  {'輝度':>7}  {'白飛び%':>7}")
        ir.on()
        t0 = time.monotonic()
        ramp = []
        for target in RAMP_POINTS:
            while time.monotonic() - t0 < target:
                time.sleep(0.005)
            s = grab(cam)
            s["t"] = time.monotonic() - t0
            ramp.append(s)
            ratio = off["exp"] / s["exp"] if s["exp"] else 0
            print(f"  {s['t']:5.2f}s  {s['exp']:>8}  {ratio:6.1f}x  "
                  f"{s['mean']:7.2f}  {s['sat']*100:6.2f}", flush=True)

        if args.keep:
            save_pgm("/tmp/ir_on.pgm", cam)
        final = ramp[-1]
        ir.off()

        print("\n--- 判定 ---")

        # ③ まず配置の妥当性。ここが駄目なら他の数字は意味を持たない。
        if final["sat"] > SAT_WARN_FRACTION:
            print(f"✗ 配置NG: 白飛び画素が {final['sat']*100:.2f}% ある。"
                  "投光器がカメラの画角に入っている疑いが濃い。")
            print("  カメラは光源に露出を合わせるので、被写体は真っ黒になる。")
            print("  → 投光器をカメラの横/上に移し、2つを同じ向きに揃えてから再測定。")
            print("  (以下の数字はこの状態では信用できない)")
        else:
            print(f"✓ 配置OK: 白飛び {final['sat']*100:.2f}% — 光源は画角の外にある")

        # ① IR が足した光量
        light_gain = off["exp"] / final["exp"] if final["exp"] else 0
        print(f"\nIR が足した光量: 露出 {off['exp']}us -> {final['exp']}us "
              f"({light_gain:.1f}倍の明るさ)")
        if light_gain < 2:
            print("  ✗ ほとんど効いていない。距離が遠すぎるか、向きが合っていない")
        elif light_gain < 8:
            print("  △ 効いているが弱い。この距離が実運用の想定なら 96灯への変更を検討")
        else:
            print("  ✓ 十分に効いている")

        # ② 露出が落ち着くまでの時間 = 必要な warmup
        tgt = final["exp"] * 1.25  # 最終露出の1.25倍以内に入ったら実用上収束
        settle = next((s["t"] for s in ramp if s["exp"] and s["exp"] <= tgt), None)
        print()
        if settle is None:
            print(f"露出の収束: {RAMP_POINTS[-1]}秒でも収束せず")
            print("  → WILDLIFE_IR_WARMUP を伸ばすか、露出を固定する(推奨)")
        else:
            print(f"露出の収束: {settle:.2f}秒")
            if settle <= 0.5:
                print("  ✓ WILDLIFE_IR_WARMUP=0.5 で足りている")
            else:
                print(f"  ✗ 0.5秒では足りない。クリップの頭 {settle:.1f}秒が露出オーバーになる")
                print(f"    対策A: WILDLIFE_IR_WARMUP={settle + 0.3:.1f} にする(検知から録画開始が遅れる)")
                print(f"    対策B: 露出を {final['exp']}us / ゲイン {final['gain']:.2f} に固定する")
                print("           (AE収束を待たずに済む。夜間で明るさが一定なら B のほうが良い)")
    finally:
        ir.off()
        ir.close()
        cam.close()
        print("\n消灯・カメラ解放しました。")


if __name__ == "__main__":
    main()
