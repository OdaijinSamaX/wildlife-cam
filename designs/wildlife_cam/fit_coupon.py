"""公差校正クーポン — 1 回の印刷で嵌合公差テーブルを確定させるための部品.

想定する取り付け方: 取り付けない。印刷して測るだけの校正用治具。
P1S / ASA / 0.4 mm ノズル / 0.2 mm 層で刷る前提。

この 1 枚で決めるもの:
  - M3 ヒートセットインサートの下穴径 (φ4.0 / 4.2 / 4.4)
  - M3 通し穴のクリアランス      (φ3.2 / 3.4 / 3.6)
  - 薄板の実効肉厚               (0.8 / 1.2 / 1.6 / 2.0)
  - O リング溝の実寸             (φ2.0 コード / 溝 2.70 x 1.50)
  - 軸穴嵌合                     (基準軸 φ10.0 に対し φ10.1 / 10.2 / 10.3 / 10.4)

未確定事項:
  - ヒートセットインサートの実物 (OD 4.6 / L5.0 は推定) が届くまで、
    どの下穴が正解かは決まらない。この部品はその答えを出すための道具。
  - ASA の収縮率は実測していない。Z 方向と XY 方向で違うはずだが未確認。

薄板 0.8 mm は **意図的に** min_wall_mm を下回る。だから CHECK_CONFIG の
min_wall_mm はこの設計だけ 0.8 にしてある（wall チェックが薄板を実測できて
いることを report の min_wall で確認する）。

## 台座が 100 x 70 から 120 x 90 に大きくなった経緯（2026-08-22）

初版では O リング溝（中心 30,-17 / 帯 r13.65..16.35）が基準ピン φ10.0
（中心 26,3）の根元を **0.95 mm 削っていた**。中心間距離 20.40 mm に対して
必要なのは 16.35 + 5.00 = 21.35 mm。overhang チェックが z=8 に span 0.95 mm の
下向き面として報告していたが、当時は原因が読めていなかった。

100 x 70 のままでは、6 段のフィーチャ列と φ33 の O リング帯を、すべての
フィーチャ間に 1.6 mm 以上の材料を残して並べることができない。台座を
120 x 90 に広げ、同時に `features()` で各フィーチャの占有領域を宣言して
`layout` チェックに突き合わせさせるようにした。
"""

import math

import cadquery as cq

from harness import feature
from parts import oring

DESIGN_NAME = "fit_coupon"

PARAMS = {
    # 台座
    "plate_l": 120.0,          # 設計値（初版 100.0 から拡大。上の経緯を参照）
    "plate_w": 90.0,           # 設計値（初版 70.0 から拡大）
    "plate_t": 8.0,            # 設計値（ヒートセット下穴 6 mm + 底 2 mm）
    # ヒートセット下穴（止まり穴）
    "heatset_dias": (4.0, 4.2, 4.4),   # 試験値
    "heatset_depth": 6.0,              # 設計値（インサート 5.0 + 逃げ 1.0）
    "heatset_x0": -52.0,               # 設計値
    "heatset_pitch": 14.0,             # 設計値
    # M3 通し穴
    "clear_dias": (3.2, 3.4, 3.6),     # 試験値
    "clear_x0": -8.0,                  # 設計値
    "clear_pitch": 14.0,               # 設計値
    "hole_row_y": 31.0,                # 設計値（上記 2 群を同じ列に置く）
    "hole_label_y": 22.0,              # 設計値
    # 軸穴 + 基準ピン
    "shaft_ref_dia": 10.0,             # 基準軸の呼び径
    "shaft_pin_h": 12.0,               # 設計値
    "shaft_pin_x": 16.0,               # 設計値
    "shaft_dias": (10.1, 10.2, 10.3, 10.4),  # 試験値
    "shaft_x0": -50.0,                 # 設計値
    "shaft_pitch": 16.0,               # 設計値
    "shaft_row_y": 10.0,               # 設計値
    "shaft_label_y": 0.0,              # 設計値
    # 薄板（垂直フィン）
    "fin_thicknesses": (0.8, 1.2, 1.6, 2.0),  # 試験値
    "fin_len": 12.0,                   # 設計値
    "fin_h": 12.0,                     # 設計値
    "fin_y": -19.0,                    # 設計値
    "fin_x0": -52.0,                   # 設計値
    "fin_pitch": 14.0,                 # 設計値
    "fin_label_y": -29.0,              # 設計値
    # O リング溝
    "oring_mean_dia": 30.0,            # 設計値
    "oring_groove_w": oring.GROOVE_WIDTH,  # parts/oring.py の根拠に従う
    "oring_groove_d": oring.GROOVE_DEPTH,
    "oring_cx": 36.0,                  # 設計値（初版 30.0。ピンとの食い合いを解消）
    "oring_cy": -24.0,                 # 設計値（初版 -17.0）
    # 刻印
    "label_size": 6.0,                 # 設計値（size 4 では文字の線幅が 0.6 mm を切り
                                       #   wall チェックに引っかかった。実測で 6.0 に上げた）
    "label_depth": 0.6,                # 設計値（0.2 mm 層 x 3）
    "title_x": -25.0,                  # 設計値
    "title_y": 39.0,                   # 設計値
    # layout チェック用
    "feature_margin": 0.8,             # min_wall(1.6) / 2。フィーチャ間に残す材料の半分
    "min_wall": 1.6,                   # 止まり穴の下に残す肉
}

