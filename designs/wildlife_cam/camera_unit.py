"""wildlife-cam カメラユニット 本体（案D の実設計）.

レイアウト検討（`docs/layout-study.md` 案D）を実設計に起こしたもの。
**背面の蓋は別ファイル** `camera_unit_lid.py`（造形姿勢が違うため一体にできない）。

## 座標

  原点は箱の**前面外側・下端・左右中央**。
  **+Y が背面（樹）方向、+Z が上、x は中央から左右。**
  カメラとドームは前面 (-Y 側) に張り出す。

## 造形姿勢と高さの上限について（**重要な確認**）

```
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}   背面の開口を上に向けて刷る
```

この姿勢だと **造形時の Z は箱の「奥行き」= 47 mm** になる。設計上の高さ 198 mm は
造形時には **XY 平面に寝る**ので、効く上限はベッドの 256 mm の方である。
案D の 229 mm も同じで、**229 は造形 Z ではない**（`layout_study_d` を
`harness check` に掛けると造形姿勢適用後の Z は 31.7 mm と出る）。

それでも高さは減らした。**229 -> 198 mm。** 理由は造形ではなく取り付け:

  - 受風面積が減る（84 x 229 = 192 cm2 -> 84 x 198 = 166 cm2、-13%）
  - 材料と質量が減る
  - 余裕は安全のためにある（指示のとおり）

閉じた箱は天井ができて刷れないので、本体は開口を上、蓋は平板として別に刷る。
この姿勢なら**サポート不要**（`overhang` が実測する）。

## 幅を 77 -> 84 mm に増やしたことと、その代償

**ドーム蓋の口径 76.0 mm が幅を決めた。** 案D の 77 mm には嵌合リブ（外径 79.4）が
入らない。84 mm にすると

| | 案D 検討時 | 本設計 | 差 |
|---|---|---|---|
| 幅 | 77.0 mm | **84.0 mm** | +7.0 |
| 幹（直径 48）からの張り出し 片側 | 14.5 mm | **18.0 mm** | **+3.5（+24%）** |
| 受風面積 | 176 cm2 | 166 cm2 | -6%（高さを減らしたぶん） |

**張り出しは増えたが、受風面積は高さを減らしたぶん差し引きで減っている。**
これ以上幅を詰めるにはドームを別の既製品に変えるしかない。

## 優先順位（指示のとおり）

  1. 高さを超えない -> 198 mm（上限 229 に対し 31 mm の余裕）
  2. 張り出しを増やさない -> +3.5 mm。ドームの口径で決まっており、これが下限
  3. 体積 -> 84 x 47 x 198 = 782 cm3（蓋とドームを除く）

## 密閉の考え方

貫通は **4 つ**（PIR / カメラの FPC ポート / ケーブルグランド / 通気ベント）。
**通気機能つきグランドが手に入れば 3 つに減る**（`docs/enclosure-body.md`）。

カメラ本体はドームの中（箱の外）にあるので、この箱の中には入らない。
FPC だけが φ8 のポートを通り、シーラントで封止する。

## パッキンの面圧（`seal` チェックを宣言しない理由）

本体側は平らな land を出すだけで、**溝もたわむ板も蓋の側にある**ので、
`SEAL_SPANS` は `camera_unit_lid.py` が宣言している（`docs/AGENTS.md` §6）。
本体のリムは合わせ面の荷重を**面内**で受ける深い壁なので、蓋よりはるかに硬く、
梁モデルでは剛体として扱っている。**考え忘れではない。**

ただし本体は **land を痩せさせない**責任を負う。合わせ面の幅が足りないと
蓋の溝が段差の縁に跨がる（2026-08-23 に実際に起きた。`docs/lid-fastening.md` §8.1）。
`tests/test_camera_unit.py::test_body_land_carries_the_whole_gasket_groove` が見ている。

## 捕捉式ねじ（`CAPTIVE_SCREWS` を宣言しない理由）

`SEAL_SPANS` と同じで、**ポケットも通し穴も蓋の側にある**ので宣言は
`camera_unit_lid.py` が持っている（`docs/AGENTS.md` §4.9 原則 1）。
**考え忘れではない。**

ただし本体は **下穴をインサートより深く彫る**責任を負う。同じ深さだと
M4 x 30 の先端が底を突き、**締めたつもりで面圧が出ない**（`lid_pilot_depth`）。

## まだ設計していないもの

  - Pi と Onyx を載せるトレー（スライドレールの受け側だけ本体に作ってある）。
    **レールの区間 z 128〜194 には蓋の柱が 2 対（z=142 と 186）通っている。**
    トレーはそこを避けた形にするか、レールを短くすること
  - リブの本数と位置は**たわみ計算をしていない**。2 本の縦リブは目安
    （**蓋のたわみは `seal` チェックで数値化した。前壁のリブはまだ**）
"""

