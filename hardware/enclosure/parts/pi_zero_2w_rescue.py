"""Raspberry Pi Zero 2 W **＋ CSI レスキューブラケットを装着した状態**（実装済みアセンブリ）.

`parts/pi_zero_2w.py` は裸の Pi である。**カメラの CSI コネクタのラッチが壊れた個体を
救うためのレスキューブラケット**（双葉数理技術「Camera Connector Rescue」の
コネクタ型固定パーツ + CLAMP）を付けると、**Pi の外形そのものが変わる。**
筐体側はもう裸の Pi を相手にできないので、**「Pi ＋ ブラケット」を 1 つの部品**として
ここに立てる。`designs/wildlife_cam/pcb_tray.py` はこの部品を相手にする。

## ★ これが本当の要点: ブラケットは Pi の取付穴 2 個を占有している

レスキューの「コネクタ型固定パーツ」の**耳のねじ穴ピッチは 23.0 mm** で、これは
**Raspberry Pi の取付穴ピッチ 58 x 23 の短辺側と同じ**である。つまり

    ブラケットは **CSI 側の取付穴 2 個を使って基板に留まっている。**

一方 `docs/pcb-tray.md`（D-021）のトレーは **M2.5 x 4 本で Pi を留める**設計だった。
**同じ穴を 2 つの部品が要求しているので、そのままでは両立しない。**
どう解いたか（**共締め**）は `docs/DECISIONS.md` **D-022** と
`designs/wildlife_cam/pcb_tray.py` の docstring。

## 座標

`parts/pi_zero_2w.py` と**同じ**。

    原点 = PCB 中心 / **PCB 上面が z = 0**（部品は +z 側）
    +X  = **CSI 側の短辺**（＝ ブラケットが張り出す向き）。microSD は -X 側
    -Y  = コネクタ長辺（mini-HDMI / micro-USB x 2 が並ぶ辺）

## ★ もう 1 つの要点: 裏に出ているのは「バー」ではなく **ナット**

2026-08-23 の実測（写真 2 枚で確認）で、**基板下面から 2.7 mm 出ているのは
CSI 側の取付穴 2 か所の真下**だと分かった。上から

    ねじ頭 -> 耳 -> 基板 -> **ナット**（高さ 2.0）-> ねじ先の突き出し 約 0.7

**この 2.7 mm は「組んだ状態を定盤に伏せて置いて測った最深部」**なので、
**アセンブリ全体の下面の下限**でもある（基板の外に張り出したバーを含む）。
だから受け側は「2.7 + クリアランス」だけ空ければ、**バーの下がり量を測らなくても済む。**

この事実の帰結が 2 つある。

  1. **共締めは成立しない。** ねじの裏はナットで塞がっていて、トレー側から
     同じ穴を使う道が無い。Pi の保持は **microSD 側の取付穴 2 本だけ**になる
     （残る自由度と、それをどう止めたかは `designs/wildlife_cam/pcb_tray.py`）
  2. **`parts/pi_zero_2w.CAN_SIT_FLAT = True` は、この部品では成り立たない。**
     下の `CAN_SIT_FLAT` はベタ書きせず **`RESCUE_BOT_H` から計算**してある

## 未確定事項

`DIM_SOURCE = "measured:2026-08-23"`（**8 個のうち 6 個が実測**）。
残る 2 個と、実測ではあるが解釈に注意が要るものを列挙する。

  - **`RESCUE_Y_POS` は未実測。** 人間の回答（72.8）が基板の Y 30.0 と矛盾したため
    無効。**「Y 方向は中央、片側 0.6 mm ずつ」を推定として置いてある。**
    効くのは**バーの逃げの Y 範囲だけ**で、ナットのポケットは基板の設計値
    （各辺から 3.5 / ピッチ 23.0）で決まるので、これが無くても引ける
  - **`NUT_AF`（ナットの二面幅）は未実測。** M2.5 用ナットの標準 5.0 を推定で置いた
  - `RESCUE_SCREW_HEAD` は**定義の読み替えが入っている**（その行のコメント）
  - `RESCUE_BOT_H` の内訳（ナット 2.0 + ねじ先 0.7）は**推定**。合計 2.7 が実測値
"""

from __future__ import annotations

