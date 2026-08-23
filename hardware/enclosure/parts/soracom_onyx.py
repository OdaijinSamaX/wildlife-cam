"""SORACOM Onyx LTE USB ドングル (SC-QGLC4-C1).

中の無線モジュールが Quectel EG25-G。**mini-PCIe カードではなく USB ドングル**
なので、以前 parts/eg25g.py で mini-PCIe (30 x 51 x 4.5) と仮定していたのは誤り。
2026-08-22 に実物の型番が判明したため差し替えた。

## 実測 2026-08-22（DIM_SOURCE = measured）

| 項目 | 実測 | 備考 |
|---|---|---|
| BODY_L | 77.5 mm | 筐体部（プラグを除く） |
| USB-A プラグ突出 | 11.9 mm | |
| 全長 | **89.4 mm** | 77.5 + 11.9。**公称 95 とは 5.6 mm 食い違う** |
| BODY_W | 35.8 mm | 公称 36 と一致 |
| BODY_H | 13.2 mm | |
| 後端の面取り | 後端から **20.8 mm** の区間で厚みが **9.3 mm** に落ちる | USB 側を上に見て。その脇には他の部品を寄せられる |
| **OTG ケーブル装着時の全長** | **115.0 mm** | **この箱の中を貫く曲がらない剛体の実長。配置を支配する** |

公称 95 mm は実測 89.4 mm と合わない。実測を採る。
115.0 = 89.4 + USB-A ハウジング 35.0 − 差し込み代 9.4 で辻褄が合う。

## 旧メーカー公称値（参考）

| 項目 | 値 |
|---|---|
| 外形 | 95 x 36 x 13 mm |
| 重量 | 36 g |
| インタフェース | USB-A オスのプラグ直付け（ケーブル無し） |
| 電源 | USB のみ / 4.2 - 6 V |
| 動作温度 | -20 - +60 degC |
| アンテナ | 内蔵 + 外部端子 CRC9 x 2（MAIN / DIV） |
| SIM | 筐体上面のスロット |

## アンテナは内蔵で確定（2026-08-22）

**外部アンテナ端子 CRC9 は使わない。** ドングル単体で通信できることを実機で確認済み。
したがって CRC9 のための筐体貫通は不要。`envelope()` の既定も
`external_antenna=False` にしてある。

**その代わり内蔵アンテナ 1 本になるので、配置ルールを守ること:**

  - **Onyx は筐体の壁際に置く**（電波が抜ける側に面させる）
  - **金属および他の基板を近づけない**

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

DIM_SOURCE = "measured:2026-08-22"
PART_NUMBER = "SC-QGLC4-C1"
FORM_FACTOR = "USB-A 直付けドングル"

# --- 実測 2026-08-22 --------------------------------------------------------
BODY_L = 77.5        # 実測（プラグを除く筐体部）
BODY_W = 35.8        # 実測（公称 36 と一致）
BODY_H = 13.2        # 実測
THIN_L = 20.8        # 実測（後端から。この区間だけ薄い）
THIN_H = 9.3         # 実測（面取り後の厚み）
OVERALL_L = 89.4     # 実測 = BODY_L 77.5 + PLUG_L 11.9。公称 95 とは食い違う
NOMINAL_L = 95.0     # 旧公称（参考。実測と 5.6 mm 違う）

#: OTG ケーブルの USB-A メスを挿した組立状態の実測全長。
#: **箱の中を貫く曲がらない剛体の実長であり、レイアウトを支配する寸法。**
ASSEMBLED_WITH_OTG_L = 115.0   # 実測 2026-08-22

#: 面取りが片側だけか両側対称かは測っていない（推定）。
#: レイアウトで薄い部分の脇を使うときは、片側だけの可能性を頭に置くこと。
THIN_IS_SYMMETRIC = True   # 推定（要確認）

MASS_G = 36.0        # 公称
VIN_MIN = 4.2        # 公称（V）
VIN_MAX = 6.0        # 公称（V）
TEMP_MIN = -20.0     # 公称（degC）
TEMP_MAX = 60.0      # 公称（degC）

# --- USB-A オスプラグ -------------------------------------------------------
PLUG_W = 12.0        # USB Type-A 規格値
PLUG_H = 4.5         # USB Type-A 規格値
PLUG_L = 11.9        # 実測 2026-08-22（筐体から突き出す長さ）
#: USB-A メスに飲み込まれる長さ = OVERALL_L + USB-A ハウジング 35.0 - 115.0
PLUG_ENGAGEMENT = 9.4         # 導出（実測の組立全長 115.0 から）
INSERT_TRAVEL = 15.0          # 推定: 抜き差しに要る直線の逃げ

# --- SIM スロット（上面） ---------------------------------------------------
SIM_SLOT_W = 14.0    # 推定（要実測）
SIM_SLOT_D = 10.0    # 推定（要実測）
SIM_SLOT_DEPTH = 1.2  # 推定（要実測）
SIM_SLOT_X = 60.0    # 推定（要実測）: プラグ先端からスロット中心まで
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
    """プラグを除いた筐体部の長さ（実測）."""
    return BODY_L


def total_length() -> float:
    """プラグ先端から遠端までの全長（実測）."""
    return OVERALL_L


def thin_region_x() -> tuple[float, float]:
    """後端の薄い区間（プラグ先端からの X 範囲）."""
    return (OVERALL_L - THIN_L, OVERALL_L)


def model(external_antenna: bool = False) -> cq.Workplane:
    """原点 = USB-A プラグの先端。+X が本体方向、+Z が SIM スロットのある上面.

    external_antenna は envelope 側の指定で、実体形状は変わらない（受け流す）.

    Y と Z は筐体断面の中心に合わせてある（プラグの中心線と筐体の中心線は一致
    するものと仮定 — 推定）。
    """
    plug = cq.Workplane("XY").box(
        PLUG_L, PLUG_W, PLUG_H, centered=(False, True, True)
    )
    body = (
        cq.Workplane("XY")
        .box(BODY_L, BODY_W, BODY_H, centered=(False, True, True))
        .translate((PLUG_L, 0, 0))
    )
    part = plug.union(body)

    # 後端 THIN_L の区間で厚みが THIN_H まで落ちる面取り（対称と仮定＝推定）
    t0, t1 = thin_region_x()
    drop = (BODY_H - THIN_H) / 2
    for sign in (1, -1):
        part = part.cut(
            cq.Workplane("XY")
            .box(THIN_L + 1.0, BODY_W + 2.0, drop, centered=(False, True, False))
            .translate((t0, 0, sign * THIN_H / 2 if sign > 0 else -BODY_H / 2))
        )

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


def envelope(clearance: float = 0.0, external_antenna: bool = False) -> cq.Workplane:
    """外形 + clearance に、抜き差し代・SIM アクセス・アンテナ配線の逃げを足す.

    CRC9 がどちらの長辺かが未確定なので、**両側**にアンテナの逃げを取る。
    片側だけ空けて実物が反対側だった、という事故を防ぐため。

    `external_antenna=False` にすると内蔵アンテナで使う前提になり、CRC9 の
    逃げ（片側 27 mm）を取らない。筐体が一気に小さくなるので、外部アンテナを
    使わないと決めたときだけ使うこと。
    """
    c = clearance
    t0, _t1 = thin_region_x()
    main = cq.Workplane("XY").box(
        t0 + INSERT_TRAVEL + 2 * c,
        BODY_W + 2 * c,
        BODY_H + 2 * c,
        centered=(False, True, True),
    ).translate((-INSERT_TRAVEL - c, 0, 0))
    # 後端の薄い区間は薄いまま包む（脇に他の部品を寄せられるようにするため）
    main = main.union(
        cq.Workplane("XY").box(
            THIN_L + 2 * c, BODY_W + 2 * c, THIN_H + 2 * c,
            centered=(False, True, True),
        ).translate((t0 - c, 0, 0))
    )

    sim = (
        cq.Workplane("XY")
        .box(SIM_SLOT_D + 2 * c, SIM_SLOT_W + 2 * c, SIM_ACCESS_H,
             centered=(True, True, False))
        .translate((SIM_SLOT_X, 0, BODY_H / 2 + c))
    )

    if not external_antenna:
        return main.union(sim)

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


def place(at=(0, 0, 0), rotate=(0, 0, 0), external_antenna: bool = False):
    return make_component(
        f"SORACOM Onyx ({PART_NUMBER})", model, envelope, at=at, rotate=rotate,
        external_antenna=external_antenna,
        dimension_source=DIM_SOURCE,
        notes=(
            "実測 2026-08-22: 本体 77.5 + プラグ 11.9 = 89.4 / 幅 35.8 / 厚み 13.2、"
            "後端 20.8 mm は厚み 9.3。**OTG 装着時の剛体全長 115.0 が配置を支配する**。"
            "外部アンテナは使わない（内蔵で通信確認済み）ので、壁際に置き "
            "金属と他基板を近づけないこと。"
            "動作温度の上限 +60 degC が熱設計の律速。"
        ),
    )
