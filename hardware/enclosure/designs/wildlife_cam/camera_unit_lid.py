"""wildlife-cam カメラユニット 背面の蓋（鞍つき）.

`camera_unit.py` の本体に被せる蓋。**造形姿勢が本体と違うので別ファイル**にしてある
（本体は開口を上、蓋は平板として寝かせる）。

## この蓋が持つもの

  1. **パッキン溝**（O リング φ2.0 コード / 周回のレーストラック）。
     溝は**蓋側**に彫る。本体側は平らな land にして、開口を広く取るため。
  2. **鞍**（幹の丸みに座る V 溝）。半角 54 度・幅 44・深さ 16。
     直径 48〜64 mm の幹に対して **2 線接触**になり、径が変わっても座りが安定する。
     円弧だと 1 つの径にしか合わない。
  3. **ベルト溝** 2 本。幅 30 mm（何重にも巻ける）、鞍の面よりさらに 3 mm 深い。
     鞍と同じ V の延長なので干渉しない。巻いたベルトが上下にずれない。
  4. **蝶ねじ 6 本の通し穴**と、**シール面側の捕捉ポケット**。
     蓋を外したとき蝶ねじが蓋に付いたまま残る（**落としたら二度と見つからない**）。
     軸に付けた平たいリテーナ（E 形止め輪 か 押しナット）がポケットの天井に
     当たって止まる。寸法の連鎖は `captive` チェックが毎回解く。
     経緯と不採用案は `docs/captive-fasteners.md` / D-020。
     **四隅 4 本では長辺の中央でパッキンが浮く**ことが `seal` チェックで分かり、
     中央（z=142）に 1 対足した。経緯と比較した案は `docs/lid-fastening.md`。
  5. **ポカヨケ**: ねじ 6 本のうち **1 本だけ M5**（他は M4）。
     180 度回すと M5 のねじが M4 のインサートに入らないので、
     **逆向きでは締まらない。** 穴径の違いは目でも分かる。
     さらに**中央の対が z=142 だけ**（上下非対称）なので、逆向きでは穴自体が合わない。
  6. **刻印**: 締める順序 1〜6 と UP。現地に説明書は無い。
     **側面 (x = ±42) に、そのねじと同じ z で彫る。** 鞍の面には置き場所が無く
     （座ぐりとの間に 1.6 mm の肉が残らない / ベルトの下に隠れる）、
     側面なら箱の横から読める。背面は幹に向いているので読めない。

## 座標

  x は左右中央、z は本体と同じ（0 = 下端、190 = 上端）。
  **y = 0 が本体に当たるシール面、+Y が樹の方向。**

## 造形姿勢

```
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}   シール面を下（ビルドプレート）に
```

  - **シール面が第 1 層**になるので、最も平坦で密な面がパッキンに当たる
  - V 溝とベルト溝は**上向きに開く**のでサポートが要らない
  - パッキン溝は下向きに開くが、幅 2.70 のブリッジなので渡せる

## パッキンの面圧（`seal` チェックが毎回検証する）

`SEAL_SPANS` に合わせ面を宣言してある。ハーネスが **build() した形状から
断面二次モーメントを実測**し、パッキンを非線形の弾性床とした梁として解いて、
締結点の間で潰し量がいくつまで落ちるかを出す。式と仮定は `harness/seal.py`、
検討の全体は `docs/lid-fastening.md`。

  6 点（z=12/142/186）で **最小圧縮率 21%**（実効弾性率の係数 0.6 / 70 Shore A）。
  四隅 4 点だと 13.3% で、静的シールの下限 15% を割る。

## 捕捉（`captive` チェックが毎回検証する）

`CAPTIVE_SCREWS` に 6 本を宣言してある。ハーネスが **build() した形状にねじ軸と
平行なレイを飛ばして**ポケットの深さと頭の座面の深さを実測し、

  「落ちない」= リテーナを受ける肉がある
  「抜けきる」= 後退できる量 9.7 mm > 噛み合い 8.0 mm + 余裕
  「平らに座る」= 緩めきったときの出しろ 1.3 mm < 柱までの隙間 3.0 mm

を解く。**ポケットを深くしても面圧はほとんど動かない**（4.5 -> 10.5 mm で
最小圧縮率 20.98% -> 20.97%）。締結点の真上＝たわみが拘束されている場所だから。

**組立**: 蝶ねじを外側から通し、頭を座ぐりに密着させたまま、リテーナを
**シール面と面一になるまで**押し込む（蓋を伏せて平らな台に突き当てればよい）。

## 未設計

  - パッキンの座りが見える段差。`docs/field-procedure.md` の宿題 3
  - **合わせ面の平面度（反り）は計算では出せない。** 実機を定盤に当てて測ること。
    198 mm の ASA の反りは、ここで計算した弾性変形（0.08 mm）より大きくなりうる
"""

