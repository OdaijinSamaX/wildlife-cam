"""Raspberry Pi Zero 2 W.

外形と取付穴は Raspberry Pi の機構図どおり（65 x 30 mm、取付穴 58 x 23 ピッチ φ2.75、
穴中心は各辺から 3.5 mm）。
実装部品の高さ（上面 3.0 mm / 下面 1.2 mm）は **推定**。ヘッダを立てる場合や
HAT を載せる場合はここでは足りない。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "datasheet"

PCB_L = 65.0          # データシート
PCB_W = 30.0          # データシート
PCB_T = 1.0           # データシート
HOLE_DIA = 2.75       # データシート
HOLE_INSET = 3.5      # データシート（各辺から穴中心まで）
TOP_COMP_H = 3.0      # 推定（SoC / 無線シールド / microSD）
BOT_COMP_H = 1.2      # 推定（はんだ面）
CONNECTOR_MARGIN = 6.0  # 推定（USB / HDMI ケーブルの抜き差し代）

HOLE_PITCH_X = PCB_L - 2 * HOLE_INSET   # 58.0
HOLE_PITCH_Y = PCB_W - 2 * HOLE_INSET   # 23.0


def hole_positions() -> list[tuple[float, float]]:
    """PCB 中心を原点としたときの取付穴中心."""
    return [
        (sx * HOLE_PITCH_X / 2, sy * HOLE_PITCH_Y / 2)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def model() -> cq.Workplane:
    """PCB 上面を z=0 とし、部品は +z 側に出る（基板中心が原点）."""
    pcb = (
        cq.Workplane("XY")
        .box(PCB_L, PCB_W, PCB_T, centered=(True, True, False))
        .translate((0, 0, -PCB_T))
    )
    for x, y in hole_positions():
        pcb = pcb.cut(
            cq.Workplane("XY")
            .circle(HOLE_DIA / 2)
            .extrude(PCB_T + 1)
            .translate((x, y, -PCB_T - 0.5))
        )
    top = cq.Workplane("XY").box(
        PCB_L - 4, PCB_W - 4, TOP_COMP_H, centered=(True, True, False)
    )
    bot = (
        cq.Workplane("XY")
        .box(PCB_L - 4, PCB_W - 4, BOT_COMP_H, centered=(True, True, False))
        .translate((0, 0, -PCB_T - BOT_COMP_H))
    )
    return pcb.union(top).union(bot)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """外形 + clearance。コネクタ側 (+X) には抜き差し代を足す."""
    c = clearance
    length = PCB_L + 2 * c + CONNECTOR_MARGIN
    return cq.Workplane("XY").box(
        length,
        PCB_W + 2 * c,
        PCB_T + TOP_COMP_H + BOT_COMP_H + 2 * c,
        centered=(True, True, False),
    ).translate((CONNECTOR_MARGIN / 2, 0, -PCB_T - BOT_COMP_H - c))


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Pi Zero 2 W", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="実装部品高さは推定。コネクタ抜き差し代 6 mm を +X に確保",
    )
