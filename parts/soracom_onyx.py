"""SORACOM Onyx LTE USB ドングル (SC-QGLC4-C1).

中の無線モジュールが Quectel EG25-G。**mini-PCIe カードではなく USB ドングル**
なので、以前 parts/eg25g.py で mini-PCIe (30 x 51 x 4.5) と仮定していたのは誤り。
2026-08-22 に実物の型番が判明したため差し替えた。

## メーカー公称値（DIM_SOURCE = datasheet）

| 項目 | 値 |
|---|---|
| 外形 | 95 x 36 x 13 mm |
| 重量 | 36 g |
| インタフェース | USB-A オスのプラグ直付け（ケーブル無し） |
| 電源 | USB のみ / 4.2 - 6 V |
| 動作温度 | -20 - +60 degC |
| アンテナ | 内蔵 + 外部端子 CRC9 x 2（MAIN / DIV） |
| SIM | 筐体上面のスロット |

## 公称値に無いので **推定** で置いているもの（追って実測値が来る）

- **USB-A プラグの突出量** — 全長 95 mm のうちプラグが何 mm を占めるか。
  ここでは USB-A オスの規格値 12.0 x 4.5 mm を使い、突出 12.0 mm と置いた。
  95 mm がプラグを含まない可能性もあるので、その場合は全長 107 mm になる。
  `LENGTH_INCLUDES_PLUG` を False にすると後者で組む。
- **SIM スロットの位置** — 上面のどこか、としか分かっていない。遠端寄りと置いた。
  SIM の形状（nano / micro）も未確認。開口 14 x 10 mm で置いている。
- **CRC9 端子の位置** — 長辺のどちら側かも分かっていない。
  そのため **envelope では左右どちらの長辺にもアンテナ用の逃げを取る**。
  片側だけ空けて実物が反対側だった、という事故を防ぐため。

## 設計上の注意

- **全長 95 mm はこの筐体で最長の部品。** Pi Zero 2 W の 65 mm より 30 mm 長い。
  さらに USB プラグの挿抜代が要るので、筐体内には 110 mm 前後の直線的な
  空きが必要になる。筐体の内寸はまずこの部品で決まる。docs/AGENTS.md 参照。
- **動作温度の上限が +60 degC。** 直射日光下の黒い密閉筐体は容易に 60 degC を
  超える。この部品は熱的に最も弱いので、放熱と日射の扱いを筐体設計で解くこと。
  このダミー形状は発熱も放熱も一切表現していない。
- USB 給電のみなので、Pi 側の USB ポート（または OTG アダプタ）から
  ドングルまでの経路が電源経路でもある。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "datasheet"
PART_NUMBER = "SC-QGLC4-C1"
FORM_FACTOR = "USB-A 直付けドングル"

# --- メーカー公称 -----------------------------------------------------------
OVERALL_L = 95.0     # 公称（外形）
BODY_W = 36.0        # 公称
BODY_H = 13.0        # 公称
MASS_G = 36.0        # 公称
VIN_MIN = 4.2        # 公称（V）
VIN_MAX = 6.0        # 公称（V）
TEMP_MIN = -20.0     # 公称（degC）
TEMP_MAX = 60.0      # 公称（degC）

# --- USB-A オスプラグ -------------------------------------------------------
PLUG_W = 12.0        # USB Type-A 規格値
PLUG_H = 4.5         # USB Type-A 規格値
PLUG_L = 12.0        # 推定（要実測）: 筐体から突き出す長さ
LENGTH_INCLUDES_PLUG = True   # 推定（要実測）: 公称 95 mm がプラグを含むかどうか
INSERT_TRAVEL = 15.0          # 推定: 抜き差しに要る直線の逃げ

# --- SIM スロット（上面） ---------------------------------------------------
SIM_SLOT_W = 14.0    # 推定（要実測）
SIM_SLOT_D = 10.0    # 推定（要実測）
SIM_SLOT_DEPTH = 1.2  # 推定（要実測）
SIM_SLOT_X = 74.0    # 推定（要実測）: プラグ先端からスロット中心まで
SIM_ACCESS_H = 12.0  # 推定: 上面から SIM を抜き差しするための空き

# --- CRC9 外部アンテナ端子 x 2 ---------------------------------------------
CRC9_PORT_DIA = 3.0   # 推定（要実測）
CRC9_PORT_DEPTH = 1.5  # 推定（要実測）
CRC9_PLUG_DIA = 5.0    # 推定: 嵌合したプラグの外径
CRC9_PLUG_L = 12.0     # 推定: 嵌合したプラグの長さ
CABLE_BEND = 15.0      # 推定: 同軸ケーブルの最小曲げ半径ぶんの逃げ
#: プラグ先端からの X 位置。MAIN と DIV。位置は推定（要実測）
CRC9_X = (80.0, 90.0)
#: 端子が出ている長辺。実物がどちら側か不明なので、envelope では両側を空ける。
CRC9_ASSUMED_SIDE = -1   # 推定: -Y 側と仮置き


def body_length() -> float:
    """プラグを除いた筐体部の長さ."""
    return (OVERALL_L - PLUG_L) if LENGTH_INCLUDES_PLUG else OVERALL_L


def total_length() -> float:
    """プラグ先端から遠端までの全長."""
    return OVERALL_L if LENGTH_INCLUDES_PLUG else OVERALL_L + PLUG_L


def model() -> cq.Workplane:
    """原点 = USB-A プラグの先端。+X が本体方向、+Z が SIM スロットのある上面.

    Y と Z は筐体断面の中心に合わせてある（プラグの中心線と筐体の中心線は一致
    するものと仮定 — 推定）。
    """
    plug = cq.Workplane("XY").box(
        PLUG_L, PLUG_W, PLUG_H, centered=(False, True, True)
    )
    body = (
        cq.Workplane("XY")
        .box(body_length(), BODY_W, BODY_H, centered=(False, True, True))
        .translate((PLUG_L, 0, 0))
    )
    part = plug.union(body)

    # SIM スロット（上面の彫り込み）
    part = part.cut(
        cq.Workplane("XY")
        .box(SIM_SLOT_D, SIM_SLOT_W, SIM_SLOT_DEPTH + 1, centered=(True, True, False))
        .translate((SIM_SLOT_X, 0, BODY_H / 2 - SIM_SLOT_DEPTH))
    )

    # CRC9 端子（長辺の彫り込み）。外面から内側へ掘る。
    side = CRC9_ASSUMED_SIDE
    for x in CRC9_X:
        start = cq.Vector(x, side * (BODY_W / 2 + 1.0), 0)
        cutter = cq.Solid.makeCylinder(
            CRC9_PORT_DIA / 2, CRC9_PORT_DEPTH + 1.0, start, cq.Vector(0, -side, 0)
        )
        part = part.cut(cq.Workplane("XY").newObject([cutter]))
    return part


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """外形 + clearance に、抜き差し代・SIM アクセス・アンテナ配線の逃げを足す.

    CRC9 がどちらの長辺かが未確定なので、**両側**にアンテナの逃げを取る。
    片側だけ空けて実物が反対側だった、という事故を防ぐため。
    """
    c = clearance
    main = cq.Workplane("XY").box(
        total_length() + INSERT_TRAVEL + 2 * c,
        BODY_W + 2 * c,
        BODY_H + 2 * c,
        centered=(False, True, True),
    ).translate((-INSERT_TRAVEL - c, 0, 0))

    sim = (
        cq.Workplane("XY")
        .box(SIM_SLOT_D + 2 * c, SIM_SLOT_W + 2 * c, SIM_ACCESS_H,
             centered=(True, True, False))
        .translate((SIM_SLOT_X, 0, BODY_H / 2 + c))
    )

    ant = cq.Workplane("XY")
    reach = CRC9_PLUG_L + CABLE_BEND
    d = CRC9_PLUG_DIA + 2 * c
    for x in CRC9_X:
        for side in (-1, 1):   # 実物がどちら側か不明なので両側を空ける
            y0 = side * (BODY_W / 2 + c)
            ymin = min(y0, y0 + side * reach)
            box = cq.Solid.makeBox(
                d, reach, d, cq.Vector(x - d / 2, ymin, -d / 2)
            )
            ant = ant.union(cq.Workplane("XY").newObject([box]))
    return main.union(sim).union(ant)


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        f"SORACOM Onyx ({PART_NUMBER})", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=(
            "外形 95x36x13 / 36g は公称。USB プラグ突出量・SIM スロット位置・"
            "CRC9 端子位置は推定（要実測）。筐体内で最長 (95 mm) の部品で、"
            "抜き差し代を含めると 110 mm 前後の直線的な空きが要る。"
            "動作温度の上限 +60 degC が熱設計の律速。"
        ),
    )
