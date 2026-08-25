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

## 幅を 77 -> 84 -> **88** mm と増やしたことと、その代償

**1 度目（77 -> 84）はドーム蓋の口径 76.0 mm が決めた。** 案D の 77 mm には
嵌合リブ（外径 79.4）が入らない。

**2 度目（84 -> 88）は CSI レスキューを付けた Pi が決めた（D-022）。**
microSD を挿したままの剛体幅が **76.9 mm** あり、**旧・背面開口 74.0 を通らない。**
束縛していたのは内寸（78.0）ではなく**背面の開口**で、トレーは背面から
引き出すので、そこを通らなければ現地で保守できない。
**増やした片側 2 mm は全部内側（キャビティ）へ回してある。**

| | 案D 検討時 | D-014 | **本設計（D-022）** |
|---|---|---|---|
| 幅 | 77.0 mm | 84.0 mm | **88.0 mm** |
| 背面の開口 | — | 74.0 mm | **78.5 mm**（`rim_step` 2.0 -> 1.75） |
| 幹（直径 48）からの張り出し 片側 | 14.5 mm | 18.0 mm | **20.0 mm** |
| 受風面積 | 176 cm2 | 166 cm2 | **174 cm2**（+4.8%） |

**張り出しの上限はここで打ち止め**（`tests/test_camera_unit.py` が押さえている）。
これ以上幅を詰めるには、ドームを別の既製品に変えるか、
`docs/pcb-tray.md` §2 の x の収支を削るしかない。

## 優先順位（指示のとおり）

  1. 高さを超えない -> 198 mm（上限 229 に対し 31 mm の余裕）
  2. 張り出しを増やさない -> **D-022 で +2.0 mm を受け入れた**（現地で保守できる
     ことを優先した。理由と不採用案は D-022）
  3. 体積 -> 88 x 47 x 198 = 819 cm3（蓋とドームを除く）

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

  - **Onyx の保持**（Pi のトレーは `pcb_tray.py` に起こした）。
    Onyx は z 21〜136 に寝ているが、いまは何にも留まっていない
  - リブの本数と位置は**たわみ計算をしていない**。2 本の縦リブは目安
    （**蓋のたわみは `seal` チェックで数値化した。前壁のリブはまだ**）
