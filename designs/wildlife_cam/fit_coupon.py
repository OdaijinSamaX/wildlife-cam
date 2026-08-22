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
"""

import cadquery as cq

from parts import m3_heatset, oring

DESIGN_NAME = "fit_coupon"

PARAMS = {
    # 台座
    "plate_l": 100.0,          # 設計値（手のひらに載るサイズ）
    "plate_w": 70.0,           # 設計値
    "plate_t": 8.0,            # 設計値（ヒートセット下穴 6 mm + 底 2 mm）
    # ヒートセット下穴
    "heatset_dias": (4.0, 4.2, 4.4),   # 試験値
    "heatset_depth": 6.0,              # 設計値（インサート 5.0 + 逃げ 1.0）
    "heatset_y": 24.0,                 # 設計値
    "heatset_x0": -44.0,               # 設計値
    "heatset_pitch": 14.0,             # 設計値
    # M3 通し穴
    "clear_dias": (3.2, 3.4, 3.6),     # 試験値
    "clear_x0": 2.0,                   # 設計値
    "clear_pitch": 14.0,               # 設計値
    # 軸穴
    "shaft_ref_dia": 10.0,             # 基準軸の呼び径
    "shaft_pin_h": 12.0,               # 設計値
    "shaft_dias": (10.1, 10.2, 10.3, 10.4),  # 試験値
    "shaft_y": 3.0,                    # 設計値
    "shaft_x0": -42.0,                 # 設計値
    "shaft_pitch": 16.0,               # 設計値
    "shaft_pin_x": 26.0,               # 設計値
    # 薄板
    "fin_thicknesses": (0.8, 1.2, 1.6, 2.0),  # 試験値
    "fin_len": 12.0,                   # 設計値
    "fin_h": 12.0,                     # 設計値
    "fin_y": -22.0,                    # 設計値
    "fin_x0": -40.0,                   # 設計値
    "fin_pitch": 14.0,                 # 設計値
    # O リング溝
    "oring_mean_dia": 30.0,            # 設計値
    "oring_groove_w": oring.GROOVE_WIDTH,  # parts/oring.py の根拠に従う
    "oring_groove_d": oring.GROOVE_DEPTH,
    "oring_cx": 30.0,                  # 設計値
    "oring_cy": -17.0,                 # 設計値
    # 刻印
    "label_size": 6.0,                 # 設計値（size 4 では文字の線幅が 0.6 mm を切り
                                   #   wall チェックに引っかかった。実測で 6.0 に上げた）
    "label_depth": 0.6,                # 設計値（0.2 mm 層 x 3）
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


def _label(text: str, x: float, y: float, p: dict) -> cq.Workplane:
    """台座上面に彫り込む文字（切り抜き用のソリッドを返す）."""
    return (
        cq.Workplane("XY")
        .text(text, p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((x, y, p["plate_t"] - p["label_depth"]))
    )


def build(p=PARAMS):
    plate = cq.Workplane("XY").box(
        p["plate_l"], p["plate_w"], p["plate_t"], centered=(True, True, False)
    )

    cuts = cq.Workplane("XY")
    adds = cq.Workplane("XY")

    # --- ヒートセット下穴（止まり穴） ---
    for i, d in enumerate(p["heatset_dias"]):
        x = p["heatset_x0"] + i * p["heatset_pitch"]
        cuts = cuts.union(
            cq.Workplane("XY").circle(d / 2).extrude(p["heatset_depth"])
            .translate((x, p["heatset_y"], p["plate_t"] - p["heatset_depth"]))
        )
        cuts = cuts.union(_label(f"{d:.1f}", x, p["heatset_y"] - 9.0, p))

    # --- M3 通し穴 ---
    for i, d in enumerate(p["clear_dias"]):
        x = p["clear_x0"] + i * p["clear_pitch"]
        cuts = cuts.union(
            cq.Workplane("XY").circle(d / 2).extrude(p["plate_t"] + 2)
            .translate((x, p["heatset_y"], -1.0))
        )
        cuts = cuts.union(_label(f"{d:.1f}", x, p["heatset_y"] - 9.0, p))

    # --- 軸穴 + 基準ピン ---
    for i, d in enumerate(p["shaft_dias"]):
        x = p["shaft_x0"] + i * p["shaft_pitch"]
        cuts = cuts.union(
            cq.Workplane("XY").circle(d / 2).extrude(p["plate_t"] + 2)
            .translate((x, p["shaft_y"], -1.0))
        )
        cuts = cuts.union(_label(f"{d:.1f}", x, p["shaft_y"] - 11.0, p))
    adds = adds.union(
        cq.Workplane("XY").circle(p["shaft_ref_dia"] / 2).extrude(p["shaft_pin_h"])
        .translate((p["shaft_pin_x"], p["shaft_y"], p["plate_t"]))
    )
    cuts = cuts.union(
        _label(f"{p['shaft_ref_dia']:.1f}", p["shaft_pin_x"],
               p["shaft_y"] - 11.0, p)
    )

    # --- 薄板（垂直フィン） ---
    for i, t in enumerate(p["fin_thicknesses"]):
        x = p["fin_x0"] + i * p["fin_pitch"]
        adds = adds.union(
            cq.Workplane("XY")
            .box(p["fin_len"], t, p["fin_h"], centered=(True, True, False))
            .translate((x, p["fin_y"], p["plate_t"]))
        )
        cuts = cuts.union(_label(f"{t:.1f}", x, p["fin_y"] - 9.0, p))

    # --- O リング溝 ---
    cuts = cuts.union(
        oring.groove_profile(
            p["oring_mean_dia"], p["oring_groove_w"], p["oring_groove_d"]
        ).translate((p["oring_cx"], p["oring_cy"], p["plate_t"]))
    )
    cuts = cuts.union(_label("OR20", p["oring_cx"], p["oring_cy"], p))

    # --- 表題 ---
    cuts = cuts.union(_label("FIT COUPON v1", -22.0, 31.0, p))

    return plate.union(adds).cut(cuts)
