"""窓 案S — ドーム蓋前提の作り直し（カメラ送り出し筒 + ドーム座）.

> **作り直しの経緯**: 当初の案S は「前面から突き出した末広がりの筒 + 平板の窓」
> だった。その後、既製品の実物が **ドリンク用の透明ドーム蓋**（口径 76.0 /
> 深さ 32.2 / **頂点の平らな窓 φ25.0** / 肉厚 0.4）に確定したので、
> これを前提に作り直した。平板ではなくこのドームが窓になる。
> 比較と根拠は `docs/window-options.md`。

## この設計を支配する条件: レンズは平窓から 16.0 mm 以内

```
L_max = (25.0 / 2) / tan(37.98 度) = 16.01 mm
```

**ドームのフランジ位置（32.2 mm 奥）では半角 21.2 度（対角 42.4 度）しかなく、
四隅が大きく欠ける。** そこで前壁から筒を前方に伸ばし、カメラを 16 mm 圏内まで
送り出して、その上からドームを被せる。防犯カメラと同じ作り。

この設計ではレンズ前面を z = 26.6、平窓を z = 40.2 に置くので距離は **13.6 mm**。
上限 16.01 に対して **2.4 mm の余裕**がある（入射瞳がレンズ前面より後ろにある
ぶんの逃げ）。`fov` チェックが `dome apex ring` との干渉として機械的に検証する。

## 座標

  原点 = 筐体前面の外面。**+Z が屋外（被写体）方向**。
  ドームの縁は取付板の前面 z = 5.0 に座り、頂点の平窓は z = 37.2。

## ドームの保持と防水の役割分担

  - **保持** = 既製品の嵌合。ドーム蓋にはカップの縁に嵌まる溝が元から成形されて
    いるので、筐体側にカップ縁と同形状のリブを印刷すれば設計どおり嵌合する。
    **工具なしで着脱でき、傷んだら買って交換できる。**
  - **防水** = そのリブの内側に敷く O リング（φ2.0 コード / 中心径 66）。

**嵌合溝の寸法は未実測**（`parts/dome_lid.UNMEASURED` に 7 項目）。
いまのリブ寸法は推定値で、実測が来たら差し替える。

## ドームが割れたときに中身を水没させない

肉厚 0.4 mm は変更できないので、**ドームは消耗品**として扱う。
密閉境界を 2 段にして、割れても被害をカメラ室に閉じ込める。

  1 段目: ドーム + O リング  -> カメラ室（この設計の筒の中）を密閉する
  2 段目: 筐体の前壁 + FPC 貫通の封止 -> **本体（Pi / Onyx）を守る**

FPC は取付板の φ8 のポートを通し、シーラントで埋める。ここが 2 段目の境界。
ドームが割れるとカメラ室（約 90 cm3）は浸水するが、本体は乾いたまま残り、
ドームとカメラを交換すれば復帰できる。

## 未確定

  - 嵌合溝の寸法 7 項目（実測待ち）
  - 入射瞳の位置。レンズ前面を円錐の頂点に置いているが、実際の瞳は
    それより後ろにある。`PUPIL_DEPTH_MM` に入れれば判定が自動で厳しくなる。
  - 庇を足すかどうか（`docs/window-options.md` で評価。既定では足さない）
"""

import math

import cadquery as cq

from harness import feature, fit, fov
from parts import cam_module3, dome_lid, oring

