"""wildlife-cam 基板トレー（**CSI レスキューを付けた** Pi Zero 2 W を載せる）.

`camera_unit.py` の本体に、**背面（開口側）から差し込む**トレー。
Pi はもう裸ではない —— **CSI レスキューブラケットを装着した状態**
（`parts/pi_zero_2w_rescue`）を 1 つの部品として相手にする。

## ★ 何が変わったのか（D-021 -> D-023）

実測（2026-08-23）で 2 つのことが分かり、**D-021 の前提が両方とも崩れた。**

```
剛体幅      65.0  ->  76.9   （microSD 4.1 + 基板 65.0 + ブラケット 7.8）
基板の裏     0.4  ->   2.7   （CSI 側の取付穴の真下。ねじ + **ナット**）
使える取付穴   4  ->     2   （CSI 側の 2 穴はブラケットが占有）
```

1. **幅 76.9 は、旧・背面開口 74.0 を通らない。** 本体を 84 -> 88 に広げた（**D-022**）。
2. **裏に 2.7 mm 出ている。** `parts/pi_zero_2w.CAN_SIT_FLAT = True` はもう成り立たない。
   ボスを 3.4 mm 立てて逃がし、**`underside` チェック（13 個目）で毎回実測する。**
3. **共締めはできない。** ねじの裏はナットで塞がっている。
   トレーが使えるのは **microSD 側の 2 穴だけ**。

## Pi の保持（**ねじ 2 本 + ナットポケット 2 個**）

| 向き | 何が受けるか |
|---|---|
| 面内 (x, z, 面内回転) | **microSD 側の M2.5 x 2 本**。2 点で面内は完全に決まる |
| -Y（基板が板へ倒れる） | 4 か所の座面（ねじボス 2 + **ナットポケットのパッド 2**） |
| ±x, ±z の CSI 端 | **ナットポケットの壁**。ナット 2 個が 2.7 mm 落ち込んでいる |
| **+Y（CSI 端が跳ね上がる）** | ナットがポケットを抜けるまで 2.7 mm。**最終的には蓋** |

**残る自由度は 1 つだけ**だった —— 2 本のねじを結ぶ線まわりの回転（CSI 端が
±Y に振れる）。ナットポケットがその回転を 2.7 mm ぶん拘束し、蓋が最後を止める
（D-021 でトレー自身の +Y を蓋が止めているのと同じ考え方）。

**ブラケットのバーを溝で掴む案は採らなかった。** バーの寸法は 1 つも測っていない。
**「測らなくて済む設計にする」**方を優先している（不採用の理由は D-023）。

## トレー自身の保持（本体側は `camera_unit._tray_receiver`）

| 向き | 何が受けるか |
|---|---|
| -Z（自重） | 本体側の**棚**（x ±34.5〜41）。掛かり代 4.35 mm |
| +Z（浮き） | **天井から吊ったフック**（x ±18〜25）。遊び 0.6 mm |
| ±X | **位置決めリップ**（x ±39.25。片側 0.4 mm） |
| -Y | 本体側の**前の当たり** |
| **+Y（抜け）** | **クリック止めの歯** / 蓋（閉めているとき） |

**+Z の押さえを天井から吊っているのが D-023 の要点。** 側壁から内側へ出すと
Pi (|x| <= 38.45) と x を奪い合うが、天井から吊れば x は柱の間 (|x| <= 25) で足りる。

## x の収支（**もう 1 mm も余っていない**）

```
背面の開口   ±39.25   (width 88.0 / wall 3.0 / rim_step 1.75)
トレーの板   ±38.85   開口まで 0.40
Pi + microSD ±38.45   板の縁まで 0.40 / リップ (±39.25) まで 0.80
```

## ポカヨケ（原則 3）— 上下・左右・前後のどれを間違えても座らない

**縁の上端は +X 側 180.8 / -X 側 180.0（段 0.8 mm）**で、本体のフックも同じ段。
どの反転でも「高い側の縁」が「低い側のフック」に当たる。トレーは棚に載っていて
**下へ逃げられない**ので、どの z でも座らない。
（段を棚側に付けられないのは、そこに Pi の下端が来るから。段が 0.8 なのは、
下げた側のフックが「0.6 持ち上げた Pi の上端」に当たらない上限だから。）

## FFC の経路（`FFC_EXIT = "horizontal"`。確定）

FFC はバーの上を通り、**基板上面とほぼ同じ高さで水平に +X へ出る**（x = 38.45）。
そこから前面のカメラ（z=60）へ向かうには 90 度曲げる必要があり、
**曲げ半径 3.0 mm（`pi_zero_2w_rescue.FFC_BEND_R_MIN`）を取ると外側が x 41.75 に
達して、側壁の内面 41.0 を 0.75 mm 超える。**

**実機で確かめること**（`docs/pcb-tray.md` §6）。使える手は 3 つ:

  - 静的曲げなので半径 2.55（厚みの 8.5 倍）で通す。**下限 10 倍を割る**
  - 側壁のその z 帯（12 mm ほど）だけ外へ 1.5 mm 膨らませる（y < 44 のみ。
    リムは 88 のまま = パッキン経路に触らない）
  - 幅を 88 -> 89.5 にする

**トレーの形はどの手を採っても変わらない**ので、ここでは止めていない。

## `SEAL_SPANS` と `CAPTIVE_SCREWS` を宣言しない理由

  - **パッキンを潰す合わせ面が無い。** 防水は本体と蓋の合わせ面が受け持つ。**考え忘れではない**
  - **現地で外すねじが無い。** Pi を留める M2.5 x 2 本は作業台で締めるもので、
    現地でトレーを出し入れするのに工具は要らない

## 未確定事項

  - **`NUT_AF`（ナットの二面幅）は推定 5.0。** ポケットの径がこれで決まる
  - **`RESCUE_Y_POS` は未実測**（推定・中央）。ここでは**使っていない**
    （ポケットの位置は Pi の機構図の値で決まる）ので、再測定が入っても形は変わらない
  - **M2.5 タッピングねじの下穴 φ2.1 は推定**
  - **クリック止めの保持力を計算していない**（歯 0.4 mm x 45 度）
  - **FFC の曲げ半径**（上）
"""

