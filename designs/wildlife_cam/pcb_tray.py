"""wildlife-cam 基板トレー（Raspberry Pi Zero 2 W を載せて背面から差し込む）.

`camera_unit.py` の本体に、**背面（開口側）から差し込む** C チャンネル式のトレー。
Pi Zero 2 W を 4 本の M2.5 タッピングねじで留め、本体側の棚に載せて
クリック止めで抜けを止める。

## なぜスライドレール（アリ溝）ではないのか — **これが本設計の要点**

本体には元々 z 方向のアリ溝レール（z 128〜194）が作ってあった。
**それは蓋の締結 6 点（D-019）と両立しない。**

```
蓋の柱が塞ぐ x    26.9 〜 35.1（両側）  ->  内側に残る幅 53.8 mm
Pi Zero 2 W の幅  65.0 mm             ->  **柱の z を通り抜けられない**
柱の影のない z    146.1 〜 181.3 = 35.2 mm
Pi の z 方向の丈  30.0 mm             ->  **動かせるのは 5.2 mm しかない**
```

もう 1 つ、**背面の開口は x ±37 しかない**（合わせ面の land が 2 mm 内側へ
張り出しているため）。側壁は x ±39 なので、**側壁に付けたアリ溝に届く幅の
トレーは、そもそも背面の開口を通れない。** だから受けは側壁から
x = ±34.5 まで内側へ伸ばし、トレーは ±36.3 に収めてある。
x 方向の位置決めは、棚の外側に立てた**リップ（x ±36.6）**が受け持つ。

つまり **Pi を載せたトレーを z 方向にスライドさせる余地が無い。**
アリ溝は端から差し込むしかないので、この時点で不成立である。
（レール自体にも「宣言 z 128〜194 に対して実物が z 62〜128」という
押し出し方向の不具合があった。同時に直した。）

代わりに **背面から差し込み、棚に載せ、クリックで止める。** 経緯は
`docs/pcb-tray.md`、決定は **D-021**。

## 座標

  `camera_unit.py` と**同じ座標系**（原点は箱の前面外側・下端・左右中央）。
  そのままブーリアンで本体と突き合わせられるようにしてある
  （`tests/test_pcb_tray.py` が「本体と食い合わない」ことを実測する）。

## 何で保持されているか（役割分担）

| 向き | 何が受けるか |
|---|---|
| -Z（落下） | 本体側の**棚**の天面。トレーの自重はここが持つ |
| +Z（浮き上がり） | 本体側の**上の押さえ**（遊び 1.2 mm） |
| ±X | 側壁（片側 0.5 mm の隙間） |
| -Y（押し込みすぎ） | 本体側の**前の当たり** |
| **+Y（抜け）** | **クリック止めの歯**（蓋を開けているとき）/ **蓋**（閉めているとき） |

**クリック止めの本当の仕事は「蓋を開けて作業している間にトレーが落ちないこと」**
である。蓋が閉まっていれば +Y は蓋が塞ぐ。屋久島の林床に基板を落とさないための
最小限の機構、という位置づけ（`docs/AGENTS.md` §4.9.3-1）。

引き出すときは**指で 0.8 mm 持ち上げながら手前に引く**。工具は要らない。
掴み代として背面側にタブを 2 枚立ててある（手袋をした手で摘める）。

## ポカヨケ（原則 3）— 上下・左右・前後のどれを間違えても座らない

**-X 側の棚だけ 2.5 mm 高く、トレーの -X 側の下隅はそのぶん欠けている。**
向きを間違えると、欠けが逆側や上側に来て

  - **低い方の棚（+X）に、欠けていない縁が乗る** -> 2.5 mm 浮いて上の押さえに当たる
  - **高い方の棚（-X）に、欠けた縁が来る** -> 板が斜めになって座らない

のどちらかになる。`tests/test_pcb_tray.py` が 3 通りの反転を**実際に回転させて、
z を ±6 mm 総当たりしてもブーリアンで必ず当たる**ことを確かめている。
さらに**対照実験**として「段違いを消すと左右反転が座ってしまう」ことも
テストにしてある（ポカヨケの根拠が段違いであることの裏取り）。

## 造形姿勢

```
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}   板を寝かせ、ボスとタブを上に立てる
```

  - 設計 Y が造形 Z になるので、**板の前面が第 1 層**。平らな面が出る
  - Pi のボス（4.5 mm）と掴みタブ（10 mm）は**上向きに立つ**のでサポート不要
  - クリックの歯のフランクは 45 度。造形 Z 方向から見ても 45 度なのでサポート不要
  - 差し込み方向（設計 Y）は造形 Z と平行 = **積層の段差を横切る。**
    原則から外れる理由は `camera_unit.SLIDE_AXIS_NOTE` に書いた
    （z 方向は柱で塞がっている / 精度嵌合ではなく落とし込み / 隙間 0.5 mm）

## `SEAL_SPANS` と `CAPTIVE_SCREWS` を宣言しない理由

  - **パッキンを潰す合わせ面が無い。** これは箱の中に入る部品で、防水は
    本体と蓋の合わせ面が受け持つ（`docs/AGENTS.md` §6）。**考え忘れではない**
  - **現地で外すねじが無い。** Pi を留める M2.5 x 4 本は作業台で締めるもので、
    現地でトレーを出し入れするのに工具は要らない（§4.9 原則 1 の対象外）

## 未確定事項

  - **M2.5 タッピングねじの下穴 φ2.1 は推定。** 実物で確かめること
  - Pi の実装部品高さ（`parts/pi_zero_2w`）は推定のままなので、
    ボスの高さ 4.5 mm は Pi の下面クリアランスを実測したら見直す
  - **クリック止めの保持力を計算していない。** 歯 0.8 mm x 45 度でどれだけの
    +Y 荷重に耐えるかは実機で見ること（`docs/pcb-tray.md` §6）
  - OTG ケーブルをトレーに固定する結束点（未設計）
"""