import math

import cadquery as cq

from harness import feature, fit, fov
from designs.wildlife_cam._layout_common import Box, onyx_assembly, route_solid
from harness.component import Component
from parts import cable_gland, dome_lid, gore_vent, hcsr501, otg_cable

DESIGN_NAME = "camera_unit"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    # --- 外形 ---
    "width": 84.0,               # ドーム嵌合リブ 外径 79.4 + 肉 2.3 x 2
    "height": 198.0,             # 案D の 229 から 31 mm 減らした
    "wall": 3.0,
    "cavity_depth": 41.0,        # 前壁の内面から背面の合わせ面まで
    "rim_step": 2.0,             # 背面の合わせ面を内側へ張り出す量
    "rim_t": 3.0,                # 合わせ面のフランジ厚
    "min_wall": 1.6,
    "feature_margin": 0.8,
    # --- 前面: PIR ---
    "pir_z": 136.0,
    "pir_hole_dia": 26.0,        # pir_bezel のスピゴット φ29.0 ではなくドーム逃げ
    "pir_pcd": 44.0,
    "pir_screw_dia": 3.0,        # M3 ヒートセット下穴（暫定。fit_coupon で確定）
    "pir_boss_dia": 7.4,
    "pir_boss_depth": 6.0,
    # --- 前面: カメラポッド（window_snoot.py が載る） ---
    "pod_z": 60.0,
    "pod_pcd": 50.0,
    "pod_screw_dia": 4.2,        # M4 ヒートセット下穴（暫定）
    "pod_boss_dia": 8.6,
    "pod_boss_depth": 8.0,
    "pod_angles_deg": (90.0, 200.0, 320.0),   # 非等分でポカヨケ
    "fpc_port_dia": 8.0,
    # --- 底面 ---
    "gland_dia": cable_gland.PANEL_HOLE,      # PG7: φ12.6
    "gland_x": -22.0,
    "vent_dia": gore_vent.PANEL_HOLE,         # M12: φ12.3
    "vent_x": 22.0,
    "bottom_feature_y": 22.0,
    # --- 蓋の締結（内部の柱にヒートセット） ---
    "lid_screw_dia": 5.0,        # M4 ヒートセット下穴（暫定）
    "lid_boss_dia": 8.2,
    "lid_boss_depth": 8.0,       # ヒートセットインサートの有効深さ
    # **下穴はインサートより深く彫る。** M4 x 30 の蝶ねじはインサートを 8 mm 噛んで
    # 先端が下穴の底に届く。ぴったりだと**先端が底を突いて締めたつもりで面圧が出ない**
    # ので、4 mm ぶん逃がしてある。`captive` チェックがこの噛み合いを毎回解く。
    "lid_pilot_depth": 12.0,     # 設計値（インサート 8.0 + 先端の逃げ 4.0）
    # **6 点（3 対）**。四隅 4 点では長辺中央でパッキンが浮くと `seal` チェックが
    # 出した（圧縮率 13.3% < 下限 15%）。中央に 1 対足して 21% に戻してある。
    # 根拠と比較した案は docs/lid-fastening.md と D-019。
    # 柱は前壁から背面 land まで通す（浮かないし、箱のねじれにも効く）。
    # x=±31 はパッキン溝（37.65〜40.35）から座ぐりを 2 mm 以上離すため。
    # **中央の対が z=142 なのは、左 (x=-31) で内蔵部品が空けている唯一の窓だから。**
    # Onyx が z 21〜136 を、Pi が z 148〜178 を塞いでいる（clearance が実測する）。
    # 真ん中 (z=99) に置ければ 24.4% になるが Onyx が居る。**2026-08-23 に
    # 「Onyx は動かさない」と人間が決定した**ので z=142 で確定（D-019）。
    # **並び順 = 現地で締める順序**（蓋の刻印 1..6）。中央 -> 対角 -> 対角。
    "lid_bosses": ((-31.0, 142.0), (31.0, 142.0), (-31.0, 12.0),
                   (31.0, 186.0), (31.0, 12.0), (-30.0, 186.0)),
    # **ポカヨケ**: 1 本だけ M5、かつ x を 1 mm ずらしてある。180 度回すと
    # M5 のねじが M4 のインサートに入らず、穴位置も合わない。
    # 中央の対が上下非対称（z=142 だけ）なので、**上下逆では穴自体が合わない。**
    "lid_big_index": 5,
    "lid_big_screw_dia": 6.2,
    "lid_big_boss_dia": 9.4,

    # --- 内部: スライドレール（トレーの受け） ---
    "rail_base_w": 12.0,         # fit_coupon v2 と同じ公称
    "rail_top_w": 8.0,
    "rail_depth": 2.0,
    "rail_gap": 0.3,             # 暫定。fit_coupon v2 の実測で確定させる
    "rail_z0": 128.0,
    "rail_z1": 194.0,
    "rail_y": 34.0,
    "detent_dia": 2.0,           # 抜け止めのクリック（最小限）
    # --- リブ ---
    "rib_x": 33.0,
    "rib_w": 2.4,
    "rib_h": 5.0,
    # --- 刻印 ---
    "label_size": 6.0,
    "label_depth": 0.6,
}

