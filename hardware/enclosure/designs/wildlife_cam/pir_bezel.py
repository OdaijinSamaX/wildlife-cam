"""PIR 接着封止キャリア — HC-SR501 を筐体壁に防水で貫通させる部品.

> ファイル名は `pir_bezel.py` のままだが、中身は **ベゼル（枠）ではなく
> 接着封止キャリア**である。2026-08-22 の実測でドームにツバが無いことが判明し、
> 「フランジを O リングで壁に押し付ける」という旧構成が不成立になったため
> 作り直した。既存の参照とレポート出力先を壊さないためファイル名は据え置く。
> 構成を選んだ根拠と、検討して不採用にした案は **docs/DECISIONS.md** にある。

## 前提が崩れた点（実測 2026-08-22）

`parts/hcsr501.py` の実測で **FLANGE_DIA == DOME_DIA == 23.0 mm**、
指でなぞっても段差が無いことを確認した。O リングを座らせるツバは存在しない。

## 採用した構成（案B: 接着封止キャリア）

  1. **ドーム ↔ キャリア: シーラント接着封止**
     内径 φ23.6 に対しドーム φ23.0 で片側 0.30 mm のボンドライン。
     接着代は円筒スカートの 3.3 mm をすべて使い、口元に φ25.6 x 深さ 1.2 mm の
     シーラント溜まりを設ける。外圧はシーラントを 0.30 mm の狭い隙間へ
     押し込む向きに働くので、抜け出す向きには効かない。
  2. **キャリア ↔ 筐体壁: フェイス O リング**
     φ2.0 コード / 中心径 34.0 / 溝 2.70 x 1.50。壁の内面に当てる。
     筐体壁の穴 φ26.0 を取り囲むので、穴から入った水はこの環の内側に閉じ込められる。
  3. 取付は M3 x 4 本を筐体内側から通し、壁の外側に張り出した肉厚パッドの
     ヒートセットインサートに締める。ねじは O リングの外側（乾燥側）にあるので
     漏れ経路にならない。**壁側のインサート穴は止まり穴にすること。**

PIR は接着するので交換できない。ただしキャリアは印刷部品で刷り直せるし
HC-SR501 は安価なので、失うものは小さい。詳しくは docs/DECISIONS.md。

## 造形姿勢（宣言）

`PRINT_ORIENTATION = {"rotate": (180, 0, 0)}` — **内径の軸は造形方向 (Z) に平行**。
これは意図的な宣言であり、変えてはいけない。

  - 軸を寝かせると、内径の積層線が軸方向に走ってシール面を縦断する。
    ラジアル方向の漏れ経路がそのまま出来上がるうえ、内径が垂れて真円でなくなる。
  - 軸を立てれば内径は同心の閉じたリングの積み重ねになり、
    層境界は軸に直交する面になる。接着面を縦断する連続した溝ができない。
  - 180 度反転しているのは、フェイス O リング溝の**シール面をビルドプレート側**に
    持ってくるため。第 1 層は最も平坦で密な面になる。
  - 反転後に下向きに残るのは O リング溝の底（幅 2.70）とシーラント溜まりの底
    （幅 1.00）だけで、どちらもブリッジで渡せる。

## パッキンの面圧（`seal` チェックを宣言しない理由）

  フェイス O リングは中心径 34.0、取付ねじは PCD 44 の 4 本なので、
  **隣り合う締結点の間隔は 34.6 mm**（円弧長）。たわみは支間の 4 乗で効くので、
  蓋（間隔 130 mm）に比べて 1/200 以下になり、面圧の落ちは問題にならない。
  したがって `SEAL_SPANS` は宣言していない（`docs/AGENTS.md` §6 の例外）。
  **考え忘れではなく、効かないと判断した。**

## 未確定事項

  - `parts/hcsr501.py` の HOLE_DIA / HOLE_PITCH は誤差の可能性あり。
    ただしこの設計は取付穴を使っていない（保持は接着）ので影響しない。
  - シーラントの選定が未定。フレネルドームは HDPE 系の可能性が高く、
    シリコーンは化学的に接着しない。**機械的な保持**（溜まり + 狭隙間への
    くさび効果）で成立させる設計にしてあるが、実物で剥離試験をすること。
  - 筐体壁の厚み 3.0 mm と、ねじパッドを壁の外側に張り出す方針は
    wildlife-cam 本体設計の前提であって、まだ確定していない。
"""