DESIGN_NAME = "window_snoot"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    # 取付板
    "plate_dia": 90.0,
    # ヒートセット 6.0 が板の中に収まる厚み。裏に出っ張らせないので
    # 裏面がそのままビルドプレートに載り、サポートが要らない。
    "plate_t": 8.0,
    # ドームの座（嵌合リブ）— 寸法は推定。実測待ち
    "rim_od": dome_lid.GROOVE_ID,     # 推定 75.4
    "rim_h": dome_lid.LIP_H,          # 推定 6.0
    "rim_wall": 2.5,
    "bead_h": dome_lid.GROOVE_H,      # 推定 3.0
    "bead_out": 0.6,                  # 推定: 抜け止めビードの張り出し
    # ドーム用 O リング（φ2.0 コード）
    "dome_oring_mean": 66.0,
    "dome_oring_w": oring.GROOVE_WIDTH,
    "dome_oring_d": oring.GROOVE_DEPTH,
    # カメラ送り出し筒
    "tube_x": 32.0,
    "tube_y": 30.0,
    "cam_pcb_z": 19.0,                # 基板前面の z。ここで 16 mm 条件が決まる
    "boss_dia": 5.4,                  # M2 セルフタッピング。CSI コネクタを避ける径
    "boss_pilot": 1.6,                # M2 セルフタッピング
    # FPC 貫通ポート（2 段目の密閉境界。シーラントで埋める）
    "fpc_port_dia": 8.0,
    "fpc_port_r": 24.0,               # O リング溝 (内径 31.65) の内側に収める
    # 取付ねじ。**大きく・少なく**（現地 UX 原則）。角度は非等分でポカヨケ
    "screw_dia": 4.5,
    # ねじは O リング溝の**内側**に置く。止まり穴なので漏れ経路にならず、
    # 板を大きくせずに済む。角度は非等分にしてポカヨケにする。
    "screw_pcd": 50.0,
    "screw_angles_deg": (90.0, 200.0, 320.0),
    "boss_depth": 6.0,                # 板厚 8.0 の中に収める（貫通させない）
    "min_wall": 1.6,
    "feature_margin": 0.8,
}

#: 造形姿勢。光軸 (+Z) を造形方向に平行に保つこと。
PRINT_ORIENTATION = {"rotate": (0, 0, 0)}
OPTICAL_AXIS = (0.0, 0.0, 1.0)

#: 入射瞳がレンズ前面より後ろにある量。**未検証**。測れたらここに入れれば
#: 視野判定が自動で厳しくなる。
PUPIL_DEPTH_MM = 0.0

LENS_FRONT_Z = PARAMS["cam_pcb_z"] + cam_module3.LENS_H          # 23.6
DOME_RIM_Z = PARAMS["plate_t"]                                   # 5.0
DOME_WINDOW_Z = DOME_RIM_Z + dome_lid.DEPTH                      # 37.2
LENS_TO_WINDOW = DOME_WINDOW_Z - LENS_FRONT_Z                    # 13.6
LENS_TO_WINDOW_LIMIT = dome_lid.max_lens_distance()              # 16.01

COMPONENTS = [
    # レンズを光軸に載せるため、基板中心は FPC の反対側へ LENS_OFFSET だけずらす
    cam_module3.place(at=(0.0, cam_module3.LENS_OFFSET, PARAMS["cam_pcb_z"])),
    # 平窓の外側（像として使えない曲面部）。ここに視野が掛かったら FAIL
    dome_lid.place_apex_ring(at=(0.0, 0.0, DOME_RIM_Z)),
]

VIEW_CONES = [
    fov.Cone.from_camera(
        cam_module3,
        apex=(0.0, 0.0, LENS_FRONT_Z - PUPIL_DEPTH_MM),
        axis=(0.0, 0.0, 1.0), length=90.0, start=0.5,
        note=(
            f"レンズ前面 z={LENS_FRONT_Z} から平窓 z={DOME_WINDOW_Z} まで "
            f"{LENS_TO_WINDOW:.1f} mm（上限 {LENS_TO_WINDOW_LIMIT:.2f}）"
        ),
    )
]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.3,
    "voxel_pitch_mm": 0.8,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": PARAMS["fpc_port_dia"], "count": 1,
         "note": "FPC 貫通ポート（シーラントで埋める = 2 段目の密閉境界）"},
    ],
}


def screw_positions(p=PARAMS):
    r = p["screw_pcd"] / 2
    return [(r * math.cos(math.radians(a)), r * math.sin(math.radians(a)))
            for a in p["screw_angles_deg"]]


def clearance_margin_mm() -> float:
    """16 mm 条件に対する余裕。入射瞳の逃げでもある."""
    return LENS_TO_WINDOW_LIMIT - LENS_TO_WINDOW


def max_hood_projection(y_offset: float) -> float:
    """高さ y_offset の庇が視野に入らずに前へ出せる距離（z）."""
    t = math.tan(math.radians(cam_module3.half_angle_deg()))
    return (y_offset / t) + LENS_FRONT_Z


