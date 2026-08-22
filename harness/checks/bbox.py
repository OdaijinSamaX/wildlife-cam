"""3. bbox — 造形サイズ枠に収まるか.

造形姿勢 (PRINT_ORIENTATION) を適用し、ビルドプレートに落としてから測る。
"""

from __future__ import annotations

from . import FAIL, PASS, CheckResult, register


@register("bbox")
def check(ctx) -> CheckResult:
    limit = tuple(float(v) for v in ctx.config("max_bbox_mm", (256.0, 256.0, 256.0)))
    bb = ctx.oriented_shape.BoundingBox()
    dims = (bb.xlen, bb.ylen, bb.zlen)

    over = [d > l for d, l in zip(dims, limit)]
    m = {
        "x_mm": round(dims[0], 3),
        "y_mm": round(dims[1], 3),
        "z_mm": round(dims[2], 3),
        "limit_mm": list(limit),
        "margin_mm": [round(l - d, 3) for d, l in zip(dims, limit)],
        "print_orientation_deg": list(ctx.print_orientation.get("rotate", (0, 0, 0))),
    }
    summary = (
        f"bbox = {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm "
        f"(枠 {limit[0]:.0f} x {limit[1]:.0f} x {limit[2]:.0f})"
    )
    if any(over):
        axes = "".join(a for a, o in zip("XYZ", over) if o)
        return CheckResult("bbox", FAIL, summary + f" / {axes} 軸が枠を超過", m, limits=LIMITS)
    return CheckResult("bbox", PASS, summary, m, limits=LIMITS)


LIMITS = (
    "見逃すもの: 枠に入っても実際には配置できないケース（プレート端のクリップ、"
    "P1S のパージタワー領域、複数部品の同時配置）。回転は PRINT_ORIENTATION の "
    "1 姿勢しか試さないので、寝かせれば入る形状を FAIL にすることがある。"
)
