"""公差校正クーポン v2 — 補正テーブルを通した版 + 基準ピンを独立部品に.

想定する取り付け方: 取り付けない。印刷して測るだけの校正用治具。
P1S / ASA / 0.4 mm ノズル / 0.2 mm 層 / 平置きで刷る前提。

## v1 からの変更点

### 1. 基準ピンを台座から切り離した（v1 の設計ミスの修正）

v1 では基準ピン φ10.0 が台座と一体で生えていたため、**同じ板の軸穴に挿して
嵌合を確かめることが物理的にできなかった。** クーポンの目的の半分が達成
できていない。

v2 ではピンを台座から独立させ、台座を貫く φ18.0 のソケット穴の中に立てて、
底の細いタブ 2 本（2.0 x 0.6 mm）だけで繋ぐ。手で折り取れば自由なピンになり、
そのまま隣の軸穴 10.1 / 10.2 / 10.3 / 10.4 に挿して確かめられる。

  - タブは第 1 層側（z = 0 〜 0.8）にしか無いので、測定に使う高さ
    （z = 2 〜 14）には折り跡が残らない。
  - ピンはビルドプレートに直接立つので、下向きの張り出しが出ない。
  - ピンの軸は軸穴と同じく造形方向に平行。**同じ向きで刷ったもの同士**を
    嵌合させるので、比較に意味がある。

### 2. 寸法補正テーブルを通した

PARAMS には **狙い寸法**（印刷後にこうなってほしい寸法）だけを書く。
`FIT_TABLE` が図面寸法へ変換する。設計側で 0.3 を足し引きしない。

  軸穴 10.1 -> 図面 10.4 / 小穴 3.2 -> 図面 3.45 / 基準ピン 10.0 -> 図面 10.25
  薄板 0.8 -> 図面 0.8（補正不要）

**v2 を刷って測った値が、そのまま補正テーブルの答え合わせになる。**
軸穴が狙いどおり 10.1 で出れば、+0.30 の補正が正しかったことになる。

## この 1 枚で決めるもの（v1 と同じ）

  - M3 ヒートセットインサートの下穴径 (φ4.0 / 4.2 / 4.4)
  - M3 通し穴のクリアランス      (φ3.2 / 3.4 / 3.6)
  - 薄板の実効肉厚               (0.8 / 1.2 / 1.6 / 2.0)
  - O リング溝の実寸             (φ2.0 コード / 溝 2.70 x 1.50)
  - 軸穴嵌合                     (基準ピン φ10.0 に対し φ10.1 / 10.2 / 10.3 / 10.4)

## 未確定事項

  - 小穴の補正 +0.25 は **暫定**。ノギスで小径の内径を測る確度が低いため。
    v2 ではピンゲージかドリル刃の実測値と突き合わせて詰めること。
  - **溝幅は補正の根拠が無い**（v1 では測っていない）。`uncompensated()` で
    無補正のまま通し、report に「無補正」として記録される。v2 で測ること。
  - φ5 〜 φ8 の穴は実測点が無く、テーブルは外挿になる。v3 で埋めたい。
  - ヒートセットインサートの実物がまだ無いので、どの下穴が正解かは未確定。
    v1 では 3 種とも貫通していないこと（設計どおり）だけを確認した。
"""

import math

import cadquery as cq

from harness import feature, fit
from parts import oring

DESIGN_NAME = "fit_coupon_v2"

