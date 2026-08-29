"""ヒートセット下穴クーポン — M4 / M5 の下穴径を実機で決める小片.

想定する取り付け方: 取り付けない。**印刷してインサートを圧入するだけ**の試験片。
P1S / ASA / 0.4 mm ノズル / 0.2 mm 層 / 平置きで刷る前提。

## なぜ要るか

`camera_unit` の蓋の柱の下穴は **M4 = 5.4 / M5 = 6.4**（D-024）。これは 2026-08-25 に
実測したインサート外径（M4 5.9 / M5 6.9）から **「外径 − 0.5」という一般則**で出した
値であって、**このプリンタとこの ASA で実際に圧入して確かめてはいない。**

外すと **本体の柱 6 本が全部駄目になる。** `camera_unit` は 10〜14 時間の印刷なので、
下穴を 0.2 mm 読み違えただけでその全部が捨てになる。**先に 50 分の小片で確かめる。**

外し方は 2 方向あり、症状が違う:

  - **細すぎる**: 溶けた樹脂の行き場が無く、柱が膨らむか**割れる**。
    旧値 5.0 を捨てた理由がこれ（D-024）。
  - **太すぎる**: インサートが空回りして保持トルクが出ない。
    **そして太い側は取り返しがつかない**（樹脂は戻らない）。細い側はドリルで広げられる。

だから帯は **狙い値を挟んで ±0.2**（5.2 / 5.4 / 5.6 と 6.2 / 6.4 / 6.6）に取ってある。

## `fit_coupon_v2` を流用しない理由

  - `heatset_dias = (4.0, 4.2, 4.4)` で **M3 用**。M4/M5 の帯が無い
  - **`heatset_depth = 6.0` / 板厚 8.0 mm。** M4 インサートは全長 8.0、M5 は 10.0 なので
    **そもそも入らない。** 板を厚くするか座を立てる改造が要る
  - v2 は 170 x 160 mm の大物で、O リング溝もアリ溝も付いている。**今日の午後には長い**

**v2 を触るより専用の小片を起こすほうが速い**と判断した（この docstring がその記録）。

## ★ 本番の柱と同じ条件にしてあること

D-024 の争点は下穴径そのものではなく、**「太った下穴のまわりに肉が残るか」**だった。
`camera_unit` は柱の肉が `min_wall` 1.6 を割ったので `lid_boss_dia` を 8.2 -> 8.8 に
太らせて **肉 1.70** を確保している。**クーポンでもそこを揃えないと試験の意味が薄れる。**

| | `camera_unit` の柱 | このクーポンの座 |
|---|---|---|
| 形 | φboss の中実円柱に止まり穴 (`_post`) | 同じ（板の上に立てた円柱） |
| 肉 = (boss − pilot)/2 | **1.70**（M4/M5 とも） | **1.70**（6 本とも。`POST_WALL`） |
| 下穴の深さ | `lid_pilot_depth` **14.0** | 同じ 14.0 |
| 下穴の底 | 止まり。前側に `min_wall` を残す | 止まり。板 3.0 mm が底 |
| 造形時の柱の向き | **鉛直**（後述） | **鉛直**（板から立つ） |

**肉を 1.70 に固定したまま下穴径だけを振る**ので、割れたときに
「下穴が細すぎた」以外の説明が立たない。boss 径は下穴に連動して太る
（5.2 -> 8.6 / 5.4 -> 8.8 / 5.6 -> 9.0 / 6.2 -> 9.6 / 6.4 -> 9.8 / 6.6 -> 10.0）。
このうち **5.4 -> 8.8 と 6.4 -> 9.8 は `camera_unit` の現行値そのもの**である。

### 造形時の向きが本番と一致している（偶然ではない）

`camera_unit` の造形姿勢は `rotate(90, 0, 0)` で、**設計 Y が造形 Z になる。**
柱は `_post` が Y 方向に伸ばすので、**本番でも柱は鉛直に積層される。**
このクーポンは平置きで板から柱を立てるので、**層の向きが本番と同じ**になる。
圧入は溶かした樹脂を層間に流す作業なので、ここがずれると試験の意味が落ちる。

## 補正テーブルについて（副産物）

`ASA_P1S` の HOLE 規則は **[2.0, 5.0) が +0.25（暫定）** と **[8.0, ∞) が +0.30** で、
**φ5 〜 φ8 に実測点が無い**（`fit_coupon_v2` の「未確定事項」に挙がっている穴）。
5.2〜6.6 はその空白に入るので、いま効いているのは **[2.0, 5.0) の外挿**である。
`camera_unit` の 5.4 / 6.4 も同じ外挿を踏んでいる。

**このクーポンを刷って下穴の実測値を書き戻せば、その空白が 6 点で埋まる。**
圧入の合否とは別に、**ノギスで 6 本の穴径を測って記録すること**（下の「測ること」）。

## 測ること（刷ったあと）

1. **圧入する前に**、6 本の下穴の内径をノギスで測って記録する（補正テーブル用）。
2. インサートをはんだごてで圧入する。**各 1 本で足りる**（M4 x3 / M5 x3）。
3. 見るのは 3 つ:
   - **座が割れていないか**（細すぎ側の症状）
   - **インサートが面一まで沈むか、天面から樹脂が盛り上がっていないか**
   - **空回りしないか**（太すぎ側の症状）。ねじを入れて手で緩めてみる
4. **合格した中で一番細いもの**を採る。D-024 の「迷ったら小さい方」と同じ判断軸
   （細ければドリルで広げられるが、太いと樹脂が戻らない）。

## 書き戻す先

  - 採用値 -> `camera_unit.PARAMS["lid_screw_dia"] / ["lid_big_screw_dia"]`
    と、それに連動する `lid_boss_dia` / `lid_big_boss_dia`（**肉 1.70 を保つ**）
  - 判断の記録 -> `docs/DECISIONS.md` に **D-024 の追記**として（新しい D 番号ではなく、
    D-024 が「実測で確かめた」状態になる）
  - 穴径の実測 -> `harness/fit.py` の `ASA_P1S` に **HOLE [5.0, 8.0) の規則**を足す。
    導出は `designs/wildlife_cam/fit_coupon.md` の手順に倣う

## 印刷時間の目安

**約 50 分**（P1S / ASA / 0.4 mm ノズル / 0.2 mm 層 / 平置き / **サポート無し**）。
外形 128 x 46 x 17 mm、体積は約 21 cm3 で、うち 18 cm3 は板。板は 15 層、座は 70 層。
**指示された 30 分〜1 時間の枠に収めるため**、板は必要最小限にしてあり、
装飾は刻印だけにしてある。

板がこの大きさになったのは **刻印が決めている**（`_label_shape` 参照）。
座 6 本だけならピッチ 12 mm・板 80 mm で足りるが、`wall` を通すために刻印を
size 10 にすると "5.2" が 14.1 mm 幅になり、**さらに隣のラベルと読み分けるための
隙間**が要るので、ピッチが 21 mm になった。**ここは削れる余地がある** —— 刻印を
1 文字（下 1 桁）にして帯の見出しを別に彫れば 80 x 40 まで縮む。
今回は**現物の前で 5.2 / 6.4 とそのまま読めること**を優先した。

## 意図して入れていないもの

  - **通し穴・O リング溝・薄板・アリ溝** — `fit_coupon` v1/v2 で済んでいる
  - **インサートを圧入した状態でのねじ引き抜き試験** — 治具が要る。ここでは
    「割れない・沈む・空回りしない」の 3 つだけを見る
  - **サポート** — 板から鉛直に立つ座しか無いので張り出しが出ない

### SKIP するチェックの理由（`docs/AGENTS.md` §6: 判断を docstring に書くこと）

  - **`clearance`** — `COMPONENTS` は空。**内蔵する部品が無い**（試験片であって
    筐体ではない）。ヒートセットは圧入する消耗品で、形として干渉を見る相手ではない
  - **`seal`** — `SEAL_SPANS` 未宣言。**合わせ面が無い。** 1 枚の板で、
    防水も締結もしない
  - **`captive`** — `CAPTIVE_SCREWS` 未宣言。**現地で外すねじが無い。**
    この部品は現地へ行かない（卓上で圧入して捨てる）
  - **`underside`** — `UNDER_BOARD` 未宣言。**基板を載せない。**
  - **`fov`** — `VIEW_CONES` 未宣言。視野を持たない

**`fit` が WARN になるのは正常。** 下穴 5.2〜6.6 が `ASA_P1S` の空白帯
（φ5〜φ8）に入るため「外挿」として 6 件出る。`camera_unit` も同じ理由で WARN で、
**その空白を埋めるのがこのクーポンの副産物**である（上の「補正テーブルについて」）。
"""

