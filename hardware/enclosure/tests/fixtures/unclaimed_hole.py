"""layout チェックの「宣言し忘れ」検出を確かめるための最小の設計.

板に穴を 2 つ開けるが、claim は 1 つしか宣言しない。
`declare_both` を True にすると両方宣言する（正常系）。
"""

import cadquery as cq

from harness import feature

DESIGN_NAME = "unclaimed_hole"

PARAMS = {
    "plate_l": 40.0,
    "plate_w": 20.0,
    "plate_t": 5.0,
    "hole_dia": 5.0,
    "hole_x": 12.0,
    "declare_both": False,
    "margin": 0.8,
}

PRINT_ORIENTATION = {"rotate": (0, 0, 0)}
COMPONENTS = []
CHECK_CONFIG = {"min_wall_mm": 1.6}


def features(p=PARAMS):
    out = [
        feature.cylinder("hole_left", (-p["hole_x"], 0.0), p["hole_dia"],
                         0.0, p["plate_t"], margin=p["margin"])
    ]
    if p["declare_both"]:
        out.append(
            feature.cylinder("hole_right", (p["hole_x"], 0.0), p["hole_dia"],
                             0.0, p["plate_t"], margin=p["margin"])
        )
    return out


def build(p=PARAMS):
    plate = cq.Workplane("XY").box(
        p["plate_l"], p["plate_w"], p["plate_t"], centered=(True, True, False)
    )
    for sx in (-1, 1):
        plate = plate.cut(
            cq.Workplane("XY").circle(p["hole_dia"] / 2).extrude(p["plate_t"] + 2)
            .translate((sx * p["hole_x"], 0.0, -1.0))
        )
    return plate
