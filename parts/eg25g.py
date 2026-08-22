"""Quectel EG25-G LTE モデム.

**実物の形態が未確定である。** mini-PCIe モジュール単体なのか、USB ドングル
（キャリアボード付き）なのかが決まっていない。ここでは mini-PCIe (full size)
30 x 51 x 4.5 mm として置いているが、これは **推定** であり要実測。

USB ドングル形態だった場合、外形は 30 x 90 x 12 mm 前後になり、筐体内のレイアウトが
根本的に変わる。実物が決まったらこのファイルを差し替えること。
アンテナは u.FL 2 系統（メイン / RX ダイバーシティ）+ GNSS を想定（推定）。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "estimated"
FORM_FACTOR = "mini-PCIe (full size) と仮定 — 要確認"

PCB_W = 30.0        # 推定（mini-PCIe 規格値）
PCB_L = 51.0        # 推定（mini-PCIe full size 規格値）
PCB_T = 1.0         # 推定
COMP_H = 3.5        # 推定（シールド缶）
UFL_H = 3.0         # 推定（u.FL コネクタとケーブルの立ち上がり）
UFL_DIA = 3.0       # 推定
CABLE_BEND = 12.0   # 推定（u.FL ケーブルの最小曲げ半径ぶんの逃げ）


def model() -> cq.Workplane:
    """基板下面を z=0。カードエッジは -Y 側."""
    pcb = cq.Workplane("XY").box(PCB_W, PCB_L, PCB_T, centered=(True, True, False))
    shield = (
        cq.Workplane("XY")
        .box(PCB_W - 3, PCB_L - 10, COMP_H, centered=(True, True, False))
        .translate((0, 2.0, PCB_T))
    )
    ufl = cq.Workplane("XY").circle(UFL_DIA / 2).extrude(UFL_H)
    a = ufl.translate((-7.0, PCB_L / 2 - 4.0, PCB_T))
    b = ufl.translate((7.0, PCB_L / 2 - 4.0, PCB_T))
    return pcb.union(shield).union(a).union(b)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    return cq.Workplane("XY").box(
        PCB_W + 2 * c,
        PCB_L + 2 * c,
        PCB_T + COMP_H + UFL_H + CABLE_BEND + 2 * c,
        centered=(True, True, False),
    ).translate((0, 0, -c))


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Quectel EG25-G", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=f"形態が未確定（{FORM_FACTOR}）。全寸法が推定・要実測",
    )