#: 背面の開口を上にして刷る。造形 Z = 箱の奥行き 47 mm。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}
#: スライドレールの摺動方向。造形時に水平に寝るので、積層の段差が摺動方向と
#: **平行**に走る（段差を横切らない）。docs/AGENTS.md §4.9.3。
SLIDE_AXIS = (0.0, 0.0, 1.0)

W = PARAMS["width"]
H = PARAMS["height"]
WALL = PARAMS["wall"]
Y_CAVITY_0 = WALL
Y_CAVITY_1 = WALL + PARAMS["cavity_depth"]          # 44.0
Y_BACK = Y_CAVITY_1 + PARAMS["rim_t"]               # 47.0

# --- 内蔵部品の配置 ---------------------------------------------------------
#: 剛体ブロック 115 mm の USB-A 側の端。ここから -Z へ 115 伸びる（z 6..121）。
ONYX_AT = (-18.1, 34.4, 136.0)
PI_BOX = Box(name="pi", center=(0.0, 36.0, 163.0), size=(65.0, 10.2, 30.0),
             note="横向き。コネクタ辺は下 (z=148) を向く")
MICRO_BOX = Box(name="otg_micro", center=(14.3, 34.2, 132.6),
                size=(9.9, 6.8, 30.8), note="データ口（左角から 46.8）から -Z に 30.8")
FLEX_POINTS = [
    (14.3, 34.2, 117.2), (14.3, 34.3, 128.0), (4.0, 34.4, 141.0),
    (-18.1, 34.4, 141.0),
]
FLEX_R = otg_cable.CABLE_DIA / 2 + 2.0


def _onyx_boxes():
    return onyx_assembly(ONYX_AT, "-Z", "X")


