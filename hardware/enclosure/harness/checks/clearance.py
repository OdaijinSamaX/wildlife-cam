"""5. clearance — 内蔵部品の外形 + クリアランスが筐体と干渉しないか.

各 Component の envelope(clearance) と筐体ソリッドのブーリアン積を取る。
envelope は部品側が寸法から作り直すので、OCC のオフセット演算には依存しない。
"""

from __future__ import annotations

from . import FAIL, PASS, SKIP, WARN, CheckResult, register


@register("clearance")
def check(ctx) -> CheckResult:
    comps = ctx.components
    clearance = float(ctx.config("component_clearance_mm", 0.4))
    tol = float(ctx.config("clearance_volume_tol_mm3", 1e-3))

    if not comps:
        return CheckResult(
            "clearance", SKIP, "COMPONENTS が空（内蔵部品の指定なし）",
            {"components": 0, "clearance_mm": clearance}, limits=LIMITS,
        )

    shell = ctx.shape
    rows = []
    bad = 0
    approx = 0
    for c in comps:
        env = c.envelope(clearance)
        try:
            hit = shell.intersect(env)
            vol = float(hit.Volume()) if hit is not None else 0.0
        except Exception as exc:
            rows.append(
                {"component": c.name, "overlap_mm3": "ERROR", "verdict": type(exc).__name__}
            )
            bad += 1
            continue
        try:
            raw = shell.intersect(c.shape)
            raw_vol = float(raw.Volume()) if raw is not None else 0.0
        except Exception:
            raw_vol = float("nan")
        verdict = "OK"
        if raw_vol > tol:
            verdict = "実体が干渉"
            bad += 1
        elif vol > tol:
            verdict = f"クリアランス {clearance} mm 不足"
            bad += 1
        if c.envelope_fn is None:
            approx += 1
        rows.append(
            {
                "component": c.name,
                "overlap_mm3": round(vol, 4),
                "solid_overlap_mm3": round(raw_vol, 4) if raw_vol == raw_vol else "ERROR",
                "envelope": "厳密" if c.envelope_fn is not None else "bbox 近似",
                "verdict": verdict,
            }
        )

    m = {
        "components": len(comps),
        "clearance_mm": clearance,
        "violations": bad,
        "bbox_approximated_envelopes": approx,
    }
    cols = ["component", "overlap_mm3", "solid_overlap_mm3", "envelope", "verdict"]
    if bad:
        return CheckResult(
            "clearance", FAIL, f"{bad} 個の部品でクリアランス不足", m,
            table=rows, table_columns=cols, limits=LIMITS,
        )
    status = WARN if approx else PASS
    note = "（うち bbox 近似 %d 個）" % approx if approx else ""
    return CheckResult(
        "clearance", status,
        f"部品 {len(comps)} 個すべて {clearance} mm のクリアランスを確保{note}",
        m, table=rows, table_columns=cols, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 部品の envelope が実物より小さければ当然すり抜ける（parts/ の "
    "推定寸法に依存）。配線・コネクタの抜き差しスペース・組立時の斜め挿入は"
    "見ていない。COMPONENTS に置かれていない部品は存在しないものとして扱う。"
)