import cadquery as cq

from harness.component import make_component
from parts import pi_zero_2w as pi

#: 8 個のうち 6 個が実測。**残りは各行の「推定」を読むこと。**
DIM_SOURCE = "measured:2026-08-23"

# 裸の Pi 側は pi_zero_2w からそのまま引く（**二重に持たない**）
PCB_L = pi.PCB_L          # 65.0  datasheet
PCB_W = pi.PCB_W          # 30.0  datasheet
PCB_T = pi.PCB_T          # 1.0   datasheet（実測時のメモは 1.4。datasheet 側を採る）
HOLE_INSET = pi.HOLE_INSET        # 3.5  datasheet
HOLE_PITCH_Y = pi.HOLE_PITCH_Y    # 23.0 datasheet
TOP_COMP_H = pi.TOP_COMP_H  # 8.8  実測 2026-08-22（GPIO 40 ピンヘッダのピン先）
BOT_COMP_H = pi.BOT_COMP_H  # 0.4  実測 2026-08-22

#: **microSD カードが基板の端から飛び出す量。** 裸の Pi でも同じだが、
#: **筐体に入るかどうかを決めるのはこちら側**なので、ここで明示して引き回す。
#: D-018 でカードは現地で抜かないと決めてあるので、**挿したままの幅で設計する。**
SD_CARD_PROTRUSION = pi.SD_CARD_PROTRUSION   # 4.1  実測 2026-08-22

# =========================================================================
# ★ 人間が測って埋める 8 個。**実測値をそのまま代入できる形にしてある**
# =========================================================================

#: 組んだ状態の全長。**microSD 側の基板端**（カードの突出部ではない）->
#: ブラケットの最も出た端。実測 2026-08-23。
RESCUE_OVERALL_X = 72.8      # 実測 2026-08-23

#: 導出: 基板の CSI 側短辺より外へ張り出す量。
RESCUE_OVERHANG_X = RESCUE_OVERALL_X - PCB_L      # 計算値: 72.8 - 65.0 = 7.8

#: 基板上面 -> ブラケット最上面（**ねじ頭を含む**）。実測 2026-08-23。
#: GPIO ヘッダの 8.8 より低いので、**上側の厚み予算には効かない。**
RESCUE_TOP_H = 6.2           # 実測 2026-08-23

#: 基板**下面**より下への最深部。実測 2026-08-23（定盤に伏せて置いて測った）。
#: **場所は CSI 側の取付穴 2 か所の真下**（ナット + ねじ先）であって、基板の外ではない。
#: 定盤法で測っているので、**アセンブリ全体の下限**でもある — つまり基板の外に
#: 張り出したバーもこれより下には出ない。**受け側はこれだけ空ければ足りる。**
RESCUE_BOT_H = 2.7           # 実測 2026-08-23

#: そのうちナットの高さ。実測 2026-08-23。残り 0.7 はねじ先の突き出し（推定）。
RESCUE_NUT_H = 2.0           # 実測 2026-08-23

#: ナットの二面幅。**推定（要実測）**。M2.5 用六角ナット（JIS B 1181）の標準値。
#: 受け側のポケットはこれで決まるので、**測ったら pcb_tray を回し直すこと。**
NUT_AF = 5.0                 # 推定（要実測）

#: ブラケットの Y 方向の幅。実測 2026-08-23（基板は 30.0）。
RESCUE_Y_W = 28.8            # 実測 2026-08-23

#: 基板の長辺（HDMI/USB 側 = -Y）-> ブラケットの Y- 端。
#: **未実測。** 人間の回答が 72.8（全長と同じ値）で基板の Y 30.0 と矛盾したため無効。
#: 推定 0.6 = (30.0 - 28.8) / 2 —— 「Y 方向は中央」という仮定を置いているだけ。
#: **効くのはバーの逃げの Y 範囲だけ**（ナットのポケットは基板の設計値で決まる）。
RESCUE_Y_POS = 0.6           # 推定（要実測）

