"""wildlife-cam カメラユニット 背面の蓋（鞍つき）.

`camera_unit.py` の本体に被せる蓋。**造形姿勢が本体と違うので別ファイル**にしてある
（本体は開口を上、蓋は平板として寝かせる）。

## この蓋が持つもの

  1. **パッキン溝**（O リング φ2.0 コード / 周回のレーストラック）。
     溝は**蓋側**に彫る。本体側は平らな land にして、開口を広く取るため。
  2. **鞍**（幹の丸みに座る V 溝）。半角 54 度・幅 44・深さ 16。
     直径 48〜64 mm の幹に対して **2 線接触**になり、径が変わっても座りが安定する。
     円弧だと 1 つの径にしか合わない。
  3. **ベルト溝** 2 本。幅 30 mm（何重にも巻ける）、鞍の面よりさらに 3 mm 深い。
     鞍と同じ V の延長なので干渉しない。巻いたベルトが上下にずれない。
  4. **蝶ねじ 4 本の通し穴**。座ぐりで**脱落しない捕捉式**にする前提
     （E リングか段付きねじ。金具そのものは未設計）。
  5. **ポカヨケ**: ねじ 4 本のうち **1 本だけ M5**（他は M4）。
     180 度回すと M5 のねじが M4 のインサートに入らないので、
     **逆向きでは締まらない。** 穴径の違いは目でも分かる。
  6. **刻印**: 締める順序 1-2-3-4 と UP。現地に説明書は無い。

## 座標

  x は左右中央、z は本体と同じ（0 = 下端、190 = 上端）。
  **y = 0 が本体に当たるシール面、+Y が樹の方向。**

## 造形姿勢

```
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}   シール面を下（ビルドプレート）に
```

  - **シール面が第 1 層**になるので、最も平坦で密な面がパッキンに当たる
  - V 溝とベルト溝は**上向きに開く**のでサポートが要らない
  - パッキン溝は下向きに開くが、幅 2.70 のブリッジなので渡せる

## 未設計

  - 蝶ねじの捕捉金具（E リング / 段付きねじ）。`docs/field-procedure.md` の宿題 1
  - パッキンの座りが見える段差。同 宿題 3
  - 4 点でパッキンの面圧が均等になるかは未検証（蓋のたわみ計算をしていない）
"""

import math

import cadquery as cq

from harness import feature, fit
from designs.wildlife_cam import camera_unit
from parts import oring

DESIGN_NAME = "camera_unit_lid"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    "width": camera_unit.PARAMS["width"],       # 84.0
    "height": camera_unit.PARAMS["height"],     # 190.0
    "plate_t": 3.0,
    "saddle_t": 19.0,            # 鞍の肉厚。V の深さ 16 + ベルト溝の 3
    "saddle_depth": 16.0,        # V の深さ
    "saddle_half_angle_deg": 54.0,
    "belt_extra_depth": 3.0,     # 鞍面よりさらに深く彫る量
    "belt_w": 30.0,              # 何重にも巻ける幅
    "belt_frac": (0.25, 0.75),
    # パッキン溝（本体の land 中央に合わせる）
    "gasket_w": oring.GROOVE_WIDTH,   # 2.70
    "gasket_d": oring.GROOVE_DEPTH,   # 1.50
    # 本体の land は x 37..42。溝はその中に収め、蓋の外縁にも 1.6 以上残す。
    "gasket_x": 39.0,
    "gasket_z_margin": 3.0,      # 上下も同じ理由
    # 蝶ねじ
    "screw_dia": 4.5,
    "screw_head_dia": 9.0,
    # 4 本目だけ M5（ポカヨケ）。本体の lid_big_index に対応する。
    "big_screw_dia": 5.5,
    "big_head_dia": 10.5,
    "screw_head_depth": 3.0,
    "min_wall": 1.6,
    "feature_margin": 0.8,
    "label_size": 6.0,   # size 5 では文字の線幅が min_wall を切る（fit_coupon の実測）
    "label_depth": 0.6,
}

#: シール面を下にして刷る。第 1 層 = 最も平坦な面がパッキンに当たる。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}

COMPONENTS = []

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 1.5,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": PARAMS["screw_dia"], "count": 3,
         "note": "蝶ねじ M4 の通し穴（パッキンの内側なので漏れ経路にならない）"},
        {"diameter_mm": PARAMS["big_screw_dia"], "count": 1,
         "note": "蝶ねじ M5（ポカヨケ。1 本だけ大きい）"},
    ],
}

SECTIONS = [
    {"name": "xy_belt", "origin": (0, 0, 47.5), "normal": (0, 0, -1)},
    {"name": "yz_mid", "origin": (0, 0, 0), "normal": (-1, 0, 0)},
]


def saddle_half_width(depth: float, p=PARAMS) -> float:
    """深さ depth のときの V の開口 半幅."""
    return depth * math.tan(math.radians(p["saddle_half_angle_deg"]))