import cadquery as cq

from harness import feature, fit
from harness.component import Component
from designs.wildlife_cam import camera_unit as cu

DESIGN_NAME = "pcb_tray"
FIT_TABLE = fit.ASA_P1S

_U = cu.PARAMS

PARAMS = {
    # --- 本体から導出する（**二重に持たない**） ---
    "z0": _U["tray_z0"],                    # 149.3
    "z1": _U["tray_z1"],                    # 176.9（縁の上端）
    "y0": _U["tray_y0"],                    # 23.9
    "key_step": _U["tray_key_step"],        # 2.5
    "seat_x": _U["tray_seat_x"],            # 34.5
    "gap": _U["tray_gap"],                  # 0.3
    "detent_y0": _U["detent_y0"],
    "detent_w": _U["detent_w"],
    "detent_h": _U["detent_h"],
    # --- トレー自身 ---
    "plate_t": 2.5,              # 設計値。板厚
    "detent_clear": 0.15,        # 歯と切り欠きの隙間（片側）
    "key_w": 2.3,                # ポカヨケの欠きの x 幅（-X 側の下隅）
    #: **中央だけ 0.6 mm 高くする。** 上の取付ボス (z=174.5 / φ5.4) は z=177.2 まで
    #: 伸びるので、縁と同じ 176.9 で切ると 0.3 mm 宙に浮く。
    #: 上の押さえは x >= 34.5 にしかいないので、中央を高くしても当たらない。
    "top_mid_extra": 0.6,
    "top_step_x": 33.0,          # ここより外側は z1 まで（押さえの下を通る）
    # Pi の取り付け（穴ピッチはデータシート）
    "pi_hole_pitch_x": 58.0,     # Raspberry Pi 機構図
    "pi_hole_pitch_z": 23.0,     # 同上
    "boss_dia": 5.4,             # 設計値。下穴 2.1 の周りに 1.65 の肉が残る
    "boss_pilot": 2.1,           # 推定（M2.5 タッピングの下穴。未実測）
    # 掴み代
    "tab_x0": 33.3,              # Pi の縁 (32.5) から 0.8 逃がす
    "tab_x1": 36.0,
    "tab_z0": 155.0,
    "tab_z1": 173.0,
    "tab_h": 10.0,               # 背面へ立てる高さ
    "min_wall": 1.6,
    "feature_margin": 0.8,
    #: **size 6 では「U」と「P」の間に残る肉が 1.11 mm しかなく `wall` が落ちる。**
    #: 文字間の隙間も字の大きさに比例するので、大きくすると解決する。
    #: 板は 72 x 28 mm あるので size 10 でも余裕で入る。
    "label_size": 10.0,          # 設計値（wall 1.6 を満たす下限より上）
    "label_depth": 0.6,
}