import math

import cadquery as cq

from harness import feature, fit, seal
from designs.wildlife_cam import camera_unit
from parts import oring

DESIGN_NAME = "camera_unit_lid"
FIT_TABLE = fit.ASA_P1S

PARAMS = {
    "width": camera_unit.PARAMS["width"],       # 88.0（D-022）
    "height": camera_unit.PARAMS["height"],     # 190.0
    "plate_t": 3.0,
    "saddle_t": 19.0,            # 鞍の肉厚。V の深さ 16 + ベルト溝の 3
    "saddle_depth": 16.0,        # V の深さ
    "saddle_half_angle_deg": 54.0,
    "belt_extra_depth": 3.0,     # 鞍面よりさらに深く彫る量
    "belt_w": 30.0,              # 何重にも巻ける幅
    # ベルトの中心 z。**蝶ねじの座ぐりに掛からない位置に置く**（掛かるとベルトを
    # 外さないと蓋を開けられない）。座ぐりが塞ぐのは z 6.8〜17.3 / 136.8〜147.3 /
    # 180.8〜191.3 なので、上のベルトは 147.3〜180.8 の窓（33.5 mm）に入れる。
    # 下 49.5 / 上 164.3 で支点間 114.8 mm（旧 99 mm より広く、揺れに強い）。
    "belt_z": (49.5, 164.3),
    # パッキン溝（本体の land 中央に合わせる）
    "gasket_w": oring.GROOVE_WIDTH,   # 2.70
    "gasket_d": oring.GROOVE_DEPTH,   # 1.50
    # **本体の側壁の内面に合わせる（二重に持たない）。** 幅 88 化（D-022）で
    # land は x 39.25..44 になった。溝 (中心 ±41.0 / 幅 2.70 -> 39.65..42.35) は
    # その中に収まり、蓋の外縁にも 44 - 42.35 = 1.65 mm 残る（min_wall 1.6）。
    # 内側に残る land は 39.65 - 39.25 = 0.40 mm。
    "gasket_x": camera_unit.PARAMS["width"] / 2 - camera_unit.PARAMS["wall"],
    "gasket_z_margin": 3.0,      # 上下も同じ理由
    # 蝶ねじ
    "screw_dia": 4.5,
    "screw_head_dia": 9.0,
    # 1 本だけ M5（ポカヨケ）。本体の lid_big_index に対応する。
    "big_screw_dia": 5.5,
    "big_head_dia": 10.5,
    "screw_head_depth": 3.0,
    #: **蝶ボルトの頭下長さ。** M4 x 30 / M5 x 30（JIS B 1184 蝶ボルト・国内で普通に買える）。
    #: 蓋を 19 mm 通り、柱まで 3 mm 跳び、インサートに 8 mm 噛む（= 呼び径の 2 倍）。
    #: 25 mm でも成立するが噛み合いが 3 mm しか取れない（`docs/captive-fasteners.md` §5）。
    "screw_len": 30.0,           # 設計値（市販の呼び長さ）
    "big_screw_len": 30.0,       # 設計値
    #: **捕捉のリテーナ = ナイロンナットをねじ込む**（D-026 で確定）。
    #: 液体のねじロック剤ではなく**プリベリングトルク形のナット**を使う。
    #: 現地で何度も開け閉めするので、**再締結のたびに効きが落ちる液体は使えない。**
    #:
    #: **2026-08-25 訂正: 旧記述「E 形止め輪 呼び4 / 呼び5」は誤りだった。**
    #: E 形止め輪の**「呼び」は軸径ではなく溝径**で、JIS の適用軸径は
    #: 呼び3 = 4〜5 / 呼び4 = 5〜7。**呼び4 は M4(φ4) の軸には使えない。**
    #: 正しく引くと M4 -> 呼び3（外径 7.0）/ M5 -> 呼び4（外径 9.0）になるが、
    #: **どちらも軸に溝（φ3.0 / φ4.0）を削る必要があり、旋盤が要る。**
    #: 押しナット（SPN-4/5）は加工不要だが外径 12/14 と大きく、
    #: **`wall` が 0.286 mm まで落ちて成立しない**（実際に回して確認した）。
    #:
    #: 残ったのがナット。**対角の最小値**で取る（穴を確実に塞ぐ側）。
    #: 対辺はナイロンナットも六角ナットも同じで M4 = 7.0 / M5 = 8.0。
    #: JIS B 1181 の対角の最小値は M4 = 7.66 / M5 = 8.79。
    "retainer_od": 7.7,          # JIS B 1181 M4 六角ナットの対角（最小 7.66）
    "big_retainer_od": 8.9,      # JIS B 1181 M5 六角ナットの対角（最小 8.79）
    "retainer_clear": 0.8,       # ポケット径 = 外径 + これ（半径 0.4 の逃げ）
    #: リテーナの厚み。**そのぶん後退できる量が減る**ので効く。
    #: **ナイロンナット 1種**（JIS B 1199-1 / DIN 982 相当）の高さ:
    #: M4 = 5.5 / M5 = 6.0。**最悪値の 6.0 を全数に当てる**（D-026）。
    "retainer_t": 6.0,           # ナイロンナット 1種 M5 の高さ（M4 は 5.5。厚い側を採る）
    #: **捕捉ポケットの深さ。** ここからリテーナの厚みを引いたものが
    #: 「ねじが後退できる量」になる。噛み合い 8.0 mm を上回らないと、ねじが相手から
    #: 抜けきる前にリテーナが止まって**蓋が開かない**。逆に深すぎると緩めたとき
    #: ねじ先が引っ込みすぎ、蓋を置いたときに柱の穴を探せない。`captive` が毎回解く。
    #: 深さを 4.5 -> 10.5 に変えても `seal` の最小圧縮率は 20.98% -> 20.97% しか
    #: 動かない（ポケットは締結点の真上＝たわみが拘束されている場所にあるため）。
    #: **2026-08-25 に 15.7 へ。** ナイロンナットが厚い（6.0）ぶんを足した（D-026）。
    #: 後退できる量は 15.7 - 6.0 = 9.7 で、噛み合い 8.0 を上回る（`captive` が実測）。
    "retainer_pocket_d": 15.7,   # 設計値（噛み合い 8.0 + リテーナ 6.0 + 余裕 1.7）
    #: 相手（本体の柱）のインサート座面までの隙間と、インサートの有効深さ。
    #: **本体から導出する。二重に持たない。**
    "post_gap": camera_unit.Y_BACK - camera_unit.Y_CAVITY_1,   # 3.0
    "insert_depth": camera_unit.PARAMS["lid_boss_depth"],      # 8.0
    #: 締結点の z（本体の柱から導出する。**二重に持たない**）。
    #: seal チェックの梁モデルが支点として使う。
    #: ネガティブテストはここを 4 点に戻して「FAIL になること」を確かめる。
    "support_z": tuple(sorted({z for _x, z in camera_unit.PARAMS["lid_bosses"]})),
    #: パッキンの硬度と材質。**硬いほど蓋を押し開く力が強い**ので、seal チェックは
    #: この値で判定する。屋外なので UV とオゾンに強い EPDM かシリコーンを使う
    #: （NBR は紫外線で割れる）。70 Shore A は入手しやすい側の上限＝安全側。
    "gasket_shore_a": 70.0,
    "gasket_material": "EPDM / シリコーン",
    "min_wall": 1.6,
    "feature_margin": 0.8,
    "label_size": 6.0,   # size 5 では文字の線幅が min_wall を切る（fit_coupon の実測）
    "label_depth": 0.6,
    #: 刻印は**側面（x = ±42）**に彫る。鞍の面には (1) 座ぐりとの間に 1.6 mm の肉が
    #: 残らない (2) ベルトの下に隠れる、のどちらかになって置き場所が無い。
    #: 側面なら現地で**横から**読めるうえ、ベルト帯 (z 149.3〜179.3) さえ避ければよい。
    "label_face_y": 11.0,   # 側面の高さ 22 の中央
}