import math

import cadquery as cq

from harness import feature, fit
from parts import hcsr501, oring

DESIGN_NAME = "pir_bezel"

#: 寸法補正テーブル。PARAMS には狙い寸法だけを書き、図面寸法への変換はここが行う。
FIT_TABLE = fit.ASA_P1S

#: PARAMS はすべて **狙い寸法**（印刷後にこうなってほしい寸法）。
#: 例: bore_dia 23.6 は「刷り上がったときに 23.6 であってほしい」という意味で、
#: 図面に描かれるのは FIT_TABLE が返す 23.9 になる。
PARAMS = {
    # 筐体壁（相手側。この部品には含まれない）
    "wall_t": 3.0,                  # 前提（wildlife-cam 本体の想定壁厚）
    "wall_hole_dia": 26.0,          # 設計値（ドーム φ23.0 + 溜まりの視認代）
    # 内径まわり
    "bore_dia": 23.6,               # 設計値: ドーム 23.0 + 片側 0.30 のボンドライン
    "bond_depth": hcsr501.SKIRT_H,  # 実測 3.3（円筒スカートの全長を使う）
    "reservoir_dia": 25.6,          # 設計値: 内径 + 片側 1.0 のシーラント溜まり
    "reservoir_depth": 1.2,         # 設計値
    # PIR の収まり
    "pcb_pocket_l": hcsr501.PCB_L + 1.0,   # 実測 32.8 + 片側 0.5
    "pcb_pocket_w": hcsr501.PCB_W + 1.0,   # 実測 24.4 + 片側 0.5
    "pocket_depth": 10.0,           # 設計値: PCB 1.4 + 裏面部品 8.0 + 余裕 0.6
    # 前板（シール面を持つ円板）
    "plate_dia": 52.0,              # 設計値
    "plate_t": 6.0,                 # 設計値
    # 後胴（PCB ポケットを包む箱）
    "body_l": 37.0,                 # 設計値: ポケット 33.8 + 肉 1.6 x 2
    "body_w": 29.0,                 # 設計値: ポケット 25.4 + 肉 1.8 x 2
    # フェイス O リング溝（φ2.0 コード）
    "face_groove_mean": 34.0,       # 設計値
    "face_groove_w": oring.GROOVE_WIDTH,   # parts/oring.py の根拠に従う (2.70)
    "face_groove_d": oring.GROOVE_DEPTH,   # (1.50)
    # 取付ねじ
    "screw_pcd": 44.0,              # 設計値
    "screw_dia": 3.4,               # fit_coupon で確定させる（暫定 3.4）
    "screw_count": 4,               # 設計値（X 軸と Y 軸上に置く）
    "min_wall": 1.6,                # 設計方針（ASA / 0.4 mm ノズル / 壁 4 本）
    "feature_margin": 0.8,          # min_wall / 2
}

PRINT_ORIENTATION = {"rotate": (180, 0, 0)}
#: 内径の軸が造形方向に平行であること。docstring の「造形姿勢」を参照。
#: 変更するときは rx, ry が 0 か 180 であることを保つこと（tests が検証する）。
BORE_AXIS = (0.0, 0.0, 1.0)

# HC-SR501 は基板前面がポケットの座面 (z = -bond_depth) に来る位置に置く。
COMPONENTS = [hcsr501.place(at=(0, 0, -PARAMS["bond_depth"]))]

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    # ドームと内径の 0.30 mm はシーラントのボンドラインであって組立クリアランス
    # ではない。判定用クリアランスはその内側の 0.25 mm を使う。
    "component_clearance_mm": 0.25,
    "voxel_pitch_mm": 0.5,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": 23.6, "count": 1,
         "note": "PIR 貫通口 — 組立時にシーラントで封止する"},
        {"diameter_mm": 3.4, "count": 4,
         "note": "M3 取付ねじ — フェイス O リング溝の外側（乾燥側）"},
    ],
}

SECTIONS = [
    {"name": "xz_mid", "origin": (0, 0, 0), "normal": (0, -1, 0)},
    {"name": "yz_mid", "origin": (0, 0, 0), "normal": (-1, 0, 0)},
]


