"""850 nm IR 投光器（別電源・GND 共通）.

**全寸法が推定。** 市販の小型 IR 投光基板を想定した概寸で、実物が決まったら差し替える。
発熱するので、筐体内に閉じ込めず外気に面させるか、放熱経路を別に設計すること
（このダミーは放熱設計を一切表現していない）。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "estimated"

BOARD_W = 45.0     # 推定
BOARD_H = 45.0     # 推定
BOARD_T = 1.6      # 推定
LED_DIA = 5.0      # 推定（φ5 砲弾 LED）
LED_H = 8.6        # 推定
LED_PITCH = 12.0   # 推定
LED_COLS = 3       # 推定
BACK_H = 6.0       # 推定（抵抗・コネクタ・配線）
BEAM_CLEAR = 5.0   # 推定（投光面前方の逃げ）


def model() -> cq.Workplane:
    """基板前面を z=0、LED は +z."""
    board = (
        cq.Workplane("XY")
        .box(BOARD_W, BOARD_H, BOARD_T, centered=(True, True, False))
        .translate((0, 0, -BOARD_T))
    )
    leds = cq.Workplane("XY")
    span = (LED_COLS - 1) * LED_PITCH / 2
    for i in range(LED_COLS):
        for j in range(LED_COLS):
            leds = leds.union(
                cq.Workplane("XY").circle(LED_DIA / 2).extrude(LED_H)
                .translate((-span + i * LED_PITCH, -span + j * LED_PITCH, 0))
            )
    back = (
        cq.Workplane("XY")
        .box(BOARD_W - 6, BOARD_H - 6, BACK_H, centered=(True, True, False))
        .translate((0, 0, -BOARD_T - BACK_H))
    )
    return board.union(leds).union(back)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    h = BOARD_T + BACK_H + LED_H + BEAM_CLEAR + 2 * c
    return cq.Workplane("XY").box(
        BOARD_W + 2 * c, BOARD_H + 2 * c, h, centered=(True, True, False)
    ).translate((0, 0, -BOARD_T - BACK_H - c))


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "850nm IR illuminator", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="全寸法が推定。放熱経路はこのダミーに含まれない",
    )