#: **`UNDER_BOARD` を宣言しない理由**（`docs/AGENTS.md` §6。考え忘れではない）。
#: 蓋は基板を受けない。載っているのは蝶ねじとパッキンだけである。
UNDER_BOARD: list = []

#: シール面を下にして刷る。第 1 層 = 最も平坦な面がパッキンに当たる。
PRINT_ORIENTATION = {"rotate": (90, 0, 0)}

COMPONENTS = []

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 1.5,
    "openings_match_tol_mm": 0.1,
    "expected_openings": [
        {"diameter_mm": PARAMS["screw_dia"],
         "count": len(camera_unit.PARAMS["lid_bosses"]) - 1,
         "note": "蝶ねじ M4 の通し穴（パッキンの内側なので漏れ経路にならない）"},
        {"diameter_mm": PARAMS["big_screw_dia"], "count": 1,
         "note": "蝶ねじ M5（ポカヨケ。1 本だけ大きい）"},
    ],
}

SECTIONS = [
    {"name": "xy_belt", "origin": (0, 0, 47.5), "normal": (0, 0, -1)},
    {"name": "yz_mid", "origin": (0, 0, 0), "normal": (-1, 0, 0)},
]


def saddle_half_width(depth: float, p=PARAMS) -> float:
    """深さ depth のときの V の開口 半幅."""
    return depth * math.tan(math.radians(p["saddle_half_angle_deg"]))