import cadquery as cq

from harness import feature, fit

DESIGN_NAME = "insert_coupon"

#: 2026-08-22 に fit_coupon v1 を実測して起こしたテーブル。素性は harness/fit.py。
FIT_TABLE = fit.ASA_P1S

#: **`camera_unit` の柱の肉。** (lid_boss_dia 8.8 − lid_screw_dia 5.4) / 2 = 1.70。
#: D-024 で `min_wall` 1.6 を割らないように 8.2 -> 8.8 と太らせて確保した値。
#: **クーポンの座もこれに揃える**（揃えないと「割れた理由」が下穴径に帰せない）。
#: tests/test_insert_coupon.py が camera_unit の実値と毎回突き合わせる。
POST_WALL = 1.70

#: **`camera_unit.PARAMS["lid_pilot_depth"]` と同じ。** M5 インサートの実測全長 10.0 +
#: 先端の逃げ 4.0。M4 は 8.0 + 逃げ 6.0 になるだけで、どちらも底を突かない（D-024）。
PILOT_DEPTH = 14.0

PARAMS = {
    # --- 台座 ---
    # 座 6 本が並ぶだけの最小の板。厚み 3.0 は止まり穴の底（min_wall 1.6 の倍近い）。
    "plate_l": 128.0,
    "plate_w": 46.0,
    "plate_t": 3.0,
    # --- 下穴の帯（狙い寸法） ---
    # 狙い値 5.4 / 6.4 を挟んで ±0.2。刻みは 0.2（ノギスで有意に読める最小）。
    "m4_pilots": (5.2, 5.4, 5.6),
    "m5_pilots": (6.2, 6.4, 6.6),
    # 座は 6 本を 1 列に並べる。M4 帯 -> M5 帯の順。
    # **ピッチ 21 は座ではなく刻印が決めている。** size 10 の "5.2" は 14.1 mm 幅で、
    # ピッチ 17 だとラベル間の隙間 2.9 mm が**字間 1.8 mm とほとんど変わらず**、
    # 現物では "5.25.45.66.2..." と地続きに読めてしまう（レンダで確認した）。
    # 21 にすると隙間 6.9 mm で字間の 4 倍近くになり、6 つの塊として読める。
    "post_x0": -52.5,
    "post_pitch": 21.0,
    "post_row_y": 2.0,
    # 座の高さ = 下穴の深さ。穴の底がちょうど板の天面になり、板 3.0 が底肉になる。
    "post_h": PILOT_DEPTH,
    "post_wall": POST_WALL,
    "pilot_depth": PILOT_DEPTH,
    # --- 刻印 ---
    "label_y": -11.0,
    # **size 10.0。** 3 文字の刻印が `wall` の閾値 1.6 を通る下限（`_label_shape` の
    # 実測。size 8 では 1 本ごとの最小が 1.316 mm で足りない）。
    # **閾値を緩める方向では逃げていない** — 緩めると座の肉 1.70 を本番と同じ
    # 厳しさで見られなくなり、このクーポンの主目的が薄まる。
    "label_size": 10.0,
    # 表題は **記号を入れず 1 語**。"M4 / M5 PILOT" は "/" と隣の字の間が
    # 0.05 mm まで落ちて FAIL した。
    "title": "INSERT",
    "title_size": 10.0,
    "title_x": 0.0,
    "title_y": 14.5,
    "label_depth": 0.6,
    # --- layout チェック用 ---
    "feature_margin": 0.8,
    "min_wall": 1.6,
}

