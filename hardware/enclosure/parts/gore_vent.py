"""防水通気ベント（ePTFE メンブレン・M12 ねじ込みタイプ）.

密閉筐体は昼夜の温度差で内圧が振れる。振れを逃がさないと O リングを
押し広げて水を吸うので、通気ベントは防水設計の一部として必ず入れる。

M12 x 1.5 のねじ / パネル穴 φ12.2 は一般的な値だが、フランジ径 17 mm、
高さ 8 mm、ナット対辺 15 mm は **推定**。実物の型番が決まったら差し替える。
"""

import math

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "estimated"

THREAD_OD = 12.0     # M12
PANEL_HOLE = 12.3    # 推定（M12 用のバカ穴）
FLANGE_DIA = 17.0    # 推定
FLANGE_T = 2.0       # 推定
THREAD_LEN = 7.0     # 推定
NUT_AF = 15.0        # 推定
NUT_H = 4.0          # 推定
MAX_PANEL_T = 4.0    # 推定


def model() -> cq.Workplane:
    """パネル外面を z=0。フランジは +z、ねじとナットは -z."""
    flange = cq.Workplane("XY").circle(FLANGE_DIA / 2).extrude(FLANGE_T)
    thread = cq.Workplane("XY").circle(THREAD_OD / 2).extrude(-THREAD_LEN)
    nut = (
        cq.Workplane("XY")
        .polygon(6, NUT_AF / math.cos(math.pi / 6))
        .extrude(NUT_H)
        .translate((0, 0, -MAX_PANEL_T - NUT_H))
    )
    return flange.union(thread).union(nut)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    d = max(FLANGE_DIA, NUT_AF / math.cos(math.pi / 6)) + 2 * c
    return (
        cq.Workplane("XY").circle(d / 2).extrude(FLANGE_T + c)
        .union(cq.Workplane("XY").circle(d / 2).extrude(-(MAX_PANEL_T + NUT_H + c)))
    )


ENVELOPE = envelope(0.5)


def panel_hole() -> float:
    return PANEL_HOLE


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Waterproof vent M12", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=f"パネル穴 φ{PANEL_HOLE}。全寸法が推定・型番未定",
    )
