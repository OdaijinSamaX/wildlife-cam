"""Raspberry Pi Camera Module 3 NoIR.

基板外形 25 x 24 mm と取付穴 4 x φ2.2 / ピッチ 21 x 12.5 mm はデータシートどおり。
レンズ鏡筒の寸法（12.5 mm 角 x 高さ 6.5 mm）と基板上の位置は **推定**。
フォーカス調整のためレンズ前方に 2 mm の逃げを見ている（推定）。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "datasheet+estimated"

PCB_L = 25.0        # データシート
PCB_W = 24.0        # データシート
PCB_T = 1.0         # データシート
HOLE_DIA = 2.2      # データシート
HOLE_PITCH_X = 21.0  # データシート
HOLE_PITCH_Y = 12.5  # データシート
LENS_SIZE = 12.5    # 推定
LENS_H = 6.5        # 推定
LENS_OFFSET_Y = 2.5  # 推定（基板中心からレンズ中心までの +Y オフセット）
BACK_COMP_H = 1.5   # 推定（はんだ面 / FPC コネクタ）
FOCUS_GAP = 2.0     # 推定（フォーカス調整の逃げ）


def hole_positions() -> list[tuple[float, float]]:
    return [
        (sx * HOLE_PITCH_X / 2, sy * HOLE_PITCH_Y / 2)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def model() -> cq.Workplane:
    """PCB 前面（レンズ側）を z=0 とし、レンズは +z に出る."""
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
    lens = (
        cq.Workplane("XY")
        .box(LENS_SIZE, LENS_SIZE, LENS_H, centered=(True, True, False))
        .translate((0, LENS_OFFSET_Y, 0))
    )
    back = (
        cq.Workplane("XY")
        .box(PCB_L - 3, PCB_W - 3, BACK_COMP_H, centered=(True, True, False))
        .translate((0, 0, -PCB_T - BACK_COMP_H))
    )
    return pcb.union(lens).union(back)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    h = PCB_T + BACK_COMP_H + LENS_H + FOCUS_GAP + 2 * c
    return cq.Workplane("XY").box(
        PCB_L + 2 * c, PCB_W + 2 * c, h, centered=(True, True, False)
    ).translate((0, 0, -PCB_T - BACK_COMP_H - c))


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Camera Module 3 NoIR", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="レンズ鏡筒寸法・位置は推定。フォーカス調整代 2 mm を含む",
    )
