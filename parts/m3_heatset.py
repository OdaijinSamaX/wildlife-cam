"""M3 ヒートセットインサート（真鍮・熱圧入）.

想定品: M3 x 全長 5.0 mm / 外径 4.6 mm（ローレット部の最大径）。
これは一般的な「M3 x L5.0 / OD 4.6」タイプの公称値だが、メーカーで 0.1〜0.2 mm 違う。
下穴径は fit_coupon の実測で確定させる（暫定 φ4.2 は **推定**）。

下穴の深さはインサート長 + 1.0 mm 以上（樹脂の逃げ）を推奨。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "estimated"

OD = 4.6            # 推定（メーカー公称の最大外径）
LENGTH = 5.0        # 推定
THREAD = 3.0        # M3
PILOT_DIA = 4.2     # 推定（fit_coupon で確定させる）
PILOT_EXTRA = 1.0   # 樹脂の逃げ
BOSS_MIN_WALL = 1.6  # ボス外径 = PILOT + 2 * これ を推奨


def model() -> cq.Workplane:
    """上面（挿入面）を z=0、インサートは -z に伸びる."""
    body = cq.Workplane("XY").circle(OD / 2).extrude(-LENGTH)
    return body.cut(cq.Workplane("XY").circle(THREAD / 2).extrude(-LENGTH - 1))


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    return cq.Workplane("XY").circle(OD / 2 + c).extrude(-(LENGTH + c))


ENVELOPE = envelope(0.2)


def pilot_hole(depth: float | None = None, dia: float | None = None) -> cq.Workplane:
    """下穴の切り抜き形状（上面 z=0 から -z 方向）."""
    d = PILOT_DIA if dia is None else dia
    h = (LENGTH + PILOT_EXTRA) if depth is None else depth
    return cq.Workplane("XY").circle(d / 2).extrude(-h)


def boss_outer_dia(pilot_dia: float | None = None) -> float:
    d = PILOT_DIA if pilot_dia is None else pilot_dia
    return d + 2 * BOSS_MIN_WALL


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "M3 heat-set insert", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="OD 4.6 / L5.0 は推定。下穴径は fit_coupon の実測で確定させる",
    )
