#!/usr/bin/env python3
"""透明送信ゲートの判定を合成クリップで検証する (再現可能な回帰テスト)。

    python3 tools/verify_screen_gate.py [--keep] [--rules config/screen_rules_v2.json]

ffmpeg で既知の動きを持つクリップを生成し、motion_screen.py の判定が
設計意図と一致するかを表で出す。閾値やルールを変えたら必ずこれを通すこと。
期待と違う判定が1つでもあれば終了コード 1。

--- クリップ生成の落とし穴 (実際に踏んだので必ず読むこと) ---

1. drawbox は使わない。ffmpeg の drawbox では式中の `t` が「時刻」ではなく
   「線の太さ (thickness)」で、`t=fill` は INT_MAX 相当になる。
   `drawbox=x='100+t*80':t=fill` は箱を画面外に飛ばし、**何も写っていない
   クリップ**を作る。overlay フィルタの `t` は時刻なのでこちらを使う。

2. 揺れの周波数を解析 fps の整数倍にしない。解析は 2fps なので、2Hz の揺れは
   完全にエイリアスして「揺れゼロ」に見える。ここでは 0.7Hz を使う。

どちらも「テストが偶然通ってしまう」種類の罠で、生成物を目視/実測しない限り
気づけない。--keep を付けるとクリップを残すので、疑わしいときは確認すること。
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import motion_screen as ms  # noqa: E402

BG = "color=c=0x333333:s=1280x720:d=10:r=30"

# (名前, 説明, 生成 filter, 許容される判定)
CASES = [
    ("animal", "動物代替: 90x60が横切る",
     ("overlay", 90, 60, "100+t*80", 400), {"wildlife"}),
    ("veg", "植生代替: 小さく揺れる(±15px)",
     ("overlay", 90, 60, "600+15*sin(2*PI*t*0.7)", 400), {"none", "uncertain"}),
    ("veg_wide", "植生代替: 大きく揺れる(±40px)",
     ("overlay", 90, 60, "600+40*sin(2*PI*t*0.7)", 400), {"none", "uncertain"}),
    ("static", "無変化: 静止画",
     ("overlay", 90, 60, "600", 400), {"none"}),
    ("small_corner", "端で小さい動物(遅い)",
     ("overlay", 30, 20, "30+t*8", 40), {"wildlife", "uncertain"}),
    ("slow", "ゆっくり横切る動物",
     ("overlay", 90, 60, "100+t*20", 400), {"wildlife", "uncertain"}),
    ("light", "全画面の輝度変動(照明)", ("geq",), {"none", "uncertain"}),
    ("fade", "全画面の緩やかなフェード", ("fade",), {"none", "uncertain"}),
    ("noise", "微小ノイズのみ", ("noise", 8), {"none"}),
    ("noise_strong", "強いセンサノイズ (sigma=30)", ("noise", 30), {"none"}),
]


def generate(spec, out: Path) -> None:
    kind = spec[0]
    if kind == "overlay":
        _, bw, bh, xexpr, y = spec
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", BG,
               "-f", "lavfi", "-i", f"color=c=white:s={bw}x{bh}:d=10:r=30",
               "-filter_complex", f"[0][1]overlay=x='{xexpr}':y={y}"]
    elif kind == "geq":
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
               "-i", "nullsrc=s=1280x720:d=10:r=30",
               "-vf", "geq=lum='128+100*sin(2*PI*T/3)':cb=128:cr=128"]
    elif kind == "fade":
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
               "-i", "color=c=white:s=1280x720:d=10:r=30",
               "-vf", "fade=t=in:st=0:d=10"]
    else:
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", BG,
               "-vf", f"noise=alls={spec[1]}:allf=t"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", "30", str(out)]
    subprocess.run(cmd, check=True, stdin=subprocess.DEVNULL)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rules", default=None)
    parser.add_argument("--keep", action="store_true", help="生成クリップを残す")
    args = parser.parse_args()

    rules = ms.load_rules(args.rules)
    tmp = Path(tempfile.mkdtemp(prefix="gate-verify-"))
    print(f"rules={rules['version']} screener={ms.SCREENER_VERSION}  clips={tmp}\n")

    hdr = (f"{'clip':<15}{'期待':<20}{'実測':<11}{'blob%':>8}"
           f"{'net_tr%':>9}{'excur%':>8}{'act_s':>7}{'ms':>7}")
    print(hdr)
    print("-" * len(hdr))

    failures = []
    for name, desc, spec, expected in CASES:
        clip = tmp / f"{name}.mp4"
        generate(spec, clip)
        started = time.time()
        rec = ms.screen_clip(str(clip), rules)
        wall = int((time.time() - started) * 1000)
        f = rec.get("features") or {}
        ok = rec["decision"] in expected
        if not ok:
            failures.append((name, desc, expected, rec))
        print(f"{name:<15}{'/'.join(sorted(expected)):<20}{rec['decision']:<11}"
              f"{f.get('max_blob_pct', -1):>8}{f.get('net_travel_pct', -1):>9}"
              f"{f.get('max_excursion_pct', -1):>8}{f.get('active_seconds', -1):>7}"
              f"{wall:>7}  {'' if ok else '<<< MISMATCH'}")

    for name, desc, expected, rec in failures:
        print(f"\n[{name}] {desc}\n  期待={sorted(expected)} 実測={rec['decision']}")
        print(f"  features: {json.dumps(rec.get('features'), ensure_ascii=False)}")
        for e in rec["rule_evaluations"]:
            print(f"    {e['rule']:<22} value={str(e['value']):<9} "
                  f"threshold={str(e['threshold']):<14} {'PASS' if e['pass'] else 'fail'}")

    print(f"\n{len(CASES) - len(failures)}/{len(CASES)} 一致")
    if not args.keep:
        for p in tmp.glob("*.mp4"):
            p.unlink()
        tmp.rmdir()
    else:
        print(f"クリップを残しました: {tmp}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
