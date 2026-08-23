"""HC-SR501 PIR モーションセンサ.

DIM_SOURCE = "measured:2026-08-22"（ノギス実測）。以前の推定値は全て破棄した。

| 項目 | 実測 | 備考 |
|---|---|---|
| PCB_L | 32.8 mm | |
| PCB_W | 24.4 mm | |
| PCB_T | 1.4 mm | |
| DOME_DIA | 23.0 mm | |
| DOME_H | 14.4 mm | **基板表面からドーム頂点まで** |
| SKIRT_H | 3.3 mm | ドーム根元の円筒部 |
| HOLE_DIA | 2.2 mm | **誤差の可能性あり**（小径で当てにくい） |
| HOLE_PITCH | 28.5 mm | **誤差の可能性あり**（穴中心の読みが甘い） |
| BACK_COMP_H | 8.0 mm | 導出値: 全高 23.8 - DOME_H 14.4 - PCB_T 1.4 |
| モジュール全高 | 23.8 mm | 基板裏の半固定抵抗頂点からドーム頂点まで |

ドーム形状: φ23.0 の円筒スカートが 3.3 mm、その上に高さ 11.1 mm の球冠。
球半径は (11.5^2 + 11.1^2) / (2 x 11.1) = 11.507 mm で、z=3.3 での面内半径が
11.500 mm となりスカートと接線連続になる。実測 3 点と整合する。

## 最重要: **O リングを押し付けるツバが存在しない**

FLANGE_DIA を実測したところ **DOME_DIA と同じ 23.0 mm** で、指でなぞっても
段差が無いことを確認した。つまりドームの根元にツバ（フランジ）は無い。

「ドームのフランジを O リングで筐体壁に押し付けて密封する」という構成は
**物理的に成立しない**。この結論に基づいて designs/wildlife_cam/pir_bezel.py を
接着封止キャリアに作り直した。経緯と検討した他案は docs/DECISIONS.md にある。

基板を使った面シールも成立しない:
  PCB_W 24.4 - DOME_DIA 23.0 -> 片側 0.70 mm しか残らない。
  最小の φ1.0 コードでも 溝幅 1.35 + 両側 land 1.6 x 2 = 4.55 mm 必要。

## 残っている前提

  ドームは基板に対して密封されていない（スナップ嵌合）。したがって
  シール面はドームの外側に作る必要があり、基板側は乾燥側に置く。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "measured:2026-08-22"

PCB_L = 32.8        # 実測 2026-08-22
PCB_W = 24.4        # 実測 2026-08-22
PCB_T = 1.4         # 実測 2026-08-22
DOME_DIA = 23.0     # 実測 2026-08-22
DOME_H = 14.4       # 実測 2026-08-22（基板表面からドーム頂点まで）
SKIRT_H = 3.3       # 実測 2026-08-22（ドーム根元の円筒部）
HOLE_DIA = 2.2      # 実測 2026-08-22 ※誤差の可能性あり（小径で当てにくい）
HOLE_PITCH = 28.5   # 実測 2026-08-22 ※誤差の可能性あり（穴中心の読みが甘い）
BACK_COMP_H = 8.0   # 導出値: MODULE_H 23.8 - DOME_H 14.4 - PCB_T 1.4
MODULE_H = 23.8     # 実測 2026-08-22（モジュール全高）

#: ドーム外径と同径。ツバ（O リングを座らせる平坦部）は存在しない。
FLANGE_DIA = DOME_DIA
#: シール用のツバを持つか。pir_bezel の構成判断はこのフラグの意味に依存する。
HAS_SEALING_FLANGE = False

#: 誤差の可能性があると申告した項目。実測をやり直したらここから消す。
UNCERTAIN = ("HOLE_DIA", "HOLE_PITCH")


def hole_positions() -> list[tuple[float, float]]:
    """基板中心を原点としたときの取付穴中心（長手方向に 2 個）."""
    return [(-HOLE_PITCH / 2, 0.0), (HOLE_PITCH / 2, 0.0)]


def dome_sphere() -> tuple[float, float]:
    """球冠の (半径, 中心 z)。スカート上端で接線連続になる値を返す."""
    r = DOME_DIA / 2
    cap_h = DOME_H - SKIRT_H
    radius = (r * r + cap_h * cap_h) / (2 * cap_h)
    return radius, DOME_H - radius


def model() -> cq.Workplane:
    """基板前面（ドーム側）を z=0 とする。ドームは +z、実装部品は -z."""
    pcb = (
        cq.Workplane("XY")
        .box(PCB_L, PCB_W, PCB_T, centered=(True, True, False))
        .translate((0, 0, -PCB_T))
    )
    for x, y in hole_positions():
        pcb = pcb.cut(
            cq.Workplane("XY").circle(HOLE_DIA / 2).extrude(PCB_T + 1)
            .translate((x, y, -PCB_T - 0.5))
        )

    r = DOME_DIA / 2
    skirt = cq.Workplane("XY").circle(r).extrude(SKIRT_H)
    sphere_r, sphere_z = dome_sphere()
    cap = (
        cq.Workplane("XY")
        .sphere(sphere_r)
        .translate((0, 0, sphere_z))
        .intersect(
            cq.Workplane("XY").circle(r).extrude(DOME_H - SKIRT_H)
            .translate((0, 0, SKIRT_H))
        )
    )
    back = (
        cq.Workplane("XY")
        .box(PCB_L - 4, PCB_W - 4, BACK_COMP_H, centered=(True, True, False))
        .translate((0, 0, -PCB_T - BACK_COMP_H))
    )
    return pcb.union(skirt).union(cap).union(back)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """段付きの keep-out。

    基板前面 (z=0) より上には基板ぶんのクリアランスを足さない。キャリアの座面で
    基板を受ける構成では、そこは「意図した接触面」だから。
    ツバが無いので、以前あったフランジ段は削除した（ドームは φ23.0 の一段）。
    """
    c = clearance
    body = cq.Workplane("XY").box(
        PCB_L + 2 * c, PCB_W + 2 * c, PCB_T + BACK_COMP_H + c,
        centered=(True, True, False),
    ).translate((0, 0, -PCB_T - BACK_COMP_H - c))
    dome = cq.Workplane("XY").circle(DOME_DIA / 2 + c).extrude(DOME_H + c)
    return body.union(dome)


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "HC-SR501 PIR", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=(
            "実測 2026-08-22。ツバが無く (FLANGE_DIA == DOME_DIA == 23.0)、"
            "O リングを押し付ける平坦部が存在しない。"
            "HOLE_DIA 2.2 と HOLE_PITCH 28.5 は誤差の可能性あり。"
        ),
    )