#: 2026-08-22 に v1 を実測して起こしたテーブル。素性は harness/fit.py。
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    # 台座
    "plate_l": 120.0,
    "plate_w": 90.0,
    "plate_t": 8.0,
    # ヒートセット下穴（止まり穴）— 狙い寸法
    "heatset_dias": (4.0, 4.2, 4.4),
    "heatset_depth": 6.0,
    "heatset_x0": -52.0,
    "heatset_pitch": 14.0,
    # M3 通し穴 — 狙い寸法
    "clear_dias": (3.2, 3.4, 3.6),
    "clear_x0": -8.0,
    "clear_pitch": 14.0,
    "hole_row_y": 31.0,
    "hole_label_y": 24.0,
    # 軸穴 — 狙い寸法
    "shaft_dias": (10.1, 10.2, 10.3, 10.4),
    "shaft_x0": -50.0,
    "shaft_pitch": 16.0,
    "shaft_row_y": 10.0,
    "shaft_label_y": 0.0,
    # 独立した基準ピン（折り取り式）
    "pin_dia": 10.0,                # 狙い寸法
    "pin_h": 15.0,
    "pin_x": 20.0,
    "pin_y": 10.0,
    "pin_socket_dia": 18.0,         # 狙い寸法（ピンを抜くための逃げ）
    "pin_label_y": -5.0,
    "tab_w": 1.5,                   # 折り取りタブの幅
    # 折り取りタブの高さ。0.2 mm 層 x 4。薄板の最小 0.8 と同値にしてあるので、
    # このクーポンの min_wall_mm 0.8 を下回らない（下回ると wall が FAIL する）。
    "tab_h": 0.8,
    "tab_count": 2,
    # 薄板（垂直フィン）— 狙い寸法
    "fin_thicknesses": (0.8, 1.2, 1.6, 2.0),
    "fin_len": 12.0,
    "fin_h": 12.0,
    "fin_y": -19.0,
    "fin_x0": -52.0,
    "fin_pitch": 14.0,
    "fin_label_y": -29.0,
    # O リング溝
    "oring_mean_dia": 30.0,
    "oring_groove_w": oring.GROOVE_WIDTH,
    "oring_groove_d": oring.GROOVE_DEPTH,
    "oring_cx": 38.0,
    "oring_cy": -26.0,
    # 刻印
    "label_size": 6.0,
    "label_depth": 0.6,
    "title_x": -25.0,
    "title_y": 39.0,
    # layout チェック用
    "feature_margin": 0.8,
    "min_wall": 1.6,
}

PRINT_ORIENTATION = {"rotate": (0, 0, 0)}   # 平置き。台座の裏と基準ピンの底がプレート。

COMPONENTS = []


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
    out = []
    for name, x, _y, d in heatset_positions(p) + clear_positions(p):
        out.append((f"label_{name}", f"{d:.1f}", x, p["hole_label_y"]))
    for name, x, _y, d in shaft_positions(p):
        out.append((f"label_{name}", f"{d:.1f}", x, p["shaft_label_y"]))
    out.append(("label_ref_pin", f"{p['pin_dia']:.1f}", p["pin_x"], p["pin_label_y"]))
    for name, x, _y, t in fin_positions(p):
        out.append((f"label_{name}", f"{t:.1f}", x, p["fin_label_y"]))
    out.append(("label_oring", "OR20", p["oring_cx"], p["oring_cy"]))
    out.append(("label_title", "FIT COUPON v2", p["title_x"], p["title_y"]))
    return out


def _label_shape(text: str, x: float, y: float, p: dict) -> cq.Workplane:
    return (
        cq.Workplane("XY")
        .text(text, p["label_size"], p["label_depth"] + 1.0, combine=False)
        .translate((x, y, p["plate_t"] - p["label_depth"]))
    )


# --- 期待する開口（狙い寸法で宣言する） -------------------------------------


def _expected_openings(p):
    rows = [
        {"diameter_mm": d, "count": 1, "note": f"M3 通し穴 φ{d}"}
        for _n, _x, _y, d in clear_positions(p)
    ]
    rows += [
        {"diameter_mm": d, "count": 1, "note": f"軸穴 φ{d}"}
        for _n, _x, _y, d in shaft_positions(p)
    ]
    rows.append(
        {"diameter_mm": p["pin_socket_dia"], "count": 1,
         "note": "基準ピンのソケット（折り取り後にピンが抜ける）"}
    )
    return rows


CHECK_CONFIG = {
    "min_wall_mm": 0.8,          # 薄板 0.8 mm を意図的に含むため
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 0.8,
    "openings_match_tol_mm": 0.05,
    "expected_openings": _expected_openings(PARAMS),
}


