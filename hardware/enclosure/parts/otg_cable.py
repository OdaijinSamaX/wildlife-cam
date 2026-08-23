"""micro-USB オス → USB-A メス の OTG ケーブル.

Pi Zero 2 W の micro-USB (OTG) ポートと、SORACOM Onyx の USB-A オスプラグを
つなぐためのケーブル。DIM_SOURCE = "measured:2026-08-22"（ノギス実測）。

| 項目 | 実測 | 備考 |
|---|---|---|
| 全長 | 150.0 mm | コネクタ端から端まで |
| USB-A メス側ハウジング | 35.0 x 16.8 x 10.3 mm | ケーブル保護部を含む |
| micro-USB オス側ハウジング | 30.8 x 9.9 x 6.8 mm | ケーブル保護部を含む |
| コネクタ剛体の合計 | 65.8 mm | 35.0 + 30.8 |
| 有効可動長 | 84.2 mm | 150.0 - 65.8 |

数値は自己整合している（30.8 + 84.2 + 35.0 = 150.0）。

## レイアウト上の意味 — 直列に並べると P1S の造形枠を超える

    Pi Zero 2 W  65.0
    OTG ケーブル 150.0
    SORACOM Onyx  95.0
    -------------------
    合計         310.0 mm   >  P1S の枠 256 mm

**直線に並べる構成は成立しない。折り返し配置が必須。**
折り返せるのは有効可動長 84.2 mm の部分だけで、両端 65.8 mm は剛体なので
曲げられない。U 字に折り返すと、往復ぶんの幅に加えて最小曲げ半径ぶんの
逃げが要る。詳細は docs/AGENTS.md の「内蔵部品の寸法順位」を参照。

## 推定（要実測）

  - ケーブル外径 3.5 mm
  - 最小曲げ半径 15.0 mm（外径の 4 倍強という一般則から）
  - USB-A レセプタクルの奥行き 12.0 mm（USB-A 規格のプラグ挿入長から）
  - ハウジング寸法のうち、金属シェルとケーブル保護部の内訳は測っていない
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "measured:2026-08-22"

TOTAL_L = 150.0        # 実測 2026-08-22

USB_A_L = 35.0         # 実測 2026-08-22（ケーブル保護部を含む）
USB_A_W = 16.8         # 実測 2026-08-22
USB_A_H = 10.3         # 実測 2026-08-22

MICRO_L = 30.8         # 実測 2026-08-22（ケーブル保護部を含む）
MICRO_W = 9.9          # 実測 2026-08-22
MICRO_H = 6.8          # 実測 2026-08-22

RIGID_TOTAL = USB_A_L + MICRO_L        # 65.8 — 曲げられない長さ
FLEX_LENGTH = TOTAL_L - RIGID_TOTAL    # 84.2 — 曲げられる長さ

CABLE_DIA = 3.5        # 推定（要実測）
MIN_BEND_RADIUS = 15.0  # 推定（外径の 4 倍強）
RECEPTACLE_DEPTH = 12.0  # 推定（USB-A 規格のプラグ挿入長）
RECEPTACLE_W = 12.5    # USB Type-A 規格値（プラグ断面）
RECEPTACLE_H = 5.5     # USB Type-A 規格値


def model() -> cq.Workplane:
    """原点 = micro-USB プラグの先端。+X が USB-A レセプタクル方向.

    **これは真っ直ぐに伸ばした姿勢**であって、実装時の形ではない。
    曲げられるのは x = MICRO_L .. TOTAL_L - USB_A_L の区間だけ。
    """
    micro = cq.Workplane("XY").box(
        MICRO_L, MICRO_W, MICRO_H, centered=(False, True, True)
    )
    cable = cq.Solid.makeCylinder(
        CABLE_DIA / 2, FLEX_LENGTH, cq.Vector(MICRO_L, 0, 0), cq.Vector(1, 0, 0)
    )
    usb_a = (
        cq.Workplane("XY")
        .box(USB_A_L, USB_A_W, USB_A_H, centered=(False, True, True))
        .translate((TOTAL_L - USB_A_L, 0, 0))
    )
    part = micro.union(cq.Workplane("XY").newObject([cable])).union(usb_a)

    # レセプタクルの開口（+X 側から見て奥へ）
    opening = cq.Solid.makeBox(
        RECEPTACLE_DEPTH + 1.0, RECEPTACLE_W, RECEPTACLE_H,
        cq.Vector(TOTAL_L - RECEPTACLE_DEPTH, -RECEPTACLE_W / 2, -RECEPTACLE_H / 2),
    )
    return part.cut(cq.Workplane("XY").newObject([opening]))


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """真っ直ぐに伸ばした姿勢の keep-out + 曲げ半径ぶんの逃げ.

    **可動部の取り回しはこの envelope では表現できない。**
    clearance チェックに使えるのは「真っ直ぐに置いた場合」だけ。
    実装では RIGID_TOTAL 65.8 と FLEX_LENGTH 84.2、MIN_BEND_RADIUS 15.0 を
    使って人が経路を決めること。
    """
    c = clearance
    micro = cq.Workplane("XY").box(
        MICRO_L + c, MICRO_W + 2 * c, MICRO_H + 2 * c, centered=(False, True, True)
    ).translate((-c, 0, 0))
    usb_a = cq.Workplane("XY").box(
        USB_A_L + c, USB_A_W + 2 * c, USB_A_H + 2 * c, centered=(False, True, True)
    ).translate((TOTAL_L - USB_A_L, 0, 0))
    # 可動部は曲げ半径ぶんの筒で包む（真っ直ぐな姿勢での保守側の見積り）
    d = CABLE_DIA + 2 * MIN_BEND_RADIUS + 2 * c
    flex = cq.Solid.makeBox(
        FLEX_LENGTH, d, d, cq.Vector(MICRO_L, -d / 2, -d / 2)
    )
    return micro.union(usb_a).union(cq.Workplane("XY").newObject([flex]))


ENVELOPE = envelope(0.5)


def folded_span(legs: int = 2) -> float:
    """可動部を legs 本に折り返したときの、直線方向に必要な長さの目安.

    剛体 65.8 mm は折り返せないので必ず 1 本ぶん効く。
    """
    usable = FLEX_LENGTH - (legs - 1) * (2 * MIN_BEND_RADIUS)
    return RIGID_TOTAL + max(usable, 0.0) / legs


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "OTG cable (micro-USB M - USB-A F)", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=(
            "実測 2026-08-22。全長 150.0 / 剛体 65.8 / 可動 84.2。"
            "Pi Zero 2 W 65 + このケーブル 150 + Onyx 95 = 310 mm で "
            "P1S の枠 256 mm を超えるため折り返し配置が必須。"
            "ケーブル外径と最小曲げ半径は推定。"
        ),
    )
