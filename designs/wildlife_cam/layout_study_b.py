"""レイアウト検討 案B — 前後 2 層（Pi と Onyx を奥行き方向に重ねる）

**最終設計ではなく比較検討。** 目的は候補を並べて選べる状態にすること。
外殻は単純な直方体シェルで、分割線・蓋・ボス・リブは入れていない
（実物はここから 1 割前後は太る）。比較の軸と結論は `docs/layout-study.md`。

## この案の折り返し方

Pi と OTG を前層 (y 0〜10)、Onyx を後層 (y 14〜27) に置く。**両者は Y で
重ならない**ので、micro-USB ハウジングが Onyx の前を素通りできる。これが
この案の折り返しの本質で、前面積を小さくできる。

## 収める 5 点（+ OTG ケーブル）

  Pi Zero 2 W      65 x 30 / 基板厚 1.0 / 表 8.8（GPIO ピン先）/ 裏 0.4
  SORACOM Onyx     実測 89.4 x 35.8 x 13.2（後端 20.8 は厚み 9.3）
  **Onyx + OTG の USB-A を挿した剛体ブロック 115.0 mm ← 配置を支配する寸法**
  OTG ケーブル     全長 150（剛体 65.8 / 可動 84.2）
  HC-SR501         基板 32.8 x 24.4 / 全高 23.8 / ドーム φ23.0
  Camera Module 3  25 x 24（CSI コネクタ未実測のため位置は仮）

## 前提

  - 座標: 前面 = -Y（カメラと PIR が向く側）、背面 = +Y（樹側）、上 = +Z
  - バッテリーは筐体の外。中に入れない（開ける回数を減らして防水を保つため）
  - IR 投光器は別筐体。隔壁も発熱対策も不要
  - **外部アンテナ (CRC9) は使わない**（ドングル単体で通信確認済み・2026-08-22）。
    そのぶん内蔵アンテナ 1 本なので、**Onyx を壁際に置き、金属と他の基板を
    近づけない**配置ルールを守る（`アンテナ配置ルール` の指標で見る）
  - 指示で確定した貫通は **グランド / PIR / ベントの 3 つ**。ただし
    **カメラ窓を 4 つ目として置いている**（カメラが外を見るには開口が要るため）。
    窓を接着封止しても漏水経路としては貫通と同じ扱いにすべき、という判断。
    ここは確認が要る
  - 取り付け方法は未決定。奥行きがあるので、背面に柱用クランプ（半割りブラケット）を付ける方式が合う。

## 未確定

  - Camera Module 3 の CSI コネクタ位置が未実測。FPC 150 mm（曲げを引いた
    実効 100〜120）が届く範囲、という条件だけで置いている
  - 蓋の分割位置・パッキン溝・ボスは未設計
"""

import math

from harness import feature, fit
from parts import otg_cable, pi_zero_2w

# 相対 import は使えない（load_design が単体モジュールとして読むため）
from designs.wildlife_cam._layout_common import Hole, Layout, box, onyx_assembly

DESIGN_NAME = "layout_study_b"
FIT_TABLE = fit.ASA_P1S

PARAMS = {"wall": 3.0, "clearance": 1.0, "inner_margin": 2.0}

PRINT_ORIENTATION = {"rotate": (90, 0, 0)}
#: 蓋になる面を上に向けて刷る。閉じた箱は天井ができて造形できないので、
#: 本体は開口を上にして刷り、蓋は平板として別に刷る（蓋は未設計）。


def _layout(p=PARAMS) -> Layout:
    # 前後 2 層。前層に Pi と OTG、後層に剛体ブロック。Y で重ならないので
    # micro-USB ハウジングが Onyx の前を素通りできる。
    boxes = onyx_assembly((120.0, 21.0, 18.0), "-X", "Z") + [
        box("pi", (32.5, 5.1, 63.0), "xzy",
            note="前層。前板にべた置き。Onyx のアンテナ端から 12 mm 離す"),
        box("otg_micro", (46.8, 3.4, 32.6), "zxy",
            note="データ口から -Z に 30.8。Onyx の前を素通りする"),
        box("pir", (31.0, 11.35, 108.0), "xzy", note="前壁を貫くキャリア φ52 込み"),
        box("cam", (85.0, 5.5, 62.0), "xzy", note="CSI 未確定のため仮置き"),
    ]
    routes = [{
        "name": "otg_flex",
        "radius": otg_cable.CABLE_DIA / 2 + 2.0,
        "points": [(46.8, 3.4, 17.2), (60.0, 4.5, 10.0), (85.0, 10.0, 6.0),
                   (110.0, 17.0, 9.0), (123.0, 20.5, 16.0)],
    }]
    holes = [
        Hole("gland", "-Z", 20.0, 20.0, 12.6, "ケーブルグランド PG7（電源）"),
        Hole("pir", "-Y", 31.0, 108.0, 26.0, "PIR 貫通口"),
        Hole("vent", "-Z", 110.0, 20.0, 12.3, "防水通気ベント M12"),
        Hole("cam_window", "-Y", 85.0, 62.0, 16.0, "カメラ窓（指示の 3 つには数えられていない）"),
    ]
    return Layout(boxes=boxes, holes=holes, routes=routes,
                  wall=p["wall"], clearance=p["clearance"],
                  inner_margin=p["inner_margin"])


LAYOUT = _layout()
COMPONENTS = LAYOUT.components()

#: 比較表に載せる指標。docs/layout-study.md がこれを引く。
METRICS = LAYOUT.metrics()
METRICS["カメラ-Pi 直線距離 (mm)"] = round(
    math.dist(
        [b.center for b in LAYOUT.boxes if b.name == "cam"][0],
        [b.center for b in LAYOUT.boxes if b.name == "pi"][0],
    ), 1,
)
METRICS["OTG 可動長 (mm)"] = otg_cable.FLEX_LENGTH
METRICS["データ-電源 コネクタ間すきま (mm)"] = round(
    pi_zero_2w.connector_positions()["usb_power"][0]
    - pi_zero_2w.connector_positions()["usb_data"][1], 2,
)

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.0,   # キープアウトに一律すきまを含めてある
    "voxel_pitch_mm": 2.0,
    "openings_match_tol_mm": 0.1,
    # 機械的に繋がっていて接するのが正しい組。コネクタと相手、ケーブルと
    # ハウジング。宣言しておかないと layout が正しい設計を FAIL にする。
    "layout_allow_contact": [
        ["part_pi", "part_otg_micro"],          # micro-USB がデータ口に刺さる
        ["part_otg_micro", "otg_flex"],         # ケーブルが自分のハウジングから出る
        ["part_onyx_assembly", "otg_flex"],     # ケーブルが USB-A ハウジングに入る
    ],
    "interior_point": LAYOUT.interior_point(),
    "expected_openings": LAYOUT.expected_openings(FIT_TABLE),
}


def features(p=PARAMS):
    return LAYOUT.features(FIT_TABLE)


def build(p=PARAMS):
    return LAYOUT.shell(FIT_TABLE)