import cadquery as cq

from harness import feature, fit, underside
from harness.component import Component
from designs.wildlife_cam import camera_unit as cu
from parts import pi_zero_2w_rescue as rescue

DESIGN_NAME = "pcb_tray"
FIT_TABLE = fit.ASA_P1S

_U = cu.PARAMS

PARAMS = {
    # --- 本体から導出する（**二重に持たない**） ---
    "z0": _U["tray_z0"],                    # 149.2  棚の天面
    "z1": _U["tray_z1"],                    # 180.8  縁の上端（+X 側）
    "y0": _U["tray_y0"],                    # 23.9
    "key_step": _U["tray_key_step"],        # 0.8
    "seat_x": _U["tray_seat_x"],            # 34.5
    "gap": _U["tray_gap"],                  # 0.4
    "detent_y0": _U["detent_y0"],
    "detent_w": _U["detent_w"],
    "detent_h": _U["detent_h"],
    # --- トレー自身 ---
    "plate_t": 2.5,              # 設計値。板厚
    "detent_clear": 0.15,        # 歯と切り欠きの隙間（片側）
    #: **Pi の座面の高さ。** 基板下面より下に出ているナット（2.7 mm 実測）を
    #: 逃がすために立てる。`underside` チェックがこの数字ではなく**形から**実測する。
    "boss_h": cu.PI_BOSS_H,      # 3.4 = 2.7 + 0.7
    "boss_dia": 5.4,             # 設計値。下穴 2.1 の周りに 1.65 の肉が残る
    "boss_pilot": 2.1,           # 推定（M2.5 タッピングの下穴。未実測）
    #: ナットポケット。**丸穴**にしてある（六角に合わせても回り止めにはならない。
    #: 面内回転は microSD 側の 2 本で既に決まっている）。
    #: 径は二面幅 5.0 -> 対角 5.77 に逃げ 0.4 を足したもの。
    "nut_bore": 6.6,             # 計算値: 5.0 * 2/sqrt(3) + 0.4 x 2（NUT_AF は推定）
    "nut_pad_dia": 9.8,          # 計算値: 6.6 + 1.6 x 2（min_wall を残す）
    # 掴み代（**背面から引き出すための取っ手**）
    #: 板の上端から立てるフィン。**柱の間（|x| <= 25）ではなく、さらに内側の
    #: 「本体のフック (|x| 18〜25) にも当たらない」帯**に置く。
    "grip_x": 15.0,              # フィンの半幅
    "grip_z1": 190.0,            # フィンの上端
    "grip_lip_z0": 186.0,        # 指を掛けるリップの z 下端
    "grip_lip_h": 8.0,           # リップが +Y へ出る量
    "min_wall": 1.6,
    "feature_margin": 0.8,
    #: size 6 では "U" と "P" の間に残る肉が 1.11 mm しかなく `wall` が落ちる。
    "label_size": 10.0,
    "label_depth": 0.6,
}