def trunk_center_height(trunk_dia: float, p=PARAMS) -> float:
    """直径 trunk_dia の幹が V に座ったときの、V の頂点からの中心高さ.

    r / sin(半角)。直径 48〜64 で V の壁の中に接触が収まることの確認に使う。
    """
    return (trunk_dia / 2) / math.sin(math.radians(p["saddle_half_angle_deg"]))


def screw_positions(p=PARAMS):
    return list(camera_unit.PARAMS["lid_bosses"])


def _is_big(i, p=PARAMS) -> bool:
    return i == camera_unit.PARAMS["lid_big_index"]


def screw_dims(i, p=PARAMS) -> dict:
    """ねじ 1 本ぶんの径。**M4 / M5 の分岐をここ 1 箇所にまとめる。**

    build() / features() / CAPTIVE_SCREWS が同じ関数から取るので、
    「片方だけ M5 を忘れる」が起きない。
    """
    big = _is_big(i, p)
    return {
        "thread": p["big_screw_dia"] if big else p["screw_dia"],
        "head": p["big_head_dia"] if big else p["screw_head_dia"],
        "retainer": p["big_retainer_od"] if big else p["retainer_od"],
        "length": p["big_screw_len"] if big else p["screw_len"],
        "pocket": (p["big_retainer_od"] if big else p["retainer_od"])
        + p["retainer_clear"],
    }