#: 平置き。**板の裏がプレート、座は鉛直に立つ。**
#: `camera_unit` は rotate(90,0,0) で設計 Y が造形 Z になるため、`_post` が Y に
#: 伸ばす柱は**本番でも鉛直**。層の向きが一致している（docstring 参照）。
PRINT_ORIENTATION = {"rotate": (0, 0, 0)}

COMPONENTS = []


# --- フィーチャの位置（build と features が同じ関数を使う） ------------------


def post_specs(p=PARAMS):
    """(名前, x, 下穴径, boss 径, ラベル) の一覧.

    **boss 径は下穴に連動して太る。** 肉 = post_wall を 6 本とも一定に保つため。
    """
    out = []
    pilots = list(p["m4_pilots"]) + list(p["m5_pilots"])
    for i, pilot in enumerate(pilots):
        boss = pilot + 2 * p["post_wall"]
        out.append((
            f"post_{pilot:.1f}",
            p["post_x0"] + i * p["post_pitch"],
            pilot,
            boss,
                f"{pilot:.1f}",
        ))
    return out


def label_specs(p=PARAMS):
    out = [
        (f"label_{name}", text, x, p["label_y"], p["label_size"])
        for name, x, _pilot, _boss, text in post_specs(p)
    ]
    out.append(("label_title", p["title"], p["title_x"], p["title_y"], p["title_size"]))
    return out