COMPONENTS = [
    hcsr501.place(at=(0.0, 12.4, PARAMS["pir_z"]), rotate=(90, 0, 0)),
] + [
    Component(name=b.name, shape=b.solid(0.0),
              envelope_fn=lambda c, _b=b: _b.solid(c),
              notes=b.note, dimension_source="camera-unit")
    for b in _onyx_boxes() + [PI_BOX, MICRO_BOX]
] + [
    Component(name="otg_flex", shape=route_solid(FLEX_POINTS, FLEX_R),
              envelope_fn=lambda c: route_solid(FLEX_POINTS, FLEX_R),
              notes="OTG ケーブル柔軟部", dimension_source="camera-unit"),
]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.5,
    "voxel_pitch_mm": 1.5,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": PARAMS["pir_hole_dia"], "count": 1,
         "note": "PIR 貫通口（pir_bezel のキャリアがラジアルシールで塞ぐ）"},
        {"diameter_mm": PARAMS["fpc_port_dia"], "count": 1,
         "note": "カメラ FPC ポート（シーラントで封止）"},
        {"diameter_mm": PARAMS["gland_dia"], "count": 1,
         "note": "ケーブルグランド PG7（電源）"},
        {"diameter_mm": PARAMS["vent_dia"], "count": 1,
         "note": "防水通気ベント M12"},
    ],
    "layout_allow_contact": [
        ["part_pi", "part_otg_micro"],
        ["part_otg_micro", "otg_flex"],
        ["part_onyx_assembly", "otg_flex"],
    ],
}

#: カメラは箱の外（ドームの中）にある。ポッド (window_snoot) を載せたときの
#: レンズ位置を頂点にした視野円錐を宣言し、**本体が視野を遮らないこと**を確かめる。
#: ポッド側の 16 mm 条件は window_snoot.py の fov が別途見ている。
VIEW_CONES = [
    fov.Cone(
        name="camera",
        apex=(0.0, -26.6, PARAMS["pod_z"]),
        axis=(0.0, -1.0, 0.0),
        half_angle_deg=37.98,
        length=150.0,
        start=0.5,
        note="ポッドのレンズ前面 (y=-26.6) を頂点とする対角半角 37.98 度の円錐",
    )
]

SECTIONS = [
    {"name": "xy_pod", "origin": (0, 0, PARAMS["pod_z"]), "normal": (0, 0, -1)},
    {"name": "yz_mid", "origin": (0, 0, 0), "normal": (-1, 0, 0)},
]


def pod_positions(p=PARAMS):
    r = p["pod_pcd"] / 2
    return [(r * math.cos(math.radians(a)), p["pod_z"] + r * math.sin(math.radians(a)))
            for a in p["pod_angles_deg"]]


def pir_positions(p=PARAMS):
    r = p["pir_pcd"] / 2
    return [(r * math.cos(math.radians(a)), p["pir_z"] + r * math.sin(math.radians(a)))
            for a in (45.0, 135.0, 225.0, 315.0)]


def lens_to_dome_window_mm(p=PARAMS) -> float:
    """ポッドを載せたときのレンズ - ドーム平窓の距離。16.0 以内であること."""
    from designs.wildlife_cam import window_snoot

    return window_snoot.LENS_TO_WINDOW


def overhang_from_trunk_mm(p=PARAMS, trunk_dia: float = 48.0) -> float:
    return (p["width"] - trunk_dia) / 2


# --- 形状 ------------------------------------------------------------------


