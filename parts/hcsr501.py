"""HC-SR501 PIR モーションセンサ.

**この部品の寸法はすべて推定（概寸）である。** 出回っているクローンで実寸が違うので、
実物が来たら必ずノギスで測って差し替えること。差し替えたら DIM_SOURCE を
"measured:YYYY-MM-DD" に変え、pir_bezel.py を再チェックする。

推定値（要実測）:
  基板 32 x 24 mm / 厚み 1.2 mm
  フレネルドーム φ23 / フランジ上面からの高さ 8 mm（うち円筒スカート 5 mm）
  取付穴 2 個 φ2.0 / ピッチ 28 mm（基板長手方向）
  背面の実装部品高さ 9 mm（トリマ 2 個・ジャンパ・レギュレータ）

重要な設計前提（動かさないこと）:
  PIR は遠赤外を見るのでアクリルや PC の窓を透過しない。窓を張る構成は成立しない。
  ドームは基板に対して密封されていないので、シール面はドームのフランジと筐体壁の
  間に作る（基板側を筐体内側に置く）。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "estimated"

PCB_L = 32.0        # 推定（要実測）
PCB_W = 24.0        # 推定（要実測）
PCB_T = 1.2         # 推定（要実測）
DOME_DIA = 23.0     # 推定（要実測）
DOME_H = 8.0        # 推定（要実測）フランジ上面からドーム頂点まで
SKIRT_H = 5.0       # 推定（要実測）ドーム根元の円筒部。ここがラジアルシール面になる
FLANGE_DIA = 24.6   # 推定（要実測）ドーム根元のツバ。O リング押さえ面に使う
FLANGE_T = 1.0      # 推定（要実測）
HOLE_DIA = 2.0      # 推定（要実測）
HOLE_PITCH = 28.0   # 推定（要実測）
BACK_COMP_H = 9.0   # 推定（要実測）トリマ・ジャンパ・レギュレータ


def hole_positions() -> list[tuple[float, float]]:
    return [(-HOLE_PITCH / 2, 0.0), (HOLE_PITCH / 2, 0.0)]


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
    flange = cq.Workplane("XY").circle(FLANGE_DIA / 2).extrude(FLANGE_T)
    # 円筒スカート + 球冠。球冠の半径は (r^2 + h^2) / (2h) から出す。
    cap_h = DOME_H - SKIRT_H
    r = DOME_DIA / 2
    sphere_r = (r * r + cap_h * cap_h) / (2 * cap_h)
    z_skirt_top = FLANGE_T + SKIRT_H
    skirt = cq.Workplane("XY").circle(r).extrude(z_skirt_top)
    cap = (
        cq.Workplane("XY")
        .sphere(sphere_r)
        .translate((0, 0, z_skirt_top + cap_h - sphere_r))
        .intersect(
            cq.Workplane("XY")
            .circle(r)
            .extrude(cap_h)
            .translate((0, 0, z_skirt_top))
        )
    )
    dome = skirt.union(cap)
    back = (
        cq.Workplane("XY")
        .box(PCB_L - 4, PCB_W - 4, BACK_COMP_H, centered=(True, True, False))
        .translate((0, 0, -PCB_T - BACK_COMP_H))
    )
    return pcb.union(flange).union(dome).union(back)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """段付きの keep-out。

    基板前面 (z=0) より上には基板ぶんのクリアランスを足さない。ベゼルの端面で
    基板を押さえる構成では、そこは「意図した接触面」だから。
    フランジ部とドーム部は径が違うので分けて包む（一括で包むと、ドームを
    通すためのベゼル内径がフランジ径に引きずられて過大になる）。
    """
    c = clearance
    body = cq.Workplane("XY").box(
        PCB_L + 2 * c, PCB_W + 2 * c, PCB_T + BACK_COMP_H + c,
        centered=(True, True, False),
    ).translate((0, 0, -PCB_T - BACK_COMP_H - c))
    flange = cq.Workplane("XY").circle(FLANGE_DIA / 2 + c).extrude(FLANGE_T)
    dome = (
        cq.Workplane("XY")
        .circle(DOME_DIA / 2 + c)
        .extrude(DOME_H + c)
        .translate((0, 0, FLANGE_T))
    )
    return body.union(flange).union(dome)


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "HC-SR501 PIR", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="全寸法が推定。実測待ち（基板 32x24 / ドーム φ23 / 穴ピッチ 28）",
    )
