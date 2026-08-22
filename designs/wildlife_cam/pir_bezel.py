"""PIR 窓ベゼル — HC-SR501 を筐体壁に防水で貫通させる部品.

想定する取り付け方:
  筐体壁（厚み 3.0 mm）に φ29.2 の丸穴を開け、このベゼルを **外側から** 差し込む。
  スピゴットが穴を通って筐体内側へ 3.2 mm 出る。その端面が HC-SR501 の基板を
  内側から押さえる面になる（基板を固定するボスは筐体本体側の役目、次フェーズ）。
  フランジは M3 x 4 本で筐体壁の外側から締める。

シール（この設計の核心）:
  1. フェイスシール  ベゼルのフランジ裏 (z=0) の溝に φ2.0 O リング（中心径 35）。
                     ベゼルと筐体壁の外面の間を塞ぐ。取付ねじはこの溝の外側に置く
                     ので、ねじ穴から水が入っても密閉空間には届かない。
                     ただし **筐体側のねじボスは止まり穴にすること**（次フェーズの制約）。
  2. ラジアルシール  ベゼル内径の溝（Ø25.25 x 幅 2.0）に φ1.5 O リング。
                     HC-SR501 のドーム根元の円筒スカート（φ23.0）に半径方向で当てる。

なぜ「窓を張る」構成ではないのか（動かさないこと）:
  PIR は遠赤外を見るので、アクリルや PC の窓を透過しない。したがってフレネル
  レンズは外気に露出させるしかない。ドームは基板に対して密封されていないので、
  基板側を筐体内側に置き、シール面はドーム外周と筐体壁（= このベゼル）の間に作る。

なぜフランジ面ではなくスカートで radial に封じるのか:
  HC-SR501 のフランジ（推定 φ24.6）とドーム（推定 φ23.0）の差は片側 0.8 mm しかなく、
  φ2.0 はもちろん φ1.0 の O リングを座らせる平坦部も取れない。フェイスシールは
  物理的に成立しない。円筒スカートに対するラジアルシールなら 5 mm の掛かりが使える。

未確定事項:
  - HC-SR501 の実寸がすべて推定（parts/hcsr501.py 参照）。特に
    スカート高さ 5.0 mm とドーム径 φ23.0 が違うと、この設計は成立しない。
    **実測が入るまで印刷しないこと。**
  - φ1.5 の O リングコードは手元にない。入手できなければ溝を φ2.0 用に引き直す
    （その場合 bore 径と外径の全体が 1 mm 大きくなる）。
  - 筐体壁の厚み 3.0 mm は wildlife-cam 本体設計の前提であって、まだ確定していない。
"""

import math

import cadquery as cq

from harness import feature
from parts import hcsr501

DESIGN_NAME = "pir_bezel"

PARAMS = {
    # 筐体壁 / スピゴット
    "wall_t": 3.0,                 # 前提（wildlife-cam 本体の想定壁厚）
    "wall_hole_dia": 29.2,         # 設計値（スピゴット + 片側 0.1）
    "spigot_dia": 29.0,            # 設計値
    "spigot_len": 6.2,             # 設計値（壁 3.0 + 内側へ 3.2 出して基板押さえにする）
    # 内径まわり
    "bore_dia": 23.4,              # 設計値（ドーム φ23.0 + 片側 0.2）
    "counterbore_dia": 25.4,       # 設計値（PIR フランジ 推定 φ24.6 の逃げ）
    "counterbore_depth": 1.0,      # 設計値（PIR フランジ厚 推定 1.0）
    # ラジアル O リング溝（φ1.5 コード / 圧縮率 25%）
    "radial_groove_dia": 25.25,    # 計算値: 23.0 + 2 * (1.5 * 0.75)
    "radial_groove_w": 2.0,        # 計算値: 1.5 * 1.35 を丸め
    "radial_groove_z0": -3.6,      # 設計値（溝下端）
    # フランジ
    "flange_dia": 52.0,            # 設計値
    "flange_t": 3.4,               # 設計値
    "chamfer_start_z": 1.2,        # 設計値（ここから 45 度で開いて PIR の視野を空ける）
    # フェイス O リング溝（φ2.0 コード）
    "face_groove_mean": 35.0,      # 設計値
    "face_groove_w": 2.70,         # parts/oring.py の根拠に従う
    "face_groove_d": 1.50,
    # 取付ねじ
    "screw_pcd": 45.0,             # 設計値
    "screw_dia": 3.4,              # fit_coupon で確定させる（暫定 3.4）
    "screw_count": 4,              # 設計値
    "min_wall": 1.6,               # 設計方針（ASA / 0.4 mm ノズル / 壁 4 本）
    "feature_margin": 0.8,         # min_wall / 2。layout チェックのフィーチャ間マージン
}

PRINT_ORIENTATION = {"rotate": (180, 0, 0)}
# フランジ上面を下にして寝かせる。こうするとフェイス O リング溝が上向きに開き、
# 溝底がサポート無しで出る。下向きに残るのはラジアル溝の片側ひさし（幅 0.9 mm）だけ。