#: 耳のねじ頭が**基板上面から**出る高さ。
#: **定義の読み替えが入っている。** 人間が測った 0.5 は「ねじ頭が**ブラケット上面**から
#: 出る量」で、基準面がこの定数の定義（基板上面）と違う。ねじ頭が最上面なので、
#: 基板上面から測れば `RESCUE_TOP_H` そのものになる。生値は下の SCREW_ABOVE_BRACKET。
RESCUE_SCREW_HEAD = RESCUE_TOP_H     # 導出（生値は SCREW_ABOVE_BRACKET = 0.5）

#: 生値。ねじ頭がブラケット上面から出る量。実測 2026-08-23（**要確認**: 解釈）。
SCREW_ABOVE_BRACKET = 0.5    # 実測 2026-08-23

#: 付属ねじの首下長さ。実測 2026-08-23。
SCREW_LEN = 6.2              # 実測 2026-08-23

#: FFC がコネクタから水平に出るか、基板端で下に折れるか。**確定**（写真で確認）。
#: FFC はバーの上を通り、**基板上面とほぼ同じ高さで水平に +X へ出る。**
FFC_EXIT = "horizontal"      # 確定 2026-08-23

#: FFC の静的曲げ半径の下限（一般値）。**筐体側で 90 度曲げるときに効く。**
FFC_BEND_R_MIN = 3.0         # 一般値（22P 0.5mm FFC。厚み 0.30 の 10 倍）

# =========================================================================
# 上の実測から出る性質
# =========================================================================

#: **裸の Pi は `pi_zero_2w.CAN_SIT_FLAT = True`（下面 0.4 でほぼ面一）だが、
#: ブラケットを付けた状態では成り立たない。** 真偽値をベタ書きせず計算で出す
#: —— `RESCUE_BOT_H` を 0.0 に差し替えた瞬間に True へ戻る形にしておくのが要点。
CAN_SIT_FLAT = bool(pi.CAN_SIT_FLAT and RESCUE_BOT_H <= 0.0)

#: 平面に置いたとき基板下面が浮く高さ（べた置きできるなら 0）。
SIT_STANDOFF = 0.0 if CAN_SIT_FLAT else RESCUE_BOT_H

#: **受け面に要る逃げの深さ。** `pcb_tray` はこれを見てボスの高さとポケットを決める。
RELIEF_DEPTH = SIT_STANDOFF

#: 未実測 / 要確認の項目。引き継ぎ文書とレポートがそのまま読む。
UNMEASURED = (
    "RESCUE_Y_POS（バーの逃げの Y 範囲にだけ効く）",
    "NUT_AF（ナットの二面幅。ポケットの寸法を決める）",
    "RESCUE_SCREW_HEAD の解釈（生値 SCREW_ABOVE_BRACKET = 0.5 の基準面）",
    "RESCUE_BOT_H 2.7 の内訳（ナット 2.0 + ねじ先 0.7 は推定。合計は実測）",
)

#: **この部品で使えなくなった取付穴。** ブラケットのねじ + ナットが占有している。
#: `pcb_tray` はここを見て「使ってよい穴」を決める（**二重に持たない**）。
OCCUPIED_MOUNT_HOLES = "csi"     # "csi" 側の 2 穴（+X 側）がブラケット専用


def free_hole_positions() -> list[tuple[float, float]]:
    """**トレー側が使ってよい取付穴**（PCB 中心を原点とした (x, y)）.

    ブラケットが CSI 側 (+X) の 2 穴を占有しているので、**microSD 側の 2 穴だけ**。
    """
    return [(x, y) for x, y in pi.hole_positions() if x < 0]


def nut_positions() -> list[tuple[float, float]]:
    """**基板の裏に出ているナット 2 個**の中心 (x, y)（PCB 中心を原点）.

    ブラケットが占有した CSI 側 (+X) の取付穴の真下。
    位置は **Pi の機構図の値**（各辺から 3.5 / ピッチ 23.0）で決まるので、
    `RESCUE_Y_POS` が未実測でもここは引ける。
    """
    return [(x, y) for x, y in pi.hole_positions() if x > 0]


def x_min() -> float:
    """microSD 側の基板端（カードの突出は含まない。= 裸の Pi と同じ）."""
    return -PCB_L / 2


def x_max() -> float:
    """ブラケットの最も出た端。**ここが筐体の内寸を決める。**"""
    return -PCB_L / 2 + RESCUE_OVERALL_X