#: 板を寝かせ、ボスとパッドと取っ手を上に立てる。板の前面が第 1 層。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}
#: 差し込み方向。原則から外している根拠は camera_unit.SLIDE_AXIS_NOTE。
SLIDE_AXIS = cu.SLIDE_AXIS

_PI = cu.PI_BOX


def x_out(p=PARAMS) -> float:
    """トレーの左右の端。**本体の位置決めリップから導出する**（二重に持たない）."""
    return cu.tray_x_out(cu.PARAMS)


def y1(p=PARAMS) -> float:
    return p["y0"] + p["plate_t"]


def edge_top(p=PARAMS, sign=1) -> float:
    """縁の上端。**-X 側だけ key_step ぶん低い**（ポカヨケ）.

    既定値は本体から導出しているが、**ネガティブテストが上書きできるように**
    自分の PARAMS を経由させてある（ポカヨケの根拠の裏取りに使う）。
    """
    return p["z1"] - (p["key_step"] if sign < 0 else 0.0)


def board_y(p=PARAMS) -> float:
    """基板の下面 y。**座面（ボス / パッドの天面）と同じ。**"""
    return y1(p) + p["boss_h"]


def screw_positions(p=PARAMS):
    """トレーが使える取付穴 (x, z)。**microSD 側の 2 つだけ**（CSI 側は占有済み）."""
    cz = _PI.center[2]
    return [(cu.PI_BOARD_CX + hx, cz + hy) for hx, hy in rescue.free_hole_positions()]


def nut_pad_positions(p=PARAMS):
    """基板の裏のナット 2 個の中心 (x, z)。**ポケットを彫る場所。**"""
    cz = _PI.center[2]
    return [(cu.PI_BOARD_CX + hx, cz + hy) for hx, hy in rescue.nut_positions()]


def _board_solid(clearance: float = 0.0):
    """基板から**上**の塊（基板下面 -> GPIO ヘッダの先）+ clearance.

    **座面（-Y 側）にはクリアランスを足さない。** 基板の下面はボスとパッドの
    天面に**接するのが正しい**ので、ここを太らせると正しい設計が
    clearance FAIL になる（`docs/AGENTS.md` §4）。

    **そしてこの免除こそが、基板の下に出ているナットを見逃す穴である。**
    座面側の隙間はもともと 0 が正しいことになっているので、そこに 2.7 mm の
    ナットがあっても `clearance` は「意図した接触」としか読まない。
    だから `UNDER_BOARD`（13 個目のチェック）を別に宣言している。
    """
    c = clearance
    sx, _sy, sz = _PI.size
    cx, _cy, cz = _PI.center
    y0 = board_y()                        # 座面。**ここだけ太らせない**
    y1_ = _PI.center[1] + _PI.size[1] / 2
    return cq.Solid.makeBox(
        sx + 2 * c, y1_ - y0 + c, sz + 2 * c,
        cq.Vector(cx - sx / 2 - c, y0, cz - sz / 2 - c))


def nut_dia() -> float:
    """六角ナットの外接円（= 対角の寸法）。**二面幅から出す**（NUT_AF は推定）."""
    return rescue.NUT_AF * 2 / 3 ** 0.5      # 5.0 -> 5.77


