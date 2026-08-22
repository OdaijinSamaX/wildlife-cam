"""内蔵部品のダミー形状（BOM プリミティブ）.

各モジュールは以下を持つ:

    DIM_SOURCE   寸法の出所 ("datasheet" / "measured:YYYY-MM-DD" / "estimated")
    model(**kw)  -> cq.Workplane   実体
    envelope(clearance=0.0, **kw) -> cq.Workplane   外形 + クリアランス
    ENVELOPE     既定クリアランス込みの envelope（dispatch の要求どおり module 変数でも持つ）
    place(at, rotate, **kw) -> harness.component.Component   配置済みの部品

**推定寸法には必ず docstring に「推定」と書くこと。** 実測が入ったら
DIM_SOURCE を "measured:YYYY-MM-DD" に変え、値を差し替える。
"""

from . import (  # noqa: F401
    cable_gland,
    cam_module3,
    eg25g,
    gore_vent,
    hcsr501,
    ir_illuminator,
    m3_heatset,
    oring,
    pi_zero_2w,
)

ALL = [
    pi_zero_2w,
    cam_module3,
    hcsr501,
    eg25g,
    ir_illuminator,
    m3_heatset,
    oring,
    cable_gland,
    gore_vent,
]