#: 板を寝かせ、ボスとタブを上へ立てる。板の前面が第 1 層。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}
#: 差し込み方向。原則から外している根拠は camera_unit.SLIDE_AXIS_NOTE。
SLIDE_AXIS = cu.SLIDE_AXIS

_PI = cu.PI_BOX


def _pi_envelope(clearance: float):
    """Pi の外形 + クリアランス。**座面（-Y 側）には足さない。**

    ボスの天面と Pi の下面は**接するのが正しい**（AGENTS.md §4）。
    ここにクリアランスを足すと、正しい設計が clearance FAIL になる。
    """
    c = clearance
    sx, sy, sz = _PI.size
    cx, cy, cz = _PI.center
    y0 = cy - sy / 2                       # 座面。ここだけ太らせない
    return cq.Solid.makeBox(
        sx + 2 * c, sy + c, sz + 2 * c,
        cq.Vector(cx - sx / 2 - c, y0, cz - sz / 2 - c),
    )


COMPONENTS = [
    Component(
        name="pi", shape=_PI.solid(0.0), envelope_fn=_pi_envelope,
        notes="Pi Zero 2 W。下面はボスの天面に載る（意図した接触なのでクリアランス 0）",
        dimension_source="datasheet+measured:2026-08-22",
    ),
]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 1.0,
    "openings_match_tol_mm": 0.1,
    #: **貫通はゼロ。** Pi の下穴 4 つは止まり穴で、板の裏まで抜けていない。
    #: 抜けたらここで FAIL になる（箱の中の部品なので防水には関係しないが、
    #: 「下穴が抜けた = ねじが板の裏へ突き出る」を検出したい）。
    "expected_openings": [],
}

SECTIONS = [
    {"name": "yz_boss", "origin": (29.0, 0, 0), "normal": (-1, 0, 0)},
    {"name": "xy_detent", "origin": (0, 0, 148.2), "normal": (0, 0, -1)},
]


def x_out(p=PARAMS) -> float:
    """トレーの左右の端。**本体の位置決めリップから導出する**（二重に持たない）.

    背面の開口は x ±37（リムの段のぶん）しかないので、ここが 37 を超えたら
    そもそも箱に入らない。`tests/test_pcb_tray.py` が実測で押さえている。
    """
    return cu.tray_x_out(cu.PARAMS)


def y1(p=PARAMS) -> float:
    return p["y0"] + p["plate_t"]


def key_z0(p=PARAMS) -> float:
    """-X 側の縁の下端 = -X 側の棚の天面（+X より key_step だけ高い）.

    既定値は本体から導出しているが、**ネガティブテストが上書きできるように**
    自分の PARAMS を経由させてある（ポカヨケが効いている根拠の裏取りに使う）。
    一致することは `tests/test_pcb_tray.py` が毎回確かめる。
    """
    return p["z0"] + p["key_step"]


def top_mid(p=PARAMS) -> float:
    """板の中央部の上端。取付ボスが宙に浮かないように縁より高くしてある."""
    return p["z1"] + p["top_mid_extra"]


def boss_positions(p=PARAMS):
    """Pi の取付穴 4 つ (x, z)。**Pi の実際の中心から出す**（二重に持たない）."""
    cx, _cy, cz = _PI.center
    hx, hz = p["pi_hole_pitch_x"] / 2, p["pi_hole_pitch_z"] / 2
    return [(cx + sx * hx, cz + sz * hz) for sx in (-1, 1) for sz in (-1, 1)]