PRINT_ORIENTATION = {"rotate": (0, 0, 0)}   # 平置き。台座の裏がビルドプレート。

COMPONENTS = []   # 内蔵部品なし（校正治具なので）

CHECK_CONFIG = {
    "min_wall_mm": 0.8,          # 薄板 0.8 mm を意図的に含むため（他の設計は 1.6）
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 0.8,
    "openings_match_tol_mm": 0.05,
    "expected_openings": [
        {"diameter_mm": 3.2, "count": 1, "note": "M3 通し穴 試験 A"},
        {"diameter_mm": 3.4, "count": 1, "note": "M3 通し穴 試験 B"},
        {"diameter_mm": 3.6, "count": 1, "note": "M3 通し穴 試験 C"},
        {"diameter_mm": 10.1, "count": 1, "note": "軸穴 試験 A"},
        {"diameter_mm": 10.2, "count": 1, "note": "軸穴 試験 B"},
        {"diameter_mm": 10.3, "count": 1, "note": "軸穴 試験 C"},
        {"diameter_mm": 10.4, "count": 1, "note": "軸穴 試験 D"},
    ],
}


# --- フィーチャの位置（build と features が同じ関数を使う） ------------------


def heatset_positions(p):
    return [
        (f"heatset_{d:.1f}", p["heatset_x0"] + i * p["heatset_pitch"], p["hole_row_y"], d)
        for i, d in enumerate(p["heatset_dias"])
    ]


def clear_positions(p):
    return [
        (f"clear_{d:.1f}", p["clear_x0"] + i * p["clear_pitch"], p["hole_row_y"], d)
        for i, d in enumerate(p["clear_dias"])
    ]


def shaft_positions(p):
    return [
        (f"shaft_{d:.1f}", p["shaft_x0"] + i * p["shaft_pitch"], p["shaft_row_y"], d)
        for i, d in enumerate(p["shaft_dias"])
    ]


def fin_positions(p):
    return [
        (f"fin_{t:.1f}", p["fin_x0"] + i * p["fin_pitch"], p["fin_y"], t)
        for i, t in enumerate(p["fin_thicknesses"])
    ]


def label_specs(p):
    """(名前, 文字列, x, y) の一覧。刻印はすべてここから作る."""
    out = []
    for name, x, _y, d in heatset_positions(p) + clear_positions(p):
        out.append((f"label_{name}", f"{d:.1f}", x, p["hole_label_y"]))
    for name, x, _y, d in shaft_positions(p):
        out.append((f"label_{name}", f"{d:.1f}", x, p["shaft_label_y"]))
    out.append(
        (
            "label_shaft_ref",
            f"{p['shaft_ref_dia']:.1f}",
            p["shaft_pin_x"],
            p["shaft_label_y"],
        )
    )
    for name, x, _y, t in fin_positions(p):
        out.append((f"label_{name}", f"{t:.1f}", x, p["fin_label_y"]))
    out.append(("label_oring", "OR20", p["oring_cx"], p["oring_cy"]))
    out.append(("label_title", "FIT COUPON v1", p["title_x"], p["title_y"]))
    return out