def _shell(p, f):
    outer = cq.Solid.makeBox(p["width"], Y_BACK, p["height"],
                             cq.Vector(-p["width"] / 2, 0, 0))
    cav = cq.Solid.makeBox(
        p["width"] - 2 * WALL, p["cavity_depth"] + p["rim_t"] + 1,
        p["height"] - 2 * WALL,
        cq.Vector(-(p["width"] / 2 - WALL), Y_CAVITY_0, WALL),
    )
    shape = outer.cut(cav)
    # 背面の合わせ面: 内側へ rim_step 張り出して land を作る（O リング溝は蓋側）
    # **厚みは Y_BACK まで（rim_t ちょうど）。** 切り抜き用の「+1」をここに書くと
    # land だけが背面より 1 mm 飛び出し、**合わせ面の幅が 5 mm から 2 mm に痩せて
    # 蓋のパッキン溝が段差の縁に跨がる。** 2026-08-23 に実際にそうなっていた。
    step = p["rim_step"]
    land = cq.Solid.makeBox(
        p["width"] - 2 * WALL, p["rim_t"], p["height"] - 2 * WALL,
        cq.Vector(-(p["width"] / 2 - WALL), Y_CAVITY_1, WALL),
    ).cut(cq.Solid.makeBox(
        p["width"] - 2 * WALL - 2 * step, p["rim_t"] + 2,
        p["height"] - 2 * WALL - 2 * step,
        cq.Vector(-(p["width"] / 2 - WALL - step), Y_CAVITY_1 - 0.5, WALL + step),
    ))
    return cq.Workplane("XY").newObject([shape.fuse(land).clean()])


def _boss(f, x, z, dia, depth, pilot):
    """前壁の内面に立てる止まりボス（ヒートセット用）."""
    body = cq.Solid.makeCylinder(
        f.boss(dia) / 2, depth, cq.Vector(x, Y_CAVITY_0, z), cq.Vector(0, 1, 0))
    hole = cq.Solid.makeCylinder(
        f.hole(pilot) / 2, depth + 1, cq.Vector(x, Y_CAVITY_0 - 0.5, z),
        cq.Vector(0, 1, 0))
    return cq.Workplane("XY").newObject([body.cut(hole)])


def _post(f, x, z, dia, pilot_depth, pilot, min_wall):
    """前壁から背面の合わせ面まで通す、蓋を留める柱.

    前壁まで通すのは (1) 柱が浮かないため (2) 箱のねじれ剛性に効くため。
    下穴は **止まり**（前側に min_wall を残す）。貫通させると漏水経路が増える。
    """
    y0 = Y_CAVITY_0
    body = cq.Solid.makeCylinder(
        f.boss(dia) / 2, Y_CAVITY_1 - y0, cq.Vector(x, y0, z), cq.Vector(0, 1, 0))
    hole = cq.Solid.makeCylinder(
        f.hole(pilot) / 2, pilot_depth + 1,
        cq.Vector(x, Y_CAVITY_1 - pilot_depth, z), cq.Vector(0, 1, 0))
    return cq.Workplane("XY").newObject([body.cut(hole)])


def _rail(p, f, sign):
    """側壁のアリ溝レール（受け）。摺動方向は Z = 造形時に水平."""
    x_wall = sign * (p["width"] / 2 - WALL)
    base = f.wall(p["rail_base_w"]) + p["rail_gap"]
    top = f.wall(p["rail_top_w"]) + p["rail_gap"]
    d = p["rail_depth"]
    y0 = p["rail_y"] - base / 2
    pts = [
        (y0, x_wall), (y0 + base, x_wall),
        (y0 + (base - top) / 2 + top, x_wall - sign * d),
        (y0 + (base - top) / 2, x_wall - sign * d),
    ]
    prof = cq.Workplane("YX").polyline(pts).close()
    solid = prof.extrude(p["rail_z1"] - p["rail_z0"])
    return solid.translate((0, 0, p["rail_z0"]))


