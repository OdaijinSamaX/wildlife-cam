"""13. underside — 基板の**下**に出ている実装部品が受け面に当たらないか.

**なぜ 13 個目が要ったのか。** `clearance` は部品の envelope と筐体の積を見るが、
**基板を受ける座面には envelope を太らせない**という規約がある（AGENTS.md §4）。
基板はボスの天面に接するのが正しいからで、太らせると正しい設計が FAIL になる。
**その免除が、基板の下にぶら下がっているものを丸ごと飲み込む。**

実際に起きたこと（2026-08-23）: CSI レスキューブラケットは Pi の CSI 側の取付穴
2 個を**ねじ + ナット**で占有していて、**基板下面から 2.7 mm 出ている**。
`parts/pi_zero_2w.BOT_COMP_H = 0.4` / `CAN_SIT_FLAT = True` を前提に立てたボスは
0.4 mm ぶんしか逃げていない。**基板が座らない。**
`wall` も `interference` も `layout` も `openings` も、これを見ていない。

設計が `UNDER_BOARD`（`harness.underside.UnderBoard` のリスト、または params を
取る関数）を宣言すると、**`build()` した形状に基板の法線と平行なレイを footprint の
格子状に飛ばして**隙間を実測し、`gap >= 突出量 + クリアランス` を毎回解き直す。

式と「見ないもの」は `harness/underside.py` の docstring。
"""

from __future__ import annotations

from .. import underside as under_mod
from . import FAIL, PASS, SKIP, WARN, CheckResult, register


def _fmt(v: float) -> float | str:
    return "材料なし" if v >= under_mod.FAR else round(v, 2)


@register("underside")
def check(ctx) -> CheckResult:
    declared = hasattr(ctx.module, "UNDER_BOARD")
    specs = getattr(ctx.module, "UNDER_BOARD", None)
    if callable(specs):
        specs = specs(ctx.params)
    specs = list(specs or [])
    if not specs:
        # **「宣言して空」と「宣言し忘れ」を区別する。**
        # 前者は「考えた結果、基板の下に出ているものは無い」という設計者の主張で、
        # 後者は何も分かっていない状態。同じ SKIP でも意味がまったく違う。
        if declared:
            return CheckResult(
                "underside", SKIP,
                "UNDER_BOARD = [] と**明示的に宣言**されている"
                "（基板の下に出ている実装部品は無い、という設計判断）。"
                "**理由が docstring に書いてあるか人が確かめること**",
                {"宣言した突起の数": 0, "宣言の有無": "あり（空）"}, limits=LIMITS)
        return CheckResult(
            "underside", SKIP,
            "UNDER_BOARD が**未宣言**。**基板の下に出ている実装部品が無いのか、"
            "宣言し忘れたのかはこの結果からは分からない**"
            "（基板を載せる設計は必ず宣言すること。AGENTS.md §6）",
            {"宣言した突起の数": 0, "宣言の有無": "なし"}, limits=LIMITS)

    rows, details, reasons = [], [], []
    worst = PASS
    m: dict = {}
    for s in specs:
        r = under_mod.measure(ctx.mesh, s)
        status, why = r.verdict()
        if status == FAIL:
            worst = FAIL
        elif status == WARN and worst != FAIL:
            worst = WARN
        reasons.extend(f"{s.name}: {w}" for w in why)
        rows.append({
            "突起": s.name,
            "axis": s.axis,
            "基板下面": round(s.board, 2),
            "突出_mm": round(s.protrusion_mm, 2),
            "要求_mm": round(s.required, 2),
            "実測隙間_mm": _fmt(r.gap_mm),
            "材料なしの割合": f"{r.open_frac * 100:.0f}%",
            "verdict": status,
        })
        m[f"{s.name}: 実測の隙間 [mm]"] = _fmt(r.gap_mm)
        m[f"{s.name}: 要求 (突出 + 逃げ) [mm]"] = round(s.required, 2)
        if s.note:
            details.append(f"{s.name}: {s.note}")

    m["宣言した突起の数"] = len(specs)
    cols = ["突起", "axis", "基板下面", "突出_mm", "要求_mm",
            "実測隙間_mm", "材料なしの割合", "verdict"]
    details.extend(reasons)

    if worst == FAIL:
        n = sum(1 for r in rows if r["verdict"] == FAIL)
        return CheckResult(
            "underside", FAIL,
            f"基板の下の突起 {n} 個が受け面に当たる（{reasons[0] if reasons else ''}）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    if worst == WARN:
        return CheckResult(
            "underside", WARN,
            f"逃げは足りているが余裕が乏しい（{reasons[0] if reasons else ''}）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    return CheckResult(
        "underside", PASS,
        f"基板の下の突起 {len(specs)} 個すべてが受け面に当たらない",
        m, details=details, table=rows, table_columns=cols, limits=LIMITS)


LIMITS = (
    "見逃すもの: **突出量そのものは申告値**（部品側の実測）で、ここでは測っていない。"
    "部品の数字が嘘なら通ってしまう。**footprint の外は見ない**ので、"
    "**宣言し忘れた突起は検出できない**（`layout` の claim と同じ弱点）。"
    "締結したときに基板がたわんで下がる量、基板そのものの反り、"
    "熱でボスの天面がクリープして沈む量も入っていない。"
    "格子は既定 5 x 5 なので、**格子の目より細いリブや突起は通り抜ける。**"
)
