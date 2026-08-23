"""9. fov — カメラの視野を筐体が遮っていないか.

設計が `VIEW_CONES` で視野円錐を宣言すると、**印刷される部品と内蔵部品の両方**を
円錐とブーリアン積して、食い込みを実測する。

対角 76 度クラスの広角では、**真っ直ぐな筒は L < 1.28 r でしか成立しない**
（`Cone.max_straight_tube_length()`）。防犯カメラの筒が長いのは望遠寄りの
狭い視野だからで、この構成では同じ形にできない。短くて末広がりの形になる。
"""

from __future__ import annotations

import numpy as np

from . import FAIL, PASS, SKIP, CheckResult, register


@register("fov")
def check(ctx) -> CheckResult:
    cones = list(getattr(ctx.module, "VIEW_CONES", []) or [])
    if not cones:
        return CheckResult(
            "fov", SKIP, "VIEW_CONES が未宣言（視野を持つ設計ではない）",
            {"cones": 0}, limits=LIMITS,
        )

    tol = float(ctx.config("fov_volume_tol_mm3", 1e-3))
    targets = [("printed", ctx.shape)] + [(c.name, c.shape) for c in ctx.components]

    rows = []
    worst_deg = 0.0
    total = 0.0
    for cone in cones:
        cone_solid = cone.solid()
        for name, shape in targets:
            try:
                hit = shape.intersect(cone_solid)
                vol = float(hit.Volume()) if hit is not None else 0.0
            except Exception as exc:
                rows.append({"cone": cone.name, "obstruction": name,
                             "volume_mm3": "ERROR", "intrusion_deg": "-",
                             "note": type(exc).__name__})
                continue
            if vol <= tol:
                continue
            # どれだけ食い込んでいるか = 軸に最も近い点の角度と、半角との差
            angles = [cone.angle_of((v.X, v.Y, v.Z)) for v in hit.Vertices()]
            deepest = min(angles) if angles else cone.half_angle_deg
            intrusion = max(cone.half_angle_deg - deepest, 0.0)
            worst_deg = max(worst_deg, intrusion)
            total += vol
            bb = hit.BoundingBox()
            rows.append({
                "cone": cone.name,
                "obstruction": name,
                "volume_mm3": round(vol, 2),
                "intrusion_deg": round(intrusion, 2),
                "note": f"最深角 {deepest:.1f} 度 / 中心 "
                        f"({bb.center.x:.1f}, {bb.center.y:.1f}, {bb.center.z:.1f})",
            })

    m = {
        "cones": len(cones),
        "half_angle_deg": [round(c.half_angle_deg, 2) for c in cones],
        "obstructions": len(rows),
        "blocked_volume_mm3": round(total, 2),
        "max_intrusion_deg": round(worst_deg, 2),
    }
    for c in cones:
        m[f"{c.name}: L/r 上限（真っ直ぐな筒）"] = round(
            c.max_straight_tube_length(1.0), 3)
    cols = ["cone", "obstruction", "volume_mm3", "intrusion_deg", "note"]
    details = [f"{c.name}: {c.note}" for c in cones if c.note]

    if rows:
        return CheckResult(
            "fov", FAIL,
            f"視野を {len(rows)} 箇所で遮っている"
            f"（最大 {worst_deg:.2f} 度 / 合計 {total:.1f} mm3）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS,
        )
    return CheckResult(
        "fov", PASS,
        f"視野円錐 {len(cones)} 本を遮る構造なし"
        f"（半角 {', '.join(f'{c.half_angle_deg:.1f}' for c in cones)} 度）",
        m, details=details, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 円錐は 1 本の直円錐でしか表せない。実際のセンサは長方形なので、"
    "対角の円錐で見ると四隅の外側を過剰に空けることになる（判定は安全側）。"
    "頂点をセンサ面に置いているのは入射瞳の位置が未測定のためで、"
    "実際の視野はこれより狭い可能性がある。"
    "**レンズの諸元（焦点距離・センサ対角）自体が要検証**で、"
    "そこが違えば結論も変わる（docs/window-options.md 参照）。"
    "透明な窓材は「遮っている」と判定される（材料の透過は見ていない）ので、"
    "窓そのものは COMPONENTS に入れないこと。"
)