def _label_shape(text: str, x: float, y: float, p: dict) -> cq.Workplane:
    """台座上面に彫り込む文字（切り抜き用のソリッド）."""
    return (
        cq.Workplane("XY")
        .text(text, p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((x, y, p["plate_t"] - p["label_depth"]))
    )


# --- 占有領域の宣言 --------------------------------------------------------


def features(p=PARAMS):
    """各フィーチャが所有すべき材料領域。規約は harness/feature.py の docstring.

    ピンとフィンは「台座から立つ」ので、足元の板を厚み方向いっぱいまで claim する。
    そうしないと、溝がピンの根元を削っていても z が重ならず検出できない。
    """
    m = p["feature_margin"]
    t = p["plate_t"]
    out = []

    for name, x, y, d in heatset_positions(p):
        # 止まり穴: 空洞 + その下に残すべき肉
        out.append(feature.cylinder(
            name, (x, y), d, t - p["heatset_depth"] - p["min_wall"], t, margin=m,
            note="ヒートセット下穴（止まり穴 + 底肉）",
        ))
    for name, x, y, d in clear_positions(p) + shaft_positions(p):
        out.append(feature.cylinder(
            name, (x, y), d, 0.0, t, margin=m, note="貫通穴",
        ))

    out.append(feature.cylinder(
        "shaft_ref_pin", (p["shaft_pin_x"], p["shaft_row_y"]), p["shaft_ref_dia"],
        0.0, t + p["shaft_pin_h"], margin=m,
        note="基準ピン（足元の板を厚み方向いっぱいまで claim）",
    ))
    for name, x, y, th in fin_positions(p):
        out.append(feature.box(
            name, (x, y), (p["fin_len"], th), 0.0, t + p["fin_h"], margin=m,
            note="薄板フィン（足元の板ごと claim）",
        ))

    out.append(feature.ring(
        "oring_groove", (p["oring_cx"], p["oring_cy"]),
        p["oring_mean_dia"], p["oring_groove_w"],
        t - p["oring_groove_d"] - p["min_wall"], t, margin=m,
        note="O リング溝（溝 + 底肉）",
    ))

    for name, text, x, y in label_specs(p):
        out.append(feature.from_shape(
            name, _label_shape(text, x, y, p), margin=m,
            z0=t - p["label_depth"], z1=t, note="刻印",
        ))
    return out


# --- 形状 ------------------------------------------------------------------


def build(p=PARAMS):
    plate = cq.Workplane("XY").box(
        p["plate_l"], p["plate_w"], p["plate_t"], centered=(True, True, False)
    )

    cuts = cq.Workplane("XY")
    adds = cq.Workplane("XY")

    for _name, x, y, d in heatset_positions(p):
        cuts = cuts.union(
            cq.Workplane("XY").circle(d / 2).extrude(p["heatset_depth"])
            .translate((x, y, p["plate_t"] - p["heatset_depth"]))
        )
    for _name, x, y, d in clear_positions(p) + shaft_positions(p):
        cuts = cuts.union(
            cq.Workplane("XY").circle(d / 2).extrude(p["plate_t"] + 2)
            .translate((x, y, -1.0))
        )

    adds = adds.union(
        cq.Workplane("XY").circle(p["shaft_ref_dia"] / 2).extrude(p["shaft_pin_h"])
        .translate((p["shaft_pin_x"], p["shaft_row_y"], p["plate_t"]))
    )
    for _name, x, y, th in fin_positions(p):
        adds = adds.union(
            cq.Workplane("XY")
            .box(p["fin_len"], th, p["fin_h"], centered=(True, True, False))
            .translate((x, y, p["plate_t"]))
        )

    cuts = cuts.union(
        oring.groove_profile(
            p["oring_mean_dia"], p["oring_groove_w"], p["oring_groove_d"]
        ).translate((p["oring_cx"], p["oring_cy"], p["plate_t"]))
    )

    for _name, text, x, y in label_specs(p):
        cuts = cuts.union(_label_shape(text, x, y, p))

    return plate.union(adds).cut(cuts)
