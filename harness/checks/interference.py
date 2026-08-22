"""4. interference — アセンブリ内のソリッド同士が食い込んでいないか.

build() が返した形状の中のソリッドを総当たりでブーリアン積し、体積が 0 かを見る。
"""

from __future__ import annotations

from itertools import combinations

from . import FAIL, PASS, CheckResult, register


@register("interference")
def check(ctx) -> CheckResult:
    solids = ctx.named_solids
    tol = float(ctx.config("interference_volume_tol_mm3", 1e-3))

    if len(solids) < 2:
        return CheckResult(
            "interference", PASS,
            "ソリッドが 1 個なので自己干渉なし",
            {"solids": len(solids)},
            limits=LIMITS,
        )

    rows = []
    worst = 0.0
    for (na, sa), (nb, sb) in combinations(solids, 2):
        try:
            common = sa.intersect(sb)
            vol = float(common.Volume()) if common is not None else 0.0
        except Exception as exc:
            rows.append({"a": na, "b": nb, "overlap_mm3": "ERROR", "note": type(exc).__name__})
            continue
        worst = max(worst, vol)
        if vol > tol:
            rows.append({"a": na, "b": nb, "overlap_mm3": round(vol, 4), "note": "干渉"})

    m = {
        "solids": len(solids),
        "pairs_checked": len(list(combinations(range(len(solids)), 2))),
        "max_overlap_mm3": round(worst, 4),
        "tolerance_mm3": tol,
        "interfering_pairs": len([r for r in rows if r.get("note") == "干渉"]),
    }
    if any(r.get("note") == "干渉" for r in rows):
        return CheckResult(
            "interference", FAIL,
            f"ソリッドが干渉 (最大 {worst:.3f} mm3)",
            m, table=rows, table_columns=["a", "b", "overlap_mm3", "note"], limits=LIMITS,
        )
    return CheckResult(
        "interference", PASS,
        f"ソリッド {len(solids)} 個、干渉なし (最大重なり {worst:.4f} mm3)",
        m, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 面が完全に一致して接触しているだけの状態（体積 0 なので PASS になる）。"
    "ソリッド数の 2 乗でブーリアンを回すので、数十個を超えると重い。"
)