def _nut_solid(x: float, z: float, clearance: float = 0.0):
    """基板の**下**に出ているナット 1 個。

    **角柱ではなく円柱で包む。** 角柱（対角を 1 辺とする正方形）にすると、
    角が丸いポケットの外へはみ出して「実体が干渉」になる。
    """
    c = clearance
    r = nut_dia() / 2 + c
    y0 = board_y() - rescue.RESCUE_BOT_H - c
    return cq.Solid.makeCylinder(
        r, rescue.RESCUE_BOT_H + 2 * c, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))


#: **基板から上とナットを別々の部品にしてある。**
#: 1 個の直方体で包むと、ナットの高さぶん（2.7 mm）が基板の footprint 全体に
#: 広がってしまい、**ボスとパッドが「部品にめり込んでいる」ことになる。**
#: ナットが出ているのは取付穴の真下の 2 か所だけなので、そこだけを別に持つ。
COMPONENTS = [
    Component(
        name="pi_rescue", shape=_board_solid(0.0), envelope_fn=_board_solid,
        notes=("Pi Zero 2 W + CSI レスキュー + microSD。剛体幅 76.9。"
               "下面はボス / パッドの天面に載る（意図した接触なのでクリアランス 0）"),
        dimension_source=rescue.DIM_SOURCE,
    ),
] + [
    Component(
        name=f"rescue_nut_{i}",
        shape=_nut_solid(x, z, 0.0),
        envelope_fn=lambda c, _x=x, _z=z: _nut_solid(_x, _z, c),
        notes="CSI レスキューのねじ + ナット。ポケットに 2.7 mm 落ちる",
        dimension_source=rescue.DIM_SOURCE,
    )
    # **位置は nut_pad_positions() から出す。** build() / features() /
    # UNDER_BOARD と同じ関数を通さないと、いずれ宣言と実物がずれる。
    for i, (x, z) in enumerate(nut_pad_positions())
]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 1.0,
    "openings_match_tol_mm": 0.1,
    #: **貫通はゼロ。** 下穴 2 個もナットポケット 2 個も止まり穴で、板の裏へ抜けない。
    "expected_openings": [],
}

SECTIONS = [
    {"name": "yz_nut", "origin": (cu.PI_BOARD_CX + 29.0, 0, 0), "normal": (-1, 0, 0)},
    {"name": "xy_detent", "origin": (0, 0, 148.5), "normal": (0, 0, -1)},
]


def UNDER_BOARD(p=PARAMS):
    """**基板の下に出ているもの**の申告（13 個目のチェック `underside`）.

    `clearance` は座面のクリアランスを 0 にしてよいことになっているので、
    **基板の下にぶら下がっているものを丸ごと見逃す。** ここで別に見張る。
    """
    by = board_y(p)
    d = nut_dia()
    out = [
        underside.UnderBoard(
            name=f"rescue_nut_{i}", board=by, protrusion_mm=rescue.RESCUE_BOT_H,
            at=(x, z), size=(d, d), shape="circle", axis="Y", sign=1, clearance_mm=0.4,
            note="CSI レスキューのねじ + ナット（基板下面から 2.7 mm。実測 2026-08-23）")
        for i, (x, z) in enumerate(nut_pad_positions(p))
    ]
    # 基板そのものの裏の実装部品。**ボスもパッドも無い中央**で見る。
    out.append(underside.UnderBoard(
        name="pi_bot_comp", board=by, protrusion_mm=rescue.BOT_COMP_H,
        at=(cu.PI_BOARD_CX, _PI.center[2]), size=(30.0, 16.0),
        axis="Y", sign=1, clearance_mm=0.4,
        note="Pi の裏の実装部品 0.4 mm（実測 2026-08-22）"))
    return out