def head_seat_depth(p=PARAMS) -> float:
    """シール面から**頭が当たる座面**までの深さ = 通し穴を通る長さ."""
    return p["plate_t"] + p["saddle_t"] - p["screw_head_depth"]


def CAPTIVE_SCREWS(p=PARAMS):
    """`captive` チェックへの申告（`docs/captive-fasteners.md` / D-020）.

    **蓋を外したとき蝶ねじ 6 本が蓋に付いたまま残る**ことを寸法の連鎖で押さえる。
    ポケットの深さと座面の深さは**申告せず、build() した形状から実測させる**
    （宣言と実物がずれないように）。
    """
    from harness.captive import CaptiveScrew

    out = []
    for i, (x, z) in enumerate(screw_positions(p)):
        d = screw_dims(i, p)
        out.append(CaptiveScrew(
            name=f"screw_{i + 1}", at=(x, z), axis="Y",
            thread_dia=d["thread"] - 0.5,      # 通し穴の狙い径 -> 呼び径（M4=4.0）
            head_dia=d["head"], retainer_od=d["retainer"], retainer_t=p["retainer_t"],
            screw_len=d["length"], gap_mm=p["post_gap"],
            insert_depth_mm=p["insert_depth"],
            note=("リテーナはシール面と面一まで押し込む（平らな台に蓋を伏せて突き当てる）。"
                  "止め輪なら首に溝が要るが、同外径の押しナットなら加工不要"),
        ))
    return out


def gasket_path(p=PARAMS):
    """パッキン中心線のレーストラック: (z0, z1, 短辺の長さ, 周長) [mm].

    build() の溝と**同じ式**から出す（二重に数字を持たない）。
    """
    zc = p["height"] / 2
    half_z = p["height"] / 2 - p["gasket_z_margin"]
    z0, z1 = zc - half_z, zc + half_z
    end_run = 2 * p["gasket_x"]
    return z0, z1, end_run, 2 * (z1 - z0) + 2 * end_run


def SEAL_SPANS(p=PARAMS):
    """`seal` チェックへの申告。長辺 2 本を 1 本の梁として解く.

    蓋は z 方向に長い梁で、パッキンの長辺 2 本（x = ±39）が下から押し上げる。
    短辺（z = 3 と 195）は梁の両端の集中荷重になる。締結点では蓋が本体の land に
    密着して止まる（ハードストップ）ので、そこの潰し量は 0.50 mm で頭打ち。
    """
    z0, z1, end_run, _perim = gasket_path(p)
    return [seal.SealSpan(
        name="lid_long_edges",
        z0=z0, z1=z1,
        supports=tuple(float(z) for z in p["support_z"]),
        gasket=seal.Gasket(
            cord_mm=oring.CORD, groove_depth_mm=p["gasket_d"],
            shore_a=p["gasket_shore_a"], lines=2, material=p["gasket_material"]),
        end_run_mm=end_run,
        note=("長辺 2 本 x 192 mm + 短辺 2 本 x 78 mm = 周長 540 mm。"
              "本体側のリムは剛体とみなす（面内で受ける深い壁なので蓋より硬い）"),
    )]


def _v_cutter(depth: float, z0: float, z1: float, p=PARAMS):
    """V 溝の切り抜き。頂点は y = saddle_t + plate_t - depth."""
    y_top = p["plate_t"] + p["saddle_t"]
    y_apex = y_top - depth
    half = saddle_half_width(depth, p)
    pts = [(-half, y_top), (half, y_top), (0.0, y_apex)]
    return (
        cq.Workplane("XY")
        .polyline(pts).close()
        .extrude(z1 - z0)
        .translate((0, 0, z0))
    )