def _label(text, x, z, p, face_y=0.0):
    """底面や側面に彫る刻印（現地 UX 原則 5）."""
    return (
        cq.Workplane("XZ")
        .text(text, p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((x, face_y + p["label_depth"], z))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    out = [
        feature.cylinder("pir_hole", (0.0, p["pir_z"]), p["pir_hole_dia"],
                         -1.0, Y_CAVITY_0 + 1.0, margin=m, axis="Y",
                         note="PIR 貫通口"),
        feature.cylinder("fpc_port", (0.0, p["pod_z"]), p["fpc_port_dia"],
                         -1.0, Y_CAVITY_0 + 1.0, margin=m, axis="Y",
                         note="カメラ FPC ポート"),
        feature.cylinder("gland", (p["gland_x"], p["bottom_feature_y"]),
                         p["gland_dia"], -1.0, WALL + 1.0, margin=m, axis="Z",
                         note="ケーブルグランド PG7"),
        feature.cylinder("vent", (p["vent_x"], p["bottom_feature_y"]),
                         p["vent_dia"], -1.0, WALL + 1.0, margin=m, axis="Z",
                         note="通気ベント M12"),
    ]
    for i, (x, z) in enumerate(pod_positions(p)):
        out.append(feature.cylinder(
            f"pod_boss_{i}", (x, z), p["pod_boss_dia"],
            -0.5, Y_CAVITY_0 + p["pod_boss_depth"], margin=m, axis="Y",
            note="カメラポッド用 M4 ヒートセット（止まり）"))
    for i, (x, z) in enumerate(pir_positions(p)):
        out.append(feature.cylinder(
            f"pir_boss_{i}", (x, z), p["pir_boss_dia"],
            -0.5, Y_CAVITY_0 + p["pir_boss_depth"], margin=m, axis="Y",
            note="PIR キャリア用 M3 ヒートセット（止まり）"))
    for i, (x, z) in enumerate(p["lid_bosses"]):
        out.append(feature.cylinder(
            f"lid_post_{i}", (x, z),
            p["lid_big_boss_dia"] if i == p["lid_big_index"] else p["lid_boss_dia"],
            Y_CAVITY_0 - 0.5, Y_CAVITY_1 + 0.5,
            margin=m, axis="Y", note="蓋の締結柱（M4 ヒートセット）"))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    part = _shell(p, f)

    # --- 前面: PIR 貫通口とキャリアのボス ---
    part = part.cut(
        cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(p["pir_hole_dia"]) / 2, WALL + 2,
            cq.Vector(0, -1, p["pir_z"]), cq.Vector(0, 1, 0))]))
    for x, z in pir_positions(p):
        part = part.union(_boss(f, x, z, p["pir_boss_dia"], p["pir_boss_depth"],
                                p["pir_screw_dia"]))

    # --- 前面: カメラポッドのボスと FPC ポート ---
    for x, z in pod_positions(p):
        part = part.union(_boss(f, x, z, p["pod_boss_dia"], p["pod_boss_depth"],
                                p["pod_screw_dia"]))
    part = part.cut(
        cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(p["fpc_port_dia"]) / 2, WALL + 2,
            cq.Vector(0, -1, p["pod_z"]), cq.Vector(0, 1, 0))]))

    # --- 底面: グランドとベント ---
    for x, dia in ((p["gland_x"], p["gland_dia"]), (p["vent_x"], p["vent_dia"])):
        part = part.cut(
            cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
                f.hole(dia) / 2, WALL + 2,
                cq.Vector(x, p["bottom_feature_y"], -1), cq.Vector(0, 0, 1))]))

    # --- 蓋の締結柱 ---
    for i, (x, z) in enumerate(p["lid_bosses"]):
        big = i == p["lid_big_index"]
        part = part.union(_post(
            f, x, z,
            p["lid_big_boss_dia"] if big else p["lid_boss_dia"],
            p["lid_pilot_depth"],
            p["lid_big_screw_dia"] if big else p["lid_screw_dia"],
            p["min_wall"]))

    # --- 内部: スライドレール（受け） ---
    for sign in (-1, 1):
        part = part.union(_rail(p, f, sign))

    # --- リブ（大きな前面のたわみ止め） ---
    for sign in (-1, 1):
        part = part.union(
            cq.Workplane("XY")
            .box(f.wall(p["rib_w"]), p["rib_h"], p["height"] - 2 * WALL - 2,
                 centered=(True, False, False))
            .translate((sign * p["rib_x"], Y_CAVITY_0, WALL + 1))
        )

    # --- 刻印（現地 UX 原則 5: 現地に説明書は無い） ---
    part = part.cut(_label("UP", -8.0, p["height"] - 14.0, p))
    part = part.cut(_label("WILDCAM", -30.0, 8.0, p))
    return part