# --- 占有領域の宣言 --------------------------------------------------------


def features(p=PARAMS):
    m = p["feature_margin"]
    t = p["plate_t"]
    out = []

    for name, x, y, d in heatset_positions(p):
        out.append(feature.cylinder(
            name, (x, y), d, t - p["heatset_depth"] - p["min_wall"], t, margin=m,
            note="ヒートセット下穴（止まり穴 + 底肉）",
        ))
    for name, x, y, d in clear_positions(p) + shaft_positions(p):
        out.append(feature.cylinder(name, (x, y), d, 0.0, t, margin=m, note="貫通穴"))

    # ソケット穴・ピン・タブはひとつの領域としてまとめて claim する
    out.append(feature.cylinder(
        "ref_pin_socket", (p["pin_x"], p["pin_y"]), p["pin_socket_dia"],
        0.0, t + p["pin_h"], margin=m,
        note="折り取り式の基準ピンとそのソケット穴（タブを含む）",
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
    """PARAMS は狙い寸法。図面寸法への変換は FIT_TABLE がまとめて行う."""
    f = FIT_TABLE

    plate = cq.Workplane("XY").box(
        p["plate_l"], p["plate_w"], p["plate_t"], centered=(True, True, False)
    )

    cuts = cq.Workplane("XY")
    adds = cq.Workplane("XY")

    for _name, x, y, d in heatset_positions(p):
        cuts = cuts.union(
            cq.Workplane("XY").circle(f.hole(d) / 2).extrude(p["heatset_depth"])
            .translate((x, y, p["plate_t"] - p["heatset_depth"]))
        )
    for _name, x, y, d in clear_positions(p) + shaft_positions(p):
        cuts = cuts.union(
            cq.Workplane("XY").circle(f.hole(d) / 2).extrude(p["plate_t"] + 2)
            .translate((x, y, -1.0))
        )

    # --- 折り取り式の基準ピン ---
    socket_r = f.hole(p["pin_socket_dia"]) / 2
    pin_r = f.boss(p["pin_dia"]) / 2
    cuts = cuts.union(
        cq.Workplane("XY").circle(socket_r).extrude(p["plate_t"] + 2)
        .translate((p["pin_x"], p["pin_y"], -1.0))
    )
    adds = adds.union(
        cq.Workplane("XY").circle(pin_r).extrude(p["pin_h"])
        .translate((p["pin_x"], p["pin_y"], 0.0))
    )
    n = int(p["tab_count"])
    for i in range(n):
        a = 2 * math.pi * i / n
        length = socket_r - pin_r + 2.0          # 両側に食い込ませて確実に繋ぐ
        tab = (
            cq.Workplane("XY")
            .box(length, f.wall(p["tab_w"]), p["tab_h"], centered=(False, True, False))
            .translate((pin_r - 1.0, 0, 0))
            .rotate((0, 0, 0), (0, 0, 1), math.degrees(a))
            .translate((p["pin_x"], p["pin_y"], 0.0))
        )
        adds = adds.union(tab)

    for _name, x, y, th in fin_positions(p):
        adds = adds.union(
            cq.Workplane("XY")
            .box(p["fin_len"], f.wall(th), p["fin_h"], centered=(True, True, False))
            .translate((x, y, p["plate_t"]))
        )

    cuts = cuts.union(
        oring.groove_profile(
            p["oring_mean_dia"],
            f.uncompensated(p["oring_groove_w"], "溝幅は v1 で測っていない"),
            f.uncompensated(p["oring_groove_d"], "溝深さは v1 で測っていない"),
        ).translate((p["oring_cx"], p["oring_cy"], p["plate_t"]))
    )

    for _name, text, x, y in label_specs(p):
        cuts = cuts.union(_label_shape(text, x, y, p))

    # 先に穴と刻印を抜いてから、立ち上がるものを足す。
    # 逆順だとソケット穴の切り抜きが折り取りタブごと削ってしまう。
    return plate.cut(cuts).union(adds)
