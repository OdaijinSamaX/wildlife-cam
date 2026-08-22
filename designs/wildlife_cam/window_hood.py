"""窓 案H — 庇つき

**比較検討用。** 推奨案 layout_study_a の前面に載せる形で、窓の方式を 2 案作った
うちの一つ。比較軸と結論は `docs/window-options.md`。

## 座標

  原点 = 筐体前面の外面。**+Z が屋外（被写体）方向**。
  カメラは筐体の中にあり、レンズ前面は z = -(壁 3.0 + 逃げ 1.0) = -4.0。
  視野円錐の頂点はセンサ面 z = -11.6（レンズ前面から LENS_H 7.6 だけ後ろ）に置く。
  入射瞳の位置が未測定なので、円錐が最も太くなる側 = 保守側に倒してある。

## 窓は印刷しない

透明フィラメントで刷っても層の線で曇るので、**窓は買った平板を嵌める**前提。
必須条件は **850 nm の近赤外を透過する**こと（IR カットフィルタは使えない）。
材料の比較は `docs/window-options.md`。

## 案H — 庇（ひさし）

窓の上に前へ張り出す屋根を付けるだけの単純な構成。板 1 枚ぶんの追加で、
造形も真っ直ぐ立つだけなのでサポートが要らない。

庇は視野円錐の外側に置く。円錐は z が進むほど太るので、庇の張り出しには
上限がある（この寸法では約 15 mm）。

## 視野

Camera Module 3 標準レンズ 焦点距離 4.74 / センサ対角 7.4 から導出した
**対角半角 37.98 度**（対角 75.95 度。公表値 約 75 度とほぼ一致）。
**真っ直ぐな筒は L < 1.281 r でしか成立しない**ので、細長い筒は作れない。
開口は円錐に沿って末広がりにしてある。`fov` チェックが実測する。
"""

import math

import cadquery as cq

from harness import feature, fit, fov
from parts import cam_module3

DESIGN_NAME = "window_hood"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    "wall_t": 3.0,               # 筐体前面の壁厚（相手側）
    "window_gap": cam_module3.WINDOW_GAP,   # レンズ前面と壁内面のすきま
    "plate_size": 50.0,          # 取付板の一辺
    "plate_t": 5.0,              # 取付板の厚み
    "aperture_margin": 0.5,      # 視野円錐に足す余裕（半径）
    "pane_dia": 30.0,            # 買う平板の直径（φ30 x 2.0 を想定）
    "pane_t": 2.0,
    "pane_fit": 0.4,             # 平板まわりのシーラント代（直径で）
    "pane_recess": 0.4,          # 平板の外面を板面より沈める量
    "screw_pcd": 42.0,
    "screw_dia": 3.4,
    "screw_count": 4,
    "min_wall": 1.6,
    "feature_margin": 0.8,
    # 庇の張り出しは視野円錐が決める。内面 y=24.0 なら
    # (z + 11.6) * tan(37.98) <= 24 -> z <= 19.1 なので、板の 5.0 から 13.0 まで。
    "hood_proj": 13.0,
    "hood_t": 3.0,
    "hood_inner_y": 24.0,        # 庇の内面。板の半幅 25 より 1 mm 内側で繋ぐ
}

#: 造形姿勢。光軸 (+Z) を造形方向に平行に保つこと。
#: 開口は同心のリングの積み重ねになり、末広がりの面は 38 度でサポート不要。
PRINT_ORIENTATION = {"rotate": (0, 0, 0)}
OPTICAL_AXIS = (0.0, 0.0, 1.0)

#: レンズ前面の z。カメラはこれより後ろ。
LENS_FRONT_Z = -(PARAMS["wall_t"] + PARAMS["window_gap"])
#: 視野円錐の頂点 = センサ面
APEX_Z = LENS_FRONT_Z - cam_module3.LENS_H

# レンズを光軸に載せるため、基板中心は FPC の反対側へ LENS_OFFSET だけずらす。
COMPONENTS = [
    cam_module3.place(at=(0.0, cam_module3.LENS_OFFSET, APEX_Z)),
]

VIEW_CONES = [
    fov.Cone.from_camera(
        cam_module3, apex=(0.0, 0.0, APEX_Z), axis=(0.0, 0.0, 1.0), length=150.0,
    )
]


def cone_radius(z: float, p=PARAMS) -> float:
    """視野円錐の半径 + 余裕。開口はこれより外側に取る."""
    return (z - APEX_Z) * math.tan(math.radians(cam_module3.half_angle_deg())) \
        + p["aperture_margin"]


CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.3,
    "voxel_pitch_mm": 0.8,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": 3.4, "count": 4, "note": "M3 取付ねじ（貫通）"},
    ],
}


def _reach(p=PARAMS):
    return 0.0


def _extra(p=PARAMS):
    """庇。板の上辺から前（+Z）へ張り出す."""
    return (
        cq.Workplane("XY")
        .box(p["plate_size"], p["hood_t"], p["hood_proj"], centered=(True, True, False))
        .translate((0, p["hood_inner_y"] + p["hood_t"] / 2, p["plate_t"]))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    out = [
        feature.cylinder(
            "aperture", (0.0, 0.0),
            max(2 * cone_radius(p["plate_t"], p) + 2.0,
                p["pane_dia"] + p["pane_fit"] + 2.0),
            0.0, p["plate_t"], margin=0.0,
            note="視野円錐に沿った末広がりの開口 + 平板の座ぐり",
        ),
    ]
    r = p["screw_pcd"] / 2
    n = int(p["screw_count"])
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append(feature.cylinder(
            f"screw_{{i}}", (r * math.cos(a), r * math.sin(a)), p["screw_dia"],
            0.0, p["plate_t"], margin=m, note="M3 取付ねじ",
        ))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    plate = cq.Workplane("XY").box(
        f.boss(p["plate_size"]), f.boss(p["plate_size"]), p["plate_t"],
        centered=(True, True, False),
    )
    part = plate.union(_extra(p))

    # 視野円錐に沿った末広がりの開口
    part = part.cut(_aperture(p))

    # 買った平板の座ぐり（外面側）
    seat_d = f.hole(p["pane_dia"] + p["pane_fit"])
    seat_depth = p["pane_t"] + p["pane_recess"]
    part = part.cut(
        cq.Workplane("XY").circle(seat_d / 2).extrude(seat_depth + 1.0)
        .translate((0, 0, p["plate_t"] - seat_depth))
    )

    r = p["screw_pcd"] / 2
    n = int(p["screw_count"])
    for i in range(n):
        a = 2 * math.pi * i / n
        part = part.cut(
            cq.Workplane("XY").circle(f.hole(p["screw_dia"]) / 2)
            .extrude(p["plate_t"] + 2)
            .translate((r * math.cos(a), r * math.sin(a), -1.0))
        )
    return part


def _aperture(p=PARAMS):
    """視野円錐に沿った末広がりの穴。真っ直ぐな筒では成立しない."""
    z0, z1 = -1.0, p["plate_t"] + _reach(p)
    return cq.Workplane("XY").newObject([
        cq.Solid.makeCone(
            cone_radius(z0, p), cone_radius(z1, p), z1 - z0,
            cq.Vector(0, 0, z0), cq.Vector(0, 0, 1),
        )
    ])
