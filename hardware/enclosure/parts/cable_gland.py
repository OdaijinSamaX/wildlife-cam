"""ケーブルグランド PG7（ナイロン・IP68 相当）.

PG7 のねじ外径 12.5 mm / ピッチ 1.27 mm は PG 規格値。
パネル穴 φ12.5、対辺 15 mm の六角ナット、本体全長 22 mm、
適用ケーブル径 3.0〜6.5 mm は **推定**（メーカーで違う）。

パネル取付部の板厚は 2.0〜5.0 mm を想定（推定）。壁がこれより厚いと
ナットが掛からないので、グランド座面を掘り下げること。
"""

import math

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "standard+estimated"

THREAD_OD = 12.5      # PG7 規格
PANEL_HOLE = 12.6     # 推定（クリアランス込みのパネル穴）
THREAD_LEN = 8.0      # 推定
NUT_AF = 15.0         # 推定（対辺）
NUT_H = 4.0           # 推定
BODY_AF = 17.0        # 推定（六角の対辺）
BODY_LEN = 14.0       # 推定（パネル外側に出る長さ）
CABLE_MIN = 3.0       # 推定
CABLE_MAX = 6.5       # 推定
MAX_PANEL_T = 5.0     # 推定（これ以上厚い壁には座ぐりが要る）


def _hex(af: float, h: float) -> cq.Workplane:
    return cq.Workplane("XY").polygon(6, af / math.cos(math.pi / 6)).extrude(h)


def model() -> cq.Workplane:
    """パネル外面を z=0。本体は +z、ねじとナットは -z（筐体内側）."""
    body = _hex(BODY_AF, BODY_LEN)
    thread = cq.Workplane("XY").circle(THREAD_OD / 2).extrude(-THREAD_LEN)
    nut = _hex(NUT_AF, NUT_H).translate((0, 0, -MAX_PANEL_T - NUT_H))
    bore = cq.Workplane("XY").circle(CABLE_MAX / 2).extrude(BODY_LEN + THREAD_LEN + NUT_H + 2) \
        .translate((0, 0, -THREAD_LEN - NUT_H - 1))
    return body.union(thread).union(nut).cut(bore)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    d = max(BODY_AF, NUT_AF) / math.cos(math.pi / 6) + 2 * c
    return cq.Workplane("XY").circle(d / 2).extrude(BODY_LEN + c) \
        .union(
            cq.Workplane("XY").circle(d / 2).extrude(-(MAX_PANEL_T + NUT_H + c))
        )


ENVELOPE = envelope(0.5)


def panel_hole() -> float:
    return PANEL_HOLE


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Cable gland PG7", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=f"パネル穴 φ{PANEL_HOLE}。ナット掛かりは板厚 {MAX_PANEL_T} mm まで（推定）",
    )