def features(p=PARAMS):
    m = p["feature_margin"]
    out = [
        feature.cylinder(
            "camera_bay", (0.0, cam_module3.LENS_OFFSET),
            max(p["tube_x"], p["tube_y"]) + 2.0,
            0.0, p["cam_pcb_z"], margin=0.0,
            note="カメラ送り出し筒とその中の基板・ボス（同軸に連続するのでまとめる）",
        ),
        feature.ring(
            "dome_seat", (0.0, 0.0),
            (p["dome_oring_mean"] / 2 - p["dome_oring_w"] / 2) + p["rim_od"] / 2,
            p["rim_od"] / 2 - (p["dome_oring_mean"] / 2 - p["dome_oring_w"] / 2),
            p["plate_t"] - p["dome_oring_d"] - p["min_wall"],
            p["plate_t"] + p["rim_h"], margin=m,
            note="ドームの嵌合リブと O リング溝（接するのが正しいのでまとめる）",
        ),
        feature.cylinder(
            "fpc_port", (0.0, -p["fpc_port_r"]), p["fpc_port_dia"],
            0.0, p["plate_t"], margin=m, note="FPC 貫通ポート",
        ),
    ]
    for i, pos in enumerate(screw_positions(p)):
        out.append(feature.cylinder(
            f"screw_boss_{i}", pos, p["screw_dia"] + 2 * p["min_wall"],
            0.0, p["boss_depth"] + p["min_wall"], margin=m,
            note="M4 ヒートセット（止まり穴。板の中に収める）",
        ))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    plate = cq.Workplane("XY").circle(f.boss(p["plate_dia"]) / 2).extrude(p["plate_t"])

    # ドームの嵌合リブ（カップの縁と同形状。寸法は推定・実測待ち）
    rim_od = f.boss(p["rim_od"])
    rim = (
        cq.Workplane("XY")
        .circle(rim_od / 2).circle(rim_od / 2 - p["rim_wall"])
        .extrude(p["rim_h"]).translate((0, 0, p["plate_t"]))
    )
    bead = (
        cq.Workplane("XY")
        .circle(rim_od / 2 + p["bead_out"]).circle(rim_od / 2 - p["rim_wall"])
        .extrude(p["bead_h"])
        .translate((0, 0, p["plate_t"] + p["rim_h"] - p["bead_h"]))
    )
    part = plate.union(rim).union(bead)

    # カメラ送り出し筒
    tube = (
        cq.Workplane("XY")
        .box(p["tube_x"], p["tube_y"], p["cam_pcb_z"] - p["plate_t"] + 0.01,
             centered=(True, True, False))
        .translate((0, cam_module3.LENS_OFFSET, p["plate_t"]))
    )
    part = part.union(tube)
    # 中は抜く（カメラ基板と CSI コネクタの逃げ）
    part = part.cut(
        cq.Workplane("XY")
        .box(p["tube_x"] - 2 * p["min_wall"], p["tube_y"] - 2 * p["min_wall"],
             p["cam_pcb_z"], centered=(True, True, False))
        .translate((0, cam_module3.LENS_OFFSET, p["plate_t"]))
    )
    # 基板を受けるボス 4 本
    for x, y in cam_module3.hole_positions():
        px, py = x, y + cam_module3.LENS_OFFSET
        part = part.union(
            cq.Workplane("XY").circle(f.boss(p["boss_dia"]) / 2)
            .extrude(p["cam_pcb_z"] - 1.0 - p["plate_t"])
            .translate((px, py, p["plate_t"]))
        )
        part = part.cut(
            cq.Workplane("XY").circle(f.hole(p["boss_pilot"]) / 2).extrude(5.0)
            .translate((px, py, p["cam_pcb_z"] - 1.0 - 5.0))
        )

    # ドーム用 O リング溝（取付板の前面）
    part = part.cut(
        oring.groove_profile(
            p["dome_oring_mean"],
            f.uncompensated(p["dome_oring_w"], "溝幅は未実測"),
            f.uncompensated(p["dome_oring_d"], "溝深さは未実測"),
        ).translate((0, 0, p["plate_t"]))
    )

    # FPC 貫通ポート
    part = part.cut(
        cq.Workplane("XY").circle(f.hole(p["fpc_port_dia"]) / 2)
        .extrude(p["plate_t"] + 2).translate((0, -p["fpc_port_r"], -1.0))
    )

    # 取付ねじの止まり穴（裏面から。ヒートセット想定）
    # 取付ねじ（ヒートセット）の止まり穴。板の中に収めるので裏に出っ張らない。
    for x, y in screw_positions(p):
        part = part.cut(
            cq.Workplane("XY").circle(f.hole(p["screw_dia"]) / 2)
            .extrude(p["boss_depth"] + 1.0).translate((x, y, -1.0))
        )
    return part