def features(p=PARAMS):
    m = p["feature_margin"]
    y_top = p["plate_t"] + p["saddle_t"]
    out = [
        feature.box(
            "saddle", (0.0, y_top - p["saddle_depth"] / 2),
            (2 * saddle_half_width(p["saddle_depth"], p), p["saddle_depth"]),
            0.0, p["height"], margin=0.0,
            note="鞍の V 溝（ベルト溝を含む）",
        ),
    ]
    for i, (x, z) in enumerate(screw_positions(p)):
        d = screw_dims(i, p)
        # 通し穴・座ぐり・捕捉ポケットは**同軸に積み上がっていて接するのが正しい**
        # ので、ひとつの claim にまとめる（docs/AGENTS.md §4.5）。
        # 径は 3 つのうち最大（＝捕捉ポケット）を取る。
        out.append(feature.cylinder(
            f"screw_{i}", (x, z), max(d["head"], d["pocket"]),
            -0.5, y_top + 0.5,
            margin=m, axis="Y", note="蝶ねじの通し穴・座ぐり・捕捉ポケット",
        ))
    # **パッキン溝の長辺**の claim。捕捉ポケットを彫ったことで、ポケットの縁と
    # 溝の間に残る肉が 1.75 mm しかない。**近づきすぎたら layout に落として欲しい**
    # ので宣言する（margin 0.8 x 2 = 1.6 = min_wall なので、1.6 を切った瞬間に重なる）。
    # 短辺（z = 3 / 195）は宣言していない。**レーストラックは円環では包めず、
    # 長辺と短辺を別々に宣言すると角で必ず重なって誤検出になる**ため。
    # ねじはすべて長辺の近く（|x| = 30〜31）にあり、短辺までは 9 mm 以上あるので
    # 危ないのは長辺の側だけである。
    z0, z1, _end, _per = gasket_path(p)
    for sign in (-1, 1):
        out.append(feature.box(
            f"gasket_long_{'p' if sign > 0 else 'n'}",
            (sign * p["gasket_x"], p["gasket_d"] / 2), (p["gasket_w"], p["gasket_d"]),
            z0, z1, margin=m, note="パッキン溝の長辺（溝は y = 0〜1.5 に彫る）"))
    return out