def _label_shape(text: str, x: float, y: float, size: float, p: dict) -> cq.Workplane:
    """刻印を板の天面に彫り込む。**文字サイズは 10.0 以上にすること.**

    `wall` は刻印の画の間に残る肉も測る。**その肉は文字サイズにほぼ比例する。**
    板 1 枚に "5.2" を 1 個だけ彫って、レイ 1 本ごとの最小値を実測した:

        size 6 -> 0.985 mm / size 8 -> 1.316 / size 10 -> 1.643 / size 12 -> 1.970

    **閾値 1.6 を全部のレイが超えるのは size 10 から。** 字数を減らしても効かない
    （"52" の size 8 は 1.352 で、"5.2" の 1.316 とほぼ同じ）ので、
    **効いているのは小数点ではなく字そのものの太さ**である。

    > size 8 は 1 個だけ彫ったときは PASS に見える。`wall` の判定は
    > `min_samples`（既定 5 本）以上が下回った厚みで出すので、刻印が 1 個だと
    > 下回るレイが 5 本に届かないだけである。**このクーポンは刻印が 7 個**あるので
    > 素通しされない。判定に使う値と 1 本ごとの最小値は report に併記される。

    記号の混ざった長い語も避けている: 表題を "M4 / M5 PILOT" にしたときは
    "/" と隣の字の間が 0.05 mm まで落ちて FAIL した。**"INSERT" の 1 語に留めてある。**
    """
    return (
        cq.Workplane("XY")
        .text(text, size, p["label_depth"] + 1.0, combine=False)
        .translate((x, y, p["plate_t"] - p["label_depth"]))
    )


# --- 期待する開口 ----------------------------------------------------------

#: **貫通は 1 つも無い。** 下穴は全部止まり（板 3.0 mm が底）。
#: ここが空でないと出たら、下穴が板を突き抜けている。
def _expected_openings(p):
    return []


CHECK_CONFIG = {
    # **`camera_unit` と同じ 1.6。** クーポンの座の肉 1.70 が本番と同じ余裕で
    # 通ることを、同じ閾値で確かめる（緩めたら試験の意味が無い）。
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 0.6,
    "openings_match_tol_mm": 0.05,
    "expected_openings": _expected_openings(PARAMS),
}


# --- 占有領域の宣言 --------------------------------------------------------


def features(p=PARAMS):
    m = p["feature_margin"]
    top = p["plate_t"] + p["post_h"]
    out = []

    for name, x, pilot, boss, _text in post_specs(p):
        # claim は「所有すべき材料領域」。板から立つ座は**足元の板を厚み方向
        # いっぱいまで**claim する（harness/feature.py の規約）。
        out.append(feature.cylinder(
            name, (x, p["post_row_y"]), boss, 0.0, top, margin=m,
            note=f"ヒートセットの座（下穴 φ{pilot:.1f} / 肉 {p['post_wall']:.2f}）",
        ))

    for name, text, x, y, size in label_specs(p):
        out.append(feature.from_shape(
            name, _label_shape(text, x, y, size, p), margin=m,
            z0=p["plate_t"] - p["label_depth"], z1=p["plate_t"], note="刻印",
        ))
    return out


# --- 形状 ------------------------------------------------------------------


def build(p=PARAMS):
    """PARAMS は狙い寸法。図面寸法への変換は FIT_TABLE がまとめて行う."""
    f = FIT_TABLE

    plate = cq.Workplane("XY").box(
        p["plate_l"], p["plate_w"], p["plate_t"], centered=(True, True, False)
    )

    adds = cq.Workplane("XY")
    cuts = cq.Workplane("XY")

    for _name, x, pilot, boss, _text in post_specs(p):
        adds = adds.union(
            cq.Workplane("XY")
            .circle(f.boss(boss) / 2)
            .extrude(p["post_h"])
            .translate((x, p["post_row_y"], p["plate_t"]))
        )
        # 止まり穴。天面から pilot_depth だけ彫るので、底はちょうど板の天面。
        # **貫通させない**（貫通すると圧入時に樹脂が下へ逃げて条件が変わる）。
        cuts = cuts.union(
            cq.Workplane("XY")
            .circle(f.hole(pilot) / 2)
            .extrude(p["pilot_depth"])
            .translate((x, p["post_row_y"],
                        p["plate_t"] + p["post_h"] - p["pilot_depth"]))
        )

    for _name, text, x, y, size in label_specs(p):
        cuts = cuts.union(_label_shape(text, x, y, size, p))

    # 座を足してから穴と刻印を抜く。座の中の下穴を彫るので順序はこちら。
    return plate.union(adds).cut(cuts)