def trunk_center_height(trunk_dia: float, p=PARAMS) -> float:
    """直径 trunk_dia の幹が V に座ったときの、V の頂点からの中心高さ.

    r / sin(半角)。直径 48〜64 で V の壁の中に接触が収まることの確認に使う。
    """
    return (trunk_dia / 2) / math.sin(math.radians(p["saddle_half_angle_deg"]))


def screw_positions(p=PARAMS):
    return list(camera_unit.PARAMS["lid_bosses"])


def _v_cutter(depth: float, z0: float, z1: float, p=PARAMS):
    """V 溝の切り抜き。頂点は y = saddle_t + plate_t - depth."""
    y_top = p["plate_t"] + p["saddle_t"]
    y_apex = y_top - depth
    half = saddle_half_width(depth, p)
    pts = [(-half, y_top), (half, y_top), (0.0, y_apex)]
    return (
        cq.Workplane("XY")
        .polyline(pts).close()
        .extrude(z1 - z0)
        .translate((0, 0, z0))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    y_top = p["plate_t"] + p["saddle_t"]
    out = [
        feature.box(
            "saddle", (0.0, y_top - p["saddle_depth"] / 2),
            (2 * saddle_half_width(p["saddle_depth"], p), p["saddle_depth"]),
            0.0, p["height"], margin=0.0,
            note="鞍の V 溝（ベルト溝を含む）",
        ),
    ]
    for i, (x, z) in enumerate(screw_positions(p)):
        out.append(feature.cylinder(
            f"screw_{i}", (x, z),
            p["big_head_dia"] if i == camera_unit.PARAMS["lid_big_index"]
            else p["screw_head_dia"], -0.5, y_top + 0.5,
            margin=m, axis="Y", note="蝶ねじの通し穴と座ぐり",
        ))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    y_top = p["plate_t"] + p["saddle_t"]

    plate = cq.Solid.makeBox(
        f.boss(p["width"]), y_top, f.boss(p["height"]),
        cq.Vector(-f.boss(p["width"]) / 2, 0, 0))
    part = cq.Workplane("XY").newObject([plate])

    # 鞍の V 溝（全長）
    part = part.cut(_v_cutter(p["saddle_depth"], -1.0, p["height"] + 1.0, p))

    # ベルト溝（さらに 3 mm 深い V を 2 本）
    for frac in p["belt_frac"]:
        zc = p["height"] * frac
        part = part.cut(_v_cutter(
            p["saddle_depth"] + p["belt_extra_depth"],
            zc - p["belt_w"] / 2, zc + p["belt_w"] / 2, p))

    # パッキン溝（シール面 y=0 に彫る周回のレーストラック）
    gw = f.uncompensated(p["gasket_w"], "溝幅は未実測")
    gd = f.uncompensated(p["gasket_d"], "溝深さは未実測")
    zc = p["height"] / 2
    half_z = p["height"] / 2 - p["gasket_z_margin"]
    outer = cq.Solid.makeBox(
        2 * p["gasket_x"] + gw, gd + 1, 2 * half_z + gw,
        cq.Vector(-(p["gasket_x"] + gw / 2), -1.0, zc - half_z - gw / 2))
    inner = cq.Solid.makeBox(
        2 * p["gasket_x"] - gw, gd + 2, 2 * half_z - gw,
        cq.Vector(-(p["gasket_x"] - gw / 2), -1.5, zc - half_z + gw / 2))
    part = part.cut(cq.Workplane("XY").newObject([outer.cut(inner)]))

    # 蝶ねじの通し穴 + 座ぐり（捕捉式にするための段）
    big_i = camera_unit.PARAMS["lid_big_index"]
    for i, (x, z) in enumerate(screw_positions(p)):
        d = p["big_screw_dia"] if i == big_i else p["screw_dia"]
        hd = p["big_head_dia"] if i == big_i else p["screw_head_dia"]
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(d) / 2, y_top + 2,
            cq.Vector(x, -1.0, z), cq.Vector(0, 1, 0))]))
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(hd) / 2, p["screw_head_depth"] + 1,
            cq.Vector(x, y_top - p["screw_head_depth"], z), cq.Vector(0, 1, 0))]))

    # 刻印（現地 UX 原則 5）。**V 溝とベルト溝を避けた平らな帯**（|x| = 26.2〜42）に彫る。
    # 締める順序を現地で読めるようにする。説明書は現地に無い。
    for i, (x, z) in enumerate(screw_positions(p)):
        dz = 11.0 if z < p["height"] / 2 else -11.0
        part = part.cut(_label(str(i + 1), x, z + dz, p))
    part = part.cut(_label("UP", 33.0, p["height"] - 34.0, p))
    return part


def _label(text, x, z, p):
    """外面 (+Y) に彫る刻印。+Y から読むので左右を反転させる.

    反転を忘れると現地で鏡文字になる。刻んでしまったら直せない。
    """
    y_top = p["plate_t"] + p["saddle_t"]
    return (
        cq.Workplane("XZ")
        .text(text, p["label_size"], p["label_depth"] + 1.0, combine=False)
        .mirror("YZ")
        .translate((x, y_top, z))
    )