def _tooth(sign, p=PARAMS):
    """クリック止めの歯。**本体側の切り欠きと同じ台形を、片側 detent_clear だけ
    小さくしたもの。**

    三角の歯にすると、切り欠きの平らな床（幅 detent_w - 2 * detent_h）の上を
    歯が自由に滑ってしまい、**抜け止めとして働かない**（歯が床の縁に当たるまでに
    0.4 mm 動けた）。台形どうしで噛ませれば、遊びは detent_clear だけになる。
    """
    z_top = cu.tray_shelf_top(cu.PARAMS)
    h = p["detent_h"]
    c = p["detent_clear"]
    ht = h - c                                   # 歯の深さ
    f0 = p["detent_y0"] + h + c                  # 歯の床（切り欠きの床より c だけ内側）
    f1 = p["detent_y0"] + p["detent_w"] - h - c
    top = z_top + 0.2
    pts = [(f0 - ht - 0.2, top), (f0, z_top - ht), (f1, z_top - ht), (f1 + ht + 0.2, top)]
    xa, xb = sign * p["seat_x"], sign * x_out(p)
    lo, hi = min(xa, xb), max(xa, xb)
    return (
        cq.Workplane("YZ").polyline(pts).close()
        .extrude(hi - lo).translate((lo, 0, 0))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    out = []
    for i, (x, z) in enumerate(screw_positions(p)):
        # ボスは**足元の板を厚み方向いっぱいまで** claim する（AGENTS.md §4.5）。
        out.append(feature.cylinder(
            f"pi_boss_{i}", (x, z), p["boss_dia"], p["y0"], board_y(p),
            margin=m, axis="Y", note="Pi の取付ボスと M2.5 下穴（止まり）"))
    for i, (x, z) in enumerate(nut_pad_positions(p)):
        out.append(feature.cylinder(
            f"nut_pad_{i}", (x, z), p["nut_pad_dia"], p["y0"], board_y(p),
            margin=m, axis="Y", note="ナットポケットのパッドとポケット（止まり）"))
    out.append(feature.box(
        "grip", (0.0, (y1(p) + y1(p) + p["grip_lip_h"]) / 2),
        (2 * p["grip_x"], p["grip_lip_h"]),
        p["z1"], p["grip_z1"], margin=m, note="背面から引き出す取っ手"))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    xo = x_out(p)
    ya, yb = p["y0"], y1(p)
    t = f.wall(p["plate_t"])

    # --- 板（+X 側は z1 まで、-X 側は key_step ぶん低い） ---
    part = None
    for sign in (-1, 1):
        x0 = min(0.0, sign * xo)
        part2 = cq.Solid.makeBox(
            xo, t, edge_top(p, sign) - p["z0"], cq.Vector(x0, ya, p["z0"]))
        part = part2 if part is None else part.fuse(part2)
    part = cq.Workplane("XY").newObject([part.clean()])

    # --- クリック止めの歯（左右の下縁。棚の切り欠きに落ちる） ---
    for sign in (-1, 1):
        part = part.union(_tooth(sign, p))

    # --- Pi の取付ボス（microSD 側の 2 本。M2.5 の下穴を止まりで彫る） ---
    h = board_y(p) - yb
    for x, z in screw_positions(p):
        part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.boss(p["boss_dia"]) / 2, h, cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(p["boss_pilot"]) / 2, h, cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))

    # --- ナットポケット（CSI 側の 2 か所。**基板の裏のナットが 2.7 mm 落ちる**） ---
    # パッドの天面は座面と同じ高さで基板を受け、ポケットの壁が CSI 端を位置決めする。
    # **ポケットの床は板の上面**（= 深さ boss_h）。板の裏には抜かない。
    for x, z in nut_pad_positions(p):
        part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.boss(p["nut_pad_dia"]) / 2, h, cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(p["nut_bore"]) / 2, h, cq.Vector(x, yb, z), cq.Vector(0, 1, 0))]))

    # --- 取っ手（背面から引き出す。**本体のフック |x| 18〜25 の内側に立てる**） ---
    gx = p["grip_x"]
    part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeBox(
        2 * gx, t, p["grip_z1"] - p["z1"], cq.Vector(-gx, ya, p["z1"]))]))
    part = part.union(cq.Workplane("XY").newObject([cq.Solid.makeBox(
        2 * gx, p["grip_lip_h"], p["grip_z1"] - p["grip_lip_z0"],
        cq.Vector(-gx, yb, p["grip_lip_z0"]))]))

    # --- 刻印（原則 5）。板の前面（= 第 1 層）に彫る ---
    part = part.cut(
        cq.Workplane("XZ")
        .text("UP", p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((-24.0, ya + p["label_depth"], p["z1"] - 10.0))
    )
    return part