# HC-SR501 は基板前面がスピゴット端面 (z = -spigot_len) に当たる位置に置く。
COMPONENTS = [hcsr501.place(at=(0, 0, -PARAMS["spigot_len"]))]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    # ドームとベゼル内径は封止のためわざと詰めてある（片側 0.2 mm）ので、
    # 判定用クリアランスは既定の 0.4 ではなく 0.15 mm を使う。
    "component_clearance_mm": 0.15,
    "voxel_pitch_mm": 0.5,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": 23.4, "count": 1,
         "note": "PIR ドーム貫通口 — ラジアル O リングで封止"},
        {"diameter_mm": 3.4, "count": 4,
         "note": "M3 取付ねじ — フェイス O リング溝の外側"},
    ],
}

SECTIONS = [
    {"name": "xz_mid", "origin": (0, 0, 0), "normal": (0, -1, 0)},
    {"name": "yz_mid", "origin": (0, 0, 0), "normal": (-1, 0, 0)},
]


def profile(p: dict) -> list[tuple[float, float]]:
    """回転断面の (半径, z) 多角形。z=0 が筐体壁の外面、+z が屋外側."""
    r_bore = p["bore_dia"] / 2
    r_cb = p["counterbore_dia"] / 2
    r_spigot = p["spigot_dia"] / 2
    r_flange = p["flange_dia"] / 2
    r_groove = p["radial_groove_dia"] / 2
    z_bottom = -p["spigot_len"]
    z_cb_top = z_bottom + p["counterbore_depth"]
    z_g0 = p["radial_groove_z0"]
    z_g1 = z_g0 + p["radial_groove_w"]
    z_flange_top = p["flange_t"]
    z_ch = p["chamfer_start_z"]
    r_ch = r_bore + (z_flange_top - z_ch)          # 45 度
    fg_in = p["face_groove_mean"] / 2 - p["face_groove_w"] / 2
    fg_out = p["face_groove_mean"] / 2 + p["face_groove_w"] / 2
    fg_d = p["face_groove_d"]

    return [
        (r_spigot, z_bottom),
        (r_spigot, 0.0),
        (fg_in, 0.0),
        (fg_in, fg_d),          # フェイス溝 内壁
        (fg_out, fg_d),         # フェイス溝 天井
        (fg_out, 0.0),          # フェイス溝 外壁
        (r_flange, 0.0),
        (r_flange, z_flange_top),
        (r_ch, z_flange_top),
        (r_bore, z_ch),         # 45 度の面取り（PIR の視野を確保）
        (r_bore, z_g1),
        (r_groove, z_g1),       # ラジアル溝 天井
        (r_groove, z_g0),
        (r_bore, z_g0),         # ラジアル溝 底（造形時の下向きひさし 0.9 mm）
        (r_bore, z_cb_top),
        (r_cb, z_cb_top),       # 座ぐり天井
        (r_cb, z_bottom),
        (r_spigot, z_bottom),
    ]


def features(p=PARAMS):
    """フィーチャの占有領域。規約は harness/feature.py の docstring.

    内径まわり（座ぐり / ラジアル溝 / 面取り）は**同軸に積み上がっていて互いに
    接するのが正しい**ので、ひとつの円柱 `bore_column` としてまとめて claim する。
    別々に宣言すると、意図した連続を「食い合い」として誤検出してしまう。

    横方向に並ぶ取付ねじとフェイス O リング溝は、まさにここで距離を保証したい
    組み合わせなので、別々に宣言する。
    """
    m = p["feature_margin"]
    r_ch = p["bore_dia"] / 2 + (p["flange_t"] - p["chamfer_start_z"])
    out = [
        feature.cylinder(
            "bore_column",
            (0.0, 0.0),
            2 * r_ch,
            -p["spigot_len"],
            p["flange_t"],
            margin=m,
            note="内径の同軸スタック（座ぐり / ラジアル溝 / ボア / 面取り）",
        ),
        feature.ring(
            "face_oring_groove",
            (0.0, 0.0),
            p["face_groove_mean"],
            p["face_groove_w"],
            0.0,
            p["face_groove_d"] + p["min_wall"],
            margin=m,
            note="フェイス O リング溝（溝 + 上に残す肉）",
        ),
    ]
    n = int(p["screw_count"])
    r = p["screw_pcd"] / 2
    for i in range(n):
        a = 2 * math.pi * i / n
        out.append(feature.cylinder(
            f"screw_{i}",
            (r * math.cos(a), r * math.sin(a)),
            p["screw_dia"],
            0.0,
            p["flange_t"],
            margin=m,
            note="M3 取付ねじ（貫通）",
        ))
    return out


def build(p=PARAMS):
    pts = profile(p)
    body = (
        cq.Workplane("XZ")
        .polyline([(r, z) for r, z in pts])
        .close()
        .revolve(360, (0, 0, 0), (0, 1, 0))  # XZ ワークプレーンのローカル Y = グローバル Z
    )
    holes = cq.Workplane("XY")
    n = int(p["screw_count"])
    r = p["screw_pcd"] / 2
    for i in range(n):
        a = 2 * math.pi * i / n
        holes = holes.union(
            cq.Workplane("XY")
            .circle(p["screw_dia"] / 2)
            .extrude(p["flange_t"] + 2)
            .translate((r * math.cos(a), r * math.sin(a), -1.0))
        )
    return body.cut(holes)