def _tooth(sign, p=PARAMS):
    """クリック止めの歯。棚の天面から下へ 45 度の三角。

    本体側の切り欠き（`camera_unit._tray_seat`）と**同じ y 中心**から出す。
    """
    z_top = cu.tray_shelf_top(cu.PARAMS, sign)
    h = p["detent_h"] - p["detent_clear"]
    yc = p["detent_y0"] + p["detent_w"] / 2
    pts = [(yc - h, z_top + 0.2), (yc, z_top - h), (yc + h, z_top + 0.2)]
    xa = sign * p["seat_x"]
    xb = sign * x_out(p)
    lo, hi = min(xa, xb), max(xa, xb)
    return (
        cq.Workplane("YZ").polyline(pts).close()
        .extrude(hi - lo).translate((lo, 0, 0))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    out = []
    for i, (x, z) in enumerate(boss_positions(p)):
        # ボスは**足元の板を厚み方向いっぱいまで** claim する（AGENTS.md §4.5）。
        # 下穴（止まり）と同軸に積み上がっているので 1 個にまとめる。
        out.append(feature.cylinder(
            f"pi_boss_{i}", (x, z), p["boss_dia"], p["y0"], _PI.lo[1],
            margin=m, axis="Y", note="Pi の取付ボスと M2.5 下穴（止まり）"))
    for sign in (-1, 1):
        s = "p" if sign > 0 else "n"
        out.append(feature.box(
            f"grip_tab_{s}",
            (sign * (p["tab_x0"] + p["tab_x1"]) / 2, y1(p) + p["tab_h"] / 2),
            (p["tab_x1"] - p["tab_x0"], p["tab_h"]),
            p["tab_z0"], p["tab_z1"], margin=m, note="掴み代のタブ"))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    xo = x_out(p)
    ya, yb = p["y0"], y1(p)

    # --- 板（中央は top_mid まで、縁は z1 まで） ---
    part = cq.Workplane("XY").newObject([cq.Solid.makeBox(
        2 * xo, f.wall(p["plate_t"]), top_mid(p) - p["z0"],
        cq.Vector(-xo, ya, p["z0"]))])
    # 上の隅を落とす。**上の押さえ（x >= 34.5）の下を通れる高さにする**
    for sign in (-1, 1):
        x0 = min(sign * p["top_step_x"], sign * xo)
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeBox(
            xo - p["top_step_x"], f.wall(p["plate_t"]) + 2,
            top_mid(p) - p["z1"] + 1,
            cq.Vector(x0, ya - 1, p["z1"]))]))

    # --- ポカヨケ（-X 側の下隅を 2.5 mm 欠く） ---
    # **これ 1 つで上下・左右・前後の 3 通りの取り違えを全部止める。**
    # -X 側の棚だけ 2.5 mm 高いので、逆向きだと欠けが逆側や上側に来て、
    # 棚に乗り上げて浮くか、上の押さえに当たる。
    if p["key_step"] > 0.01:            # 0 はポカヨケ無しの対照実験（テスト用）
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeBox(
            p["key_w"], f.wall(p["plate_t"]) + 2, key_z0(p) - p["z0"],
            cq.Vector(-xo, ya - 1, p["z0"]))]))

    # --- クリック止めの歯（左右の下縁。棚の切り欠きに落ちる） ---
    for sign in (-1, 1):
        part = part.union(_tooth(sign, p))

    # --- Pi の取付ボス（4.5 mm 立てて、M2.5 の下穴を止まりで彫る） ---
    for x, z in boss_positions(p):
        part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.boss(p["boss_dia"]) / 2, _PI.lo[1] - yb,
            cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(p["boss_pilot"]) / 2, _PI.lo[1] - yb,
            cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))

    # --- 掴み代（手袋をした手で摘める。背面へ立てる） ---
    for sign in (-1, 1):
        x0 = min(sign * p["tab_x0"], sign * p["tab_x1"])
        part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeBox(
            p["tab_x1"] - p["tab_x0"], p["tab_h"], p["tab_z1"] - p["tab_z0"],
            cq.Vector(x0, yb, p["tab_z0"]))]))

    # --- 刻印（原則 5）---
    # **板の前面（= 第 1 層）に彫る。** 背面は Pi がほぼ覆ってしまって場所が無い。
    # トレーを手に持ったときに読める面、という位置づけ。物理的なポカヨケ
    # （張り出し）が主で、これは補助である。
    part = part.cut(
        cq.Workplane("XZ")
        .text("UP", p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((-24.0, ya + p["label_depth"], p["z1"] - 8.0))
    )
    return part
