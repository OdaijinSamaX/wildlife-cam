"""O リングコード φ2.0（線径 2.0 mm）.

溝寸法の根拠（静的なフェイスシール = 面圧で潰す使い方）:
  圧縮率  (cord - depth) / cord = 25%  … 静的シールの一般的な目安 20〜30%
  溝深さ  depth = 0.75 * cord = 1.50 mm
  溝幅    width = 1.35 * cord = 2.70 mm
  充填率  cord 断面積 / 溝断面積 = pi * 1.0^2 / (2.70 * 1.50) = 77.6%
          （潰れたゴムが逃げられる余地を残すため 90% 未満に収める）
プリント品は溝底が荒れるので、深さは -0.05 mm ほど浅めに出る想定。
実測で詰めるのは fit_coupon の役目。
"""

import math

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "engineering-rule"

CORD = 2.0
COMPRESSION = 0.25
GROOVE_DEPTH = round(CORD * (1 - COMPRESSION), 2)   # 1.50
GROOVE_WIDTH = round(CORD * 1.35, 2)                # 2.70


def fill_ratio(cord: float = CORD, width: float = GROOVE_WIDTH,
               depth: float = GROOVE_DEPTH) -> float:
    return math.pi * (cord / 2) ** 2 / (width * depth)


def model(mean_dia: float = 30.0, cord: float = CORD) -> cq.Workplane:
    """z=0 の平面上に置いた O リング（mean_dia = 中心径）."""
    torus = cq.Solid.makeTorus(mean_dia / 2, cord / 2)
    return cq.Workplane("XY").newObject([torus])


def envelope(clearance: float = 0.0, mean_dia: float = 30.0, cord: float = CORD) -> cq.Workplane:
    return model(mean_dia=mean_dia, cord=cord + 2 * clearance)


ENVELOPE = envelope(0.1)


def groove_profile(mean_dia: float, width: float = GROOVE_WIDTH,
                   depth: float = GROOVE_DEPTH) -> cq.Workplane:
    """溝の切り抜き形状。z=0 のシール面から -z 方向に depth 掘る."""
    outer = mean_dia / 2 + width / 2
    inner = mean_dia / 2 - width / 2
    return (
        cq.Workplane("XY")
        .circle(outer)
        .circle(inner)
        .extrude(-depth)
    )


def place(at=(0, 0, 0), rotate=(0, 0, 0), mean_dia: float = 30.0):
    return make_component(
        f"O-ring cord phi{CORD} (mean {mean_dia})", model, envelope,
        at=at, rotate=rotate, mean_dia=mean_dia,
        dimension_source=DIM_SOURCE,
        notes=f"溝 {GROOVE_WIDTH} x {GROOVE_DEPTH} mm / 圧縮率 25% / 充填率 {fill_ratio()*100:.0f}%",
    )