def rigid_x_span() -> tuple[float, float]:
    """**筐体の開口を通さなければならない剛体の X 範囲**（microSD カード込み）.

    カードは D-018 で現地では抜かないと決めてあるので、**挿したままの幅**で見る。
    `x_max() - (x_min() - SD_CARD_PROTRUSION)` = 4.1 + 65.0 + 7.8 = 76.9
    """
    return x_min() - SD_CARD_PROTRUSION, x_max()


def rigid_width() -> float:
    a, b = rigid_x_span()
    return b - a


def bracket_y_span() -> tuple[float, float]:
    """ブラケットの Y 範囲（基板中心を原点）。**RESCUE_Y_POS が推定なので推定。**"""
    y0 = -PCB_W / 2 + RESCUE_Y_POS
    return y0, y0 + RESCUE_Y_W


def bracket_x_span() -> tuple[float, float]:
    """ブラケットの X 範囲（耳の先端 -> バーの先端）.

    耳は CSI 側の取付穴（基板端から 3.5）に載るので、そこから外へ伸びる。
    左端は**耳の先端**で、穴より 3.1（推定）だけ内側。
    """
    hole_x = PCB_L / 2 - HOLE_INSET          # +28.0
    return hole_x - 3.1, x_max()             # 3.1 は推定（要実測）


def ffc_exit_x() -> float:
    """FFC がアセンブリから出る X。**水平に出る**ので、バーの先端そのもの."""
    return x_max()


def model() -> cq.Workplane:
    """裸の Pi にブラケットとナットの塊を足した実体（PCB 上面 z=0、部品は +z）.

    **形はレスキューパーツを再現したものではない。** ここで作るのは
    **筐体設計が相手にすべき外形の塊**である。
    """
    body = pi.model()
    bx0, bx1 = bracket_x_span()
    by0, by1 = bracket_y_span()

    # 基板上面より上（耳・腕・バー・ねじ頭をまとめた塊）
    body = body.union(
        cq.Workplane("XY").newObject([cq.Solid.makeBox(
            bx1 - bx0, by1 - by0, RESCUE_TOP_H, cq.Vector(bx0, by0, 0.0))])) 

    # 基板下面より下（**ナット 2 個 + ねじ先**。ここが 2.7 mm の正体）
    for x, y in nut_positions():
        body = body.union(
            cq.Workplane("XY").newObject([cq.Solid.makeBox(
                NUT_AF, NUT_AF, RESCUE_BOT_H,
                cq.Vector(x - NUT_AF / 2, y - NUT_AF / 2, -PCB_T - RESCUE_BOT_H))]))

    # microSD カード（挿したまま。**筐体の開口を決めるのはここ**）
    body = body.union(
        cq.Workplane("XY").newObject([cq.Solid.makeBox(
            SD_CARD_PROTRUSION, pi.SD_CARD_W, 1.0,
            cq.Vector(x_min() - SD_CARD_PROTRUSION, -pi.SD_CARD_W / 2, -PCB_T))]))
    return body


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """外形 + clearance（**microSD カード込み**）.

    **裸の Pi と違い、+X には「コネクタ抜き差し代」を足さない。**
    CSI 側はブラケットが占めていて、そこにケーブルを挿す作業はもう無い
    （FFC はブラケットで押さえられていて、現地で抜き差ししない）。
    micro-USB / mini-HDMI は -Y の長辺なので、この向きには効かない。
    """
    c = clearance
    x0, x1 = rigid_x_span()
    x0, x1 = x0 - c, x1 + c
    z_lo = -PCB_T - max(BOT_COMP_H, RESCUE_BOT_H) - c
    z_hi = max(TOP_COMP_H, RESCUE_TOP_H) + c
    return cq.Workplane("XY").newObject([cq.Solid.makeBox(
        x1 - x0, PCB_W + 2 * c, z_hi - z_lo, cq.Vector(x0, -PCB_W / 2 - c, z_lo))])


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Pi Zero 2 W + CSI レスキュー", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=("ブラケットが CSI 側の取付穴 2 個をねじ + ナットで占有しているので、"
               "トレーが使えるのは microSD 側の 2 穴だけ。"
               f"未実測 / 要確認: {' / '.join(UNMEASURED)}"),
    )