def build(p=PARAMS):
    f = FIT_TABLE
    y_top = p["plate_t"] + p["saddle_t"]

    plate = cq.Solid.makeBox(
        f.boss(p["width"]), y_top, f.boss(p["height"]),
        cq.Vector(-f.boss(p["width"]) / 2, 0, 0))
    part = cq.Workplane("XY").newObject([plate])

    # 鞍の V 溝（全長）
    part = part.cut(_v_cutter(p["saddle_depth"], -1.0, p["height"] + 1.0, p))

    # ベルト溝（さらに 3 mm 深い V を 2 本）
    for zc in p["belt_z"]:
        part = part.cut(_v_cutter(
            p["saddle_depth"] + p["belt_extra_depth"],
            zc - p["belt_w"] / 2, zc + p["belt_w"] / 2, p))

    # パッキン溝（シール面 y=0 に彫る周回のレーストラック）
    gw = f.uncompensated(p["gasket_w"], "溝幅は未実測")
    gd = f.uncompensated(p["gasket_d"], "溝深さは未実測")
    zc = p["height"] / 2
    half_z = p["height"] / 2 - p["gasket_z_margin"]
    outer = cq.Solid.makeBox(
        2 * p["gasket_x"] + gw, gd + 1, 2 * half_z + gw,
        cq.Vector(-(p["gasket_x"] + gw / 2), -1.0, zc - half_z - gw / 2))
    inner = cq.Solid.makeBox(
        2 * p["gasket_x"] - gw, gd + 2, 2 * half_z - gw,
        cq.Vector(-(p["gasket_x"] - gw / 2), -1.5, zc - half_z + gw / 2))
    part = part.cut(cq.Workplane("XY").newObject([outer.cut(inner)]))

    # 蝶ねじの通し穴 + 頭の座ぐり（外側）+ 捕捉ポケット（シール面側）
    #
    #   y=0 シール面                                        y=22 鞍の面
    #     |<- 捕捉ポケット ->|<---- 通し穴 ---->|<- 座ぐり ->|
    #     φ9.8 / 深さ 4.5      φ4.5              φ9.0 / 3.0
    #
    # **捕捉ポケットは「ねじが後退できる量（逃げ）」を形で決めるためにある。**
    # リテーナ（止め輪 / 押しナット）をシール面と面一まで押し込むと、緩めたときに
    # リテーナがポケットの天井に当たって止まる。その行程が噛み合いより長ければ
    # ねじは相手から抜けきり、短ければ**蓋が開かない**。`captive` が毎回解く。
    #
    # ポケットは**シール面（= 第 1 層）に開く**ので、天井は幅
    # (φ9.8 - φ4.5)/2 = 2.65 mm の環になり、ブリッジで渡せる（サポート不要）。
    # ポケットはパッキン溝の内側にあるので**漏れ経路にはならない**。
    for i, (x, z) in enumerate(screw_positions(p)):
        dd = screw_dims(i, p)
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(dd["thread"]) / 2, y_top + 2,
            cq.Vector(x, -1.0, z), cq.Vector(0, 1, 0))]))
        part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
            f.hole(dd["head"]) / 2, p["screw_head_depth"] + 1,
            cq.Vector(x, y_top - p["screw_head_depth"], z), cq.Vector(0, 1, 0))]))
        if p["retainer_pocket_d"] > 0.01:
            part = part.cut(cq.Workplane("XY").newObject([cq.Solid.makeCylinder(
                f.hole(dd["pocket"]) / 2, p["retainer_pocket_d"] + 1.0,
                cq.Vector(x, -1.0, z), cq.Vector(0, 1, 0))]))

    # 刻印（現地 UX 原則 5）。締める順序を現地で読めるようにする。説明書は現地に無い。
    # **側面に、そのねじと同じ z で彫る。** 鞍の面は座ぐりとベルトで埋まっていて
    # 1.6 mm の肉を残せない。側面なら箱の横から読める（背面は幹に向いている）。
    half_w = f.boss(p["width"]) / 2      # 補正後の側面の位置（彫り込み深さを一定に保つ）
    for i, (x, z) in enumerate(screw_positions(p)):
        part = part.cut(_label(str(i + 1), 1 if x > 0 else -1, z, p, half_w))
    # UP は左右両面の上端近くに。どちら側から近づいても読める。
    for sign in (-1, 1):
        part = part.cut(_label("UP", sign, p["height"] - 4.0, p, half_w))
    return part


def _label(text, sign, z, p, half_w=None):
    """側面 (x = sign * half_w) に彫る刻印。彫り込みは label_depth、外へ 1 mm 逃がす.

    面は YZ 平面（文字の並びが +Y、上が +Z）。
    **+X 側の面は外から見ると +Y が左に来る**ので左右を反転させる。
    （視線 -X / 上 +Z で見ると、見る人の右は Z x (-X) = -Y になる。）
    反転を忘れると現地で鏡文字になる。刻んでしまったら直せない。
    """
    depth = p["label_depth"] + 1.0
    solid = (
        cq.Workplane("YZ")
        .text(text, p["label_size"], depth, combine=False)   # x = 0..depth に立つ
    )
    x_face = sign * (p["width"] / 2 if half_w is None else half_w)
    if sign > 0:
        solid = solid.mirror("XZ")                 # y -> -y（+X 面から読めるように）
        x0 = x_face - p["label_depth"]             # 面から内側へ label_depth だけ食い込む
    else:
        x0 = x_face - 1.0                          # -X 面: 外へ 1 mm 出して内側へ食い込む
    return solid.translate((x0, p["label_face_y"], z))