"""

import math

import cadquery as cq

from harness import feature, fit, fov
from designs.wildlife_cam._layout_common import Box, onyx_assembly, route_solid
from harness.component import Component
from parts import (cable_gland, dome_lid, gore_vent, hcsr501, otg_cable,
                   pi_zero_2w_rescue)

DESIGN_NAME = "camera_unit"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    # --- 外形 ---
    # **84.0 から 88.0 へ改訂した（D-022）。** 84 は「ドーム嵌合リブ 外径 79.4 +
    # 肉 2.3 x 2」から出した数字だったが、**CSI レスキューブラケットを付けた Pi
    # （microSD 込みで 76.9 mm）が背面の開口 74.0 を通らない**ことが実測で分かった。
    # **増やした片側 2 mm は全部内側（キャビティ）へ回す。** 壁は 3.0 のまま、
    # 開口が 74.0 -> 78.5 になる。前面のドーム周りは結果として肉が 2.3 -> 4.3 に
    # 増えるが、**ドームは中心から動かさない**（窓の光軸を動かしたくない）。
    "width": 88.0,               # D-022（旧 84.0）
    "height": 198.0,             # 案D の 229 から 31 mm 減らした
    "wall": 3.0,
    "cavity_depth": 41.0,        # 前壁の内面から背面の合わせ面まで
    # 背面の合わせ面を内側へ張り出す量。**下限は 1.35**（= パッキン溝の幅の半分。
    # これより薄くすると蓋の溝が本体の land から外れる。
    # tests/test_camera_unit.py::test_body_land_carries_the_whole_gasket_groove）。
    # **2.0 -> 1.75 に薄くした。** 開口を 78.0 -> 78.5 まで広げないと、トレーが
    # 棚に載る掛かり代（片側 0.4）を取れないため。溝の内側に残る land は 0.4 mm。
    "rim_step": 1.75,            # D-022（旧 2.0）
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
    # **2026-08-25 に実測で確定（暫定値からの置き換え）。**
    # M4 ヒートセットの実測外径は 5.9（ラベル M4x8x6）。ヒートセットの下穴は
    # 「外径 − 0.4〜0.5」が定石なので 5.4〜5.5。**迷ったら小さい方**を採った
    # （細ければドリルで広げられるが、太いと樹脂が戻らず取り返しがつかない）。
    # 旧 5.0 は細すぎて、溶けた樹脂の行き場が無く柱が膨らむか割れる。
    "lid_screw_dia": 5.4,        # 実測 2026-08-25（M4 インサート外径 5.9 − 0.5）
    # **柱の肉 = (boss - pilot) / 2 が min_wall 1.6 を割らないこと。**
    # 旧 8.2 のままだと (8.2 − 5.4)/2 = 1.40 で割る。8.6 でちょうど 1.60 だが、
    # `wall` チェックはレイキャストの実測値なので閾値ちょうどは危ない。
    # **8.8 にして肉 1.70 を確保した**（外へ 0.3 太るだけで、
    # 柱の外縁は x=37.40。キャビティ内面 41.00 まで 3.60、land 内縁 39.25 まで 1.85）。
    "lid_boss_dia": 8.8,         # 2026-08-25（旧 8.2）
    "lid_boss_depth": 8.0,       # M4 インサートの有効深さ（= 噛み合い。実測 全長 8.0）
    # **下穴はインサートより深く彫る。** M4 x 30 の蝶ねじはインサートを 8 mm 噛んで
    # 先端が下穴の底に届く。ぴったりだと**先端が底を突いて締めたつもりで面圧が出ない**
    # ので、4 mm ぶん逃がしてある。`captive` チェックがこの噛み合いを毎回解く。
    # **M5 側の全長 10.0 が支配する**（実測 2026-08-25。ラベル M5x10x7）。
    # M4 は 8.0 + 逃げ 6.0、M5 は 10.0 + 逃げ 4.0 で、どちらも底を突かない。
    # 柱はキャビティ深さ 41.0 mm ぶん通っているので 14.0 は余裕で収まる。
    "lid_pilot_depth": 14.0,     # 2026-08-25（旧 12.0。M5 インサート 10.0 + 逃げ 4.0）
    # **6 点（3 対）**。四隅 4 点では長辺中央でパッキンが浮くと `seal` チェックが
    # 出した（圧縮率 13.3% < 下限 15%）。中央に 1 対足して 21% に戻してある。
    # 根拠と比較した案は docs/lid-fastening.md と D-019。
    # 柱は前壁から背面 land まで通す（浮かないし、箱のねじれにも効く）。
    # x=±33 はパッキン溝（39.65〜42.35）から座ぐりを 2 mm 以上離すため
    # （幅 88 化に合わせて ±31 -> ±33 / -30 -> -32 へ 2 mm 外へ動かした。D-022）。
    # **中央の対が z=142 なのは、左 (x=-31) で内蔵部品が空けている唯一の窓だから。**
    # Onyx が z 21〜136 を、Pi が z 148〜178 を塞いでいる（clearance が実測する）。
    # 真ん中 (z=99) に置ければ 24.4% になるが Onyx が居る。**2026-08-23 に
    # 「Onyx は動かさない」と人間が決定した**ので z=142 で確定（D-019）。
    # **並び順 = 現地で締める順序**（蓋の刻印 1..6）。中央 -> 対角 -> 対角。
    # **2026-08-25: 柱が太ったぶん z を動かして、元のクリアランスを取り戻した。**
    # 中央の対 142.0 -> 141.7（柱の影の天面 146.9 を維持。棚の下面 147.0 の下）。
    # 上の対 186.0 -> 186.5。**φ が 0.6 太ったので 0.2 上げただけでは底が下がる。**
    # 0.6 持ち上げたトレーの縁（+X 181.4 / -X 180.6）に対し、柱 + クリアランス 0.5 の
    # 底は 181.6 / 181.1 で余裕 +0.20 / +0.50（**旧設計の +0.00 / +0.20 より広い**）。
    # **トレー側の z 収支は 1 mm も余っていない**ので、トレーではなく柱を動かした。
    # 中央の対は Onyx (z <= 136) と 1.3 mm 空く。上の対は天井の内面 195 まで 3.9 mm。
    "lid_bosses": ((-33.0, 141.7), (33.0, 141.7), (-33.0, 12.0),
                   (33.0, 186.5), (33.0, 12.0), (-32.0, 186.5)),
    # **ポカヨケ**: 1 本だけ M5、かつ x を 1 mm ずらしてある。180 度回すと
    # M5 のねじが M4 のインサートに入らず、穴位置も合わない。
    # 中央の対が上下非対称（z=142 だけ）なので、**上下逆では穴自体が合わない。**
    "lid_big_index": 5,
    # M5 ヒートセットの実測外径は 6.9（ラベル M5x10x7）。同じ定石で 6.4〜6.5 の
    # **小さい方**。柱は肉 1.70 を確保するため 9.8（旧 9.4 では (9.4−6.4)/2 = 1.50）。
    "lid_big_screw_dia": 6.4,    # 実測 2026-08-25（M5 インサート外径 6.9 − 0.5）
    "lid_big_boss_dia": 9.8,     # 2026-08-25（旧 9.4）

    # --- 内部: 基板トレーの受け ---
    #
    # **2026-08-23 に 2 度目の作り直し（D-023）。** 1 度目（D-021）は側壁から
    # 内側へ伸ばした C チャンネルだったが、**CSI レスキューブラケットを付けた Pi は
    # 幅 76.9 mm（microSD 込み）あり、側壁から伸ばした棚の x 範囲を Pi 自身が
    # 占めてしまう。** 棚を Pi の外（x >= 38.85）まで下げると、今度は棚が
    # 2.15 mm の細いひさしになり、トレーが載る掛かり代が取れない。
    #
    # 代わりに **荷重は「前壁から張り出した全幅の床」で受ける。**
    # 側壁の棚をやめたので、**棚の z が柱に縛られなくなった**のが効いている。
    #
    #   棚（x ±34.5〜41・z 146.6〜148.0） … -Z（自重）。柱の影 146.1 のすぐ上
    #   上の押さえ（x ±20〜27）           … +Z。**天井から吊る**ので x の予算が要らない
    #   位置決めリップ（x ±39.25〜41）    … ±X
    #   前の当たり                        … -Y
    #   クリック止めの歯                  … +Y（蓋を開けているとき）
    #
    # **x の予算はもう 1 mm も余っていない**（下の x 収支）。だから
    # **+Z の押さえは「天井から吊ったフック」にした。** 側壁から内側へ出すと
    # Pi (|x| <= 38.45) と食い合うが、天井から吊れば x は柱の間 (|x| <= 27) で足り、
    # **z も Pi の上端 178.5 より上なので干渉しない。**
    #
    #   x 収支（片側）: 開口 39.25 -> トレー 38.85 (0.4) -> Pi 38.45 (0.4)
    #                   リップ内端 39.25 / 壁の内面 41.0（リップ厚 1.75）
    #   z 収支: 柱 146.9 -> 棚 147.0〜149.2 -> Pi 149.7〜179.7 -> 縁 180.8
    #           -> フック 180.6 (-X) / 181.4 (+X) -> 柱 181.3 は |x|<=25 に無い
    #
    # **ポカヨケ（原則 3）も「上の押さえ」に移した。** 棚に段を付けると Pi の
    # 下端（z 148.5）と食い合うが、押さえは z 179 より上にあって **Pi が居ない。**
    # 段は 1.0 mm —— **1.5 では、下げた側の押さえが「0.6 持ち上げた Pi の上端」に
    # 当たる**（178.5 + 0.6 = 179.1 vs 180.8 - 1.5 = 179.3 で余裕 0.2 しかない）。
    # 棚の**下面は z 147.0**。柱 (z=142, φ8.2 -> z 137.9〜146.1) の claim が
    # マージン 0.8 込みで 146.9 まで来るので、そこを踏まないぎりぎりの位置。
    "tray_z0": 149.2,            # 設計値。棚の天面 = トレーの下端
    # トレーの縁の上端（+X 側）。**柱 (z=186, 大 φ9.4 -> z 181.3〜) の 0.5 mm 下。**
    "tray_z1": 180.8,            # 設計値
    # 棚とフックの厚み（z 方向）。**クリック止めの切り欠き 0.4 を彫っても
    # 1.8 mm 残る**厚みにしてある（1.4 だと残り 0.9 で `wall` が落ちた）。
    "tray_ledge_t": 2.2,
    "tray_lift": 0.6,            # 上の押さえまでの遊び。歯が乗り越えるぶん
    "tray_seat_x": 34.5,         # 棚 / 前の当たり の内側の端（掛かり代 4.35 mm）
    # 天井から吊るフックの x 範囲。**大柱 (x=-32, φ9.4) の claim が
    # マージン込みで x -26.5 まで来る**ので、25.0 で止める（claim は 25.8）。
    "tray_hook_x": (18.0, 25.0),
    "tray_lip_x": 39.25,         # x 方向の位置決めリップの内側の端
    "tray_lip_h": 4.0,           # リップの高さ（棚の天面から）
    "tray_y0": 23.9,             # トレーの前面が当たる位置
    "tray_stop_t": 2.0,          # 前の当たりの厚み（y 方向）
    # **ポカヨケ（原則 3）**: 上の押さえは -X 側だけ 1.0 mm 低い。トレーの縁も
    # -X 側だけ 1.0 mm 低い。**左右・前後・上下のどの反転でも、高い方の縁が
    # 低い方のフックに当たる**（トレーは棚に載っているので下へ逃げられない）。
    # 検証と対照実験は tests/test_pcb_tray.py。
    # **0.8 なのは、下げた側のフック (180.8 - 0.8 + 0.6 = 180.6) が
    # 「0.6 持ち上げた Pi の上端」(179.7 + 0.6 = 180.3) に当たらない上限**だから。
    "tray_key_step": 0.8,
    # 抜け止めのクリック。**床の天面に切り欠き、トレーの下縁に歯**。
    "detent_h": 0.4,             # 設計値（歯の高さ = 切り欠きの深さ）
    "detent_y0": 24.1,           # 切り欠きの y 始点。トレーの板厚 23.9〜26.4 の中
    "detent_w": 2.1,             # 切り欠きの y 幅（歯 1.6 + 逃げ 0.25 x 2）
    # トレーの縁と位置決めリップの隙間（片側）。**層厚 0.2 の 2 倍以上を取る。**
    "tray_gap": 0.4,
    # --- リブ ---
    "rib_x": 35.0,          # 幅 88 化に合わせて外へ（D-022）
    "rib_w": 2.4,
    "rib_h": 5.0,
    # --- 刻印 ---
    "label_size": 6.0,
    "label_depth": 0.6,
}

#: 背面の開口を上にして刷る。造形 Z = 箱の奥行き 47 mm。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}
#: 基板トレーの差し込み方向。**背面（+Y）から差し込む。**
SLIDE_AXIS = (0.0, 1.0, 0.0)
#: **原則（AGENTS.md §4.9.3-2「段差が摺動方向と平行に走る姿勢」）から外している
#: ので根拠を書く。** 造形姿勢 rotate(90,0,0) では設計 Y が造形 Z になるため、
#: この方向の摺動は**積層の段差を横切る。**
#:
#:   1. **z 方向のスライドは幾何的に成立しない。** 蓋の柱 6 点が x 26.9〜35.1 を
#:      塞ぐので、幅 65 mm の Pi を載せたトレーは柱の z を通り抜けられない（D-021）。
#:   2. **これは精度嵌合ではなく落とし込みである。** 片側 0.4 mm（= 層厚 0.2 の
#:      2 倍）の隙間で、段差に引っかかる余地を残していない。
#:   3. **荷重を受ける面は摺動しない。** トレーの重量は棚の天面（z 方向）が受け、
#:      そこは差し込み方向と直交しているので擦れない。
SLIDE_AXIS_NOTE = ("z 方向は蓋の柱で塞がっている（D-021）。"
                   "落とし込みなので隙間 0.4 mm（D-023 でもこの向きは変えていない）")

#: **`UNDER_BOARD` を宣言しない理由**（`docs/AGENTS.md` §6。考え忘れではない）。
#: 基板を受けているのは**トレー**（`pcb_tray`）であって本体ではない。
#: 本体の中で基板の下面に近づく面は無いので、宣言する突起が無い。
#: **Onyx を保持する設計を起こしたら、そこでは宣言が要る**（§9 の未設計 1 番）。
UNDER_BOARD: list = []
SLIDE_FIT_CLEARANCE = PARAMS["tray_gap"]

W = PARAMS["width"]
H = PARAMS["height"]
WALL = PARAMS["wall"]
Y_CAVITY_0 = WALL
Y_CAVITY_1 = WALL + PARAMS["cavity_depth"]          # 44.0
Y_BACK = Y_CAVITY_1 + PARAMS["rim_t"]               # 47.0

# --- 内蔵部品の配置 ---------------------------------------------------------
#: 剛体ブロック 115 mm の USB-A 側の端。ここから -Z へ 115 伸びる（z 6..121）。
ONYX_AT = (-18.1, 34.4, 136.0)
#: **CSI レスキューブラケットを装着した Pi**（`parts/pi_zero_2w_rescue`）。
#: 裸の Pi (65.0) ではなく **microSD 込みの剛体幅 76.9 mm** で見る。
#: **背面の開口 (x ±39.25) の中央に置く**ので、基板の中心は x = -1.85 になる
#: （microSD が -X に 4.1 出るぶん、基板は +X 側へ寄らない）。
_R = pi_zero_2w_rescue
PI_RIGID_W = _R.rigid_width()                       # 76.9
#: 基板（PCB）の -X 端。= -(76.9/2) + microSD の突出 4.1
PI_BOARD_X0 = -PI_RIGID_W / 2 + _R.SD_CARD_PROTRUSION      # -34.35
PI_BOARD_CX = PI_BOARD_X0 + _R.PCB_L / 2                   # -1.85
#: トレーの板の上面（`pcb_tray` と**同じ数字を二重に持たない**ための導出）
TRAY_PLATE_Y1 = PARAMS["tray_y0"] + 2.5
#: Pi の座面（ボスの天面）。**ナット 2.7 mm + 逃げ 0.4 を空ける**（D-023 / underside）
PI_BOSS_H = _R.RELIEF_DEPTH + 0.7                          # 3.4
PI_BOARD_Y = TRAY_PLATE_Y1 + PI_BOSS_H                     # 基板下面 29.8
PI_Z0 = PARAMS["tray_z0"] + 0.5                            # 棚の天面 + 0.5
PI_BOX = Box(
    name="pi",
    center=(0.0,
            (PI_BOARD_Y - _R.RESCUE_BOT_H + PI_BOARD_Y + _R.PCB_T + _R.TOP_COMP_H) / 2,
            PI_Z0 + _R.PCB_W / 2),
    size=(PI_RIGID_W,
          _R.RESCUE_BOT_H + _R.PCB_T + _R.TOP_COMP_H,
          _R.PCB_W),
    note="横向き。コネクタ辺は下を向く。**レスキュー + microSD 込みの剛体幅 76.9**")
#: micro-USB データ口。基板の左角から 46.8 mm（`parts/pi_zero_2w` の実測から）。
MICRO_X = PI_BOARD_X0 + 46.8                               # 12.45
MICRO_BOX = Box(name="otg_micro",
                center=(MICRO_X, PI_BOARD_Y + 3.3, PI_Z0 - 30.8 / 2),
                size=(9.9, 6.8, 30.8), note="データ口（左角から 46.8）から -Z に 30.8")
FLEX_POINTS = [
    (MICRO_X, PI_BOARD_Y + 3.3, PI_Z0 - 30.8), (MICRO_X, 34.3, 129.7),
    (4.0, 34.4, 141.0), (-18.1, 34.4, 141.0),
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


def tray_shelf_top(p) -> float:
    """棚の天面 z。**左右で同じ。**

    D-021 では -X 側だけ 2.5 mm 高くしてポカヨケにしていたが、**そこにはもう
    Pi の下端が来る**（幅 76.9 の Pi が棚の x 範囲まで届く）。段は
    `tray_hook_bottom` へ移した（D-023）。**だから sign を取らない** ——
    昔の呼び出しが残っていたら、ここで TypeError になって気づける。
    """
    return p["tray_z0"]


def tray_edge_top(p, sign) -> float:
    """トレーの縁の上端 z。**-X 側だけ tray_key_step ぶん低い**（ポカヨケ）."""
    return p["tray_z1"] - (p["tray_key_step"] if sign < 0 else 0.0)


def tray_hook_bottom(p, sign) -> float:
    """天井から吊ったフックの下面 z。縁の上端 + 遊び（**左右で段が付く**）."""
    return tray_edge_top(p, sign) + p["tray_lift"]


def tray_x_out(p) -> float:
    """トレーの左右の端。位置決めリップから gap だけ逃がす.

    **背面の開口より内側**でなければ、そもそも箱に入らない。
    """
    return p["tray_lip_x"] - p["tray_gap"]


def back_opening_x(p) -> float:
    """背面の開口の半幅。**リムの段のぶん側壁より内側**（トレーはここを通る）."""
    return p["width"] / 2 - WALL - p["rim_step"]


def _tray_receiver(p, f):
    """基板トレーの受け = 棚 + 位置決めリップ + 前の当たり + 天井から吊るフック.

    **2 度目の作り直し（D-023）。** 側壁から内側へ伸ばす C チャンネル（D-021）は、
    CSI レスキューを付けた Pi（幅 76.9）と x を奪い合って成立しない。
    +Z の押さえだけを**天井から吊る**ことで、x の予算を使わずに解いた。

    棚の天面には**クリック止めの切り欠き**（45 度フランク）を彫ってある。
    """
    xw = p["width"] / 2 - WALL                   # 41.0
    y0 = p["tray_y0"] - p["tray_stop_t"]
    y1 = Y_CAVITY_1
    z_shelf = tray_shelf_top(p)
    ceil_z = p["height"] - WALL                  # 天井の内面

    def blk(xa, xb, ya, yb, za, zb):
        lo, hi = min(xa, xb), max(xa, xb)
        return cq.Solid.makeBox(hi - lo, yb - ya, zb - za, cq.Vector(lo, ya, za))

    parts = []
    for sign in (-1, 1):
        xi = sign * p["tray_seat_x"]              # ±34.5
        xl = sign * p["tray_lip_x"]               # ±39.25
        parts.append(blk(xi, sign * xw, y0, y1,
                         z_shelf - p["tray_ledge_t"], z_shelf))          # 棚
        parts.append(blk(xl, sign * xw, y0, y1,
                         z_shelf, z_shelf + p["tray_lip_h"]))            # リップ
        parts.append(blk(xi, sign * xw, y0, p["tray_y0"],
                         z_shelf, tray_edge_top(p, sign)))               # 前の当たり
        # 天井から吊るフック（**x は柱の間。z は Pi の上端より上**）
        h0, h1 = p["tray_hook_x"]
        parts.append(blk(sign * h0, sign * h1, y0, y1,
                         tray_hook_bottom(p, sign), ceil_z))
    seat = parts[0]
    for q in parts[1:]:
        seat = seat.fuse(q)
    seat = seat.clean()

    # クリック止めの切り欠き（棚の天面。y-z 平面の台形を x 方向に押し出す）
    h = p["detent_h"]
    ya, yb = p["detent_y0"], p["detent_y0"] + p["detent_w"]
    pts = [(ya, z_shelf + 0.1), (ya + h, z_shelf - h),
           (yb - h, z_shelf - h), (yb, z_shelf + 0.1)]
    notch = (
        cq.Workplane("YZ").polyline(pts).close()
        .extrude(2 * xw).translate((-xw, 0, 0))
    )
    return cq.Workplane("XY").newObject([seat]).cut(notch)


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
    # トレーの受け。**柱との間に残る肉が薄い**ので宣言して見張る。
    # 棚・リップ・当たりは接するのが正しいので側ごとに 1 個の claim にまとめる
    # （docs/AGENTS.md §4.5）。中の空間もトレーの所有物なので claim に含める。
    for sign in (-1, 1):
        s_ = "p" if sign > 0 else "n"
        x0 = sign * p["tray_seat_x"]
        x1 = sign * (p["width"] / 2 - WALL)
        yc = (p["tray_y0"] - p["tray_stop_t"] + Y_CAVITY_1) / 2
        yl = Y_CAVITY_1 - p["tray_y0"] + p["tray_stop_t"]
        out.append(feature.box(
            f"tray_seat_{s_}", ((x0 + x1) / 2, yc), (abs(x1 - x0), yl),
            p["tray_z0"] - p["tray_ledge_t"],
            p["tray_z0"] + p["tray_lip_h"],
            margin=m, note="基板トレーの棚・位置決めリップ・前の当たり"))
        h0, h1 = p["tray_hook_x"]
        out.append(feature.box(
            f"tray_hook_{s_}", (sign * (h0 + h1) / 2, yc), (h1 - h0, yl),
            tray_hook_bottom(p, sign), p["height"] - WALL,
            margin=m, note="天井から吊る +Z の押さえ（ポカヨケの段つき）"))
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

    # --- 内部: 基板トレーの受け（棚 + リップ + 当たり + 天井から吊るフック） ---
    part = part.union(_tray_receiver(p, f))

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