def screw_positions(p) -> list[tuple[float, float]]:
    """X 軸と Y 軸の上に置く。斜め 45 度だと PCB ポケットの角と食い合う."""
    r = p["screw_pcd"] / 2
    n = int(p["screw_count"])
    return [(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def profile(p: dict) -> list[tuple[float, float]]:
    """前板の回転断面 (半径, z)。z=0 が筐体壁に当たるシール面、-z が筐体内側.

    寸法はすべて FIT_TABLE を通す。狙い寸法をそのまま描くと、内径が
    0.30 mm 小さく刷り上がってボンドラインが 0.15 mm になってしまう。
    """
    f = FIT_TABLE
    r_bore = f.hole(p["bore_dia"]) / 2
    r_res = f.hole(p["reservoir_dia"]) / 2
    r_plate = f.boss(p["plate_dia"]) / 2
    z_back = -p["plate_t"]
    z_res = -p["reservoir_depth"]
    groove_w = f.uncompensated(p["face_groove_w"], "溝幅は未実測（v2 クーポンで測る）")
    fg_in = p["face_groove_mean"] / 2 - groove_w / 2
    fg_out = p["face_groove_mean"] / 2 + groove_w / 2
    fg_d = f.uncompensated(p["face_groove_d"], "溝深さは未実測（v2 クーポンで測る）")

    return [
        (r_bore, z_back),
        (r_bore, z_res),        # 内径（接着面）
        (r_res, z_res),         # シーラント溜まりの底
        (r_res, 0.0),           # 溜まりの外壁
        (fg_in, 0.0),           # シール面
        (fg_in, -fg_d),         # O リング溝 内壁
        (fg_out, -fg_d),        # O リング溝 底
        (fg_out, 0.0),          # O リング溝 外壁
        (r_plate, 0.0),
        (r_plate, z_back),
        (r_bore, z_back),
    ]


def features(p=PARAMS):
    """フィーチャの占有領域。規約は harness/feature.py の docstring."""
    m = p["feature_margin"]
    z_seat = -p["bond_depth"]
    z_pocket_bottom = z_seat - p["pocket_depth"]
    return [
        feature.cylinder(
            "pir_bore", (0.0, 0.0), p["reservoir_dia"], z_seat, 0.0, margin=m,
            note="内径 + シーラント溜まり（同軸に連続するのでひとつにまとめる）",
        ),
        feature.box(
            "pir_pocket", (0.0, 0.0), (p["pcb_pocket_l"], p["pcb_pocket_w"]),
            z_pocket_bottom, z_seat, margin=m,
            note="PIR 基板と裏面部品のポケット",
        ),
        feature.ring(
            "face_oring_groove", (0.0, 0.0),
            p["face_groove_mean"], p["face_groove_w"],
            -(p["face_groove_d"] + p["min_wall"]), 0.0, margin=m,
            note="フェイス O リング溝（溝 + 下に残す肉）",
        ),
    ] + [
        feature.cylinder(
            f"screw_{i}", pos, p["screw_dia"], -p["plate_t"], 0.0, margin=m,
            note="M3 取付ねじ（貫通）",
        )
        for i, pos in enumerate(screw_positions(p))
    ]


def build(p=PARAMS):
    plate = (
        cq.Workplane("XZ")
        .polyline(profile(p))
        .close()
        .revolve(360, (0, 0, 0), (0, 1, 0))  # XZ ワークプレーンのローカル Y = グローバル Z
    )

    z_back = -p["plate_t"]
    z_seat = -p["bond_depth"]
    z_bottom = z_seat - p["pocket_depth"]
    body = (
        cq.Workplane("XY")
        .box(p["body_l"], p["body_w"], z_back - z_bottom, centered=(True, True, False))
        .translate((0, 0, z_bottom))
    )
    part = plate.union(body)

    f = FIT_TABLE
    pocket = (
        cq.Workplane("XY")
        .box(
            f.uncompensated(p["pcb_pocket_l"], "角ポケットの補正規則がテーブルに無い"),
            f.uncompensated(p["pcb_pocket_w"], "角ポケットの補正規則がテーブルに無い"),
            p["pocket_depth"] + 1.0,
            centered=(True, True, False),
        )
        .translate((0, 0, z_bottom - 1.0))
    )
    part = part.cut(pocket)

    for x, y in screw_positions(p):
        part = part.cut(
            cq.Workplane("XY").circle(f.hole(p["screw_dia"]) / 2).extrude(p["plate_t"] + 2)
            .translate((x, y, z_back - 1.0))
        )
    return part
