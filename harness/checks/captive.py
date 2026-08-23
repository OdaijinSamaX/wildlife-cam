"""11. captive — 捕捉式ねじが本当に「落ちない・開く・座る」か.

**なぜ要るのか。** 現地で保守するのは機械に強くない人で、落としたねじは落ち葉の中で
二度と見つからない（`docs/AGENTS.md` §4.9 原則 1）。だから蝶ねじは蓋に付いたまま
残らなければならない。それは**寸法の連鎖**で成立していて、連鎖が切れると

  - ねじが**抜けて落ちる**（捕捉されない）
  - ねじが相手から**抜けきる前にリテーナが止まって蓋が開かない**
  - ねじ先が引っ込みきらず**蓋を平らに置けない**
  - ねじ先が**下穴の底を突いて**締めたつもりで面圧が出ない

のいずれかになる。**どれも `wall` / `openings` / `layout` / `seal` は見ていない。**
しかも現地に行くまで気づけない。

設計が `CAPTIVE_SCREWS`（`harness.captive.CaptiveScrew` のリスト、または params を
取る関数）を宣言すると、**`build()` した形状にねじ軸と平行なレイを飛ばして**
ポケットの深さと頭の座面の深さを実測し、成立条件を毎回解き直す。

式・記号・見ないものは `harness/captive.py` の docstring、
方式の比較と不採用案は `docs/captive-fasteners.md`。
"""

from __future__ import annotations

from .. import captive as captive_mod
from . import FAIL, PASS, SKIP, WARN, CheckResult, register


@register("captive")
def check(ctx) -> CheckResult:
    screws = getattr(ctx.module, "CAPTIVE_SCREWS", None)
    if callable(screws):
        screws = screws(ctx.params)
    screws = list(screws or [])
    if not screws:
        return CheckResult(
            "captive", SKIP,
            "CAPTIVE_SCREWS が未宣言。**捕捉式のねじが無いのか、宣言し忘れたのかは "
            "この結果からは分からない**（docs/AGENTS.md §4.9 原則 1: 現地で外す"
            "ねじは捕捉式にすること）",
            {"screws": 0}, limits=LIMITS)

    rows, details = [], []
    worst = PASS
    reasons: list[str] = []
    m: dict = {}
    for s in screws:
        r = captive_mod.measure(ctx.mesh, s)
        status, why = r.verdict()
        if status == FAIL:
            worst = FAIL
        elif status == WARN and worst != FAIL:
            worst = WARN
        reasons.extend(f"{s.name}: {w}" for w in why)
        rows.append({
            "screw": s.name,
            "M": f"M{s.thread_dia:g}x{s.screw_len:g}",
            "seat_mm": round(r.seat_mm, 2),
            "pocket_mm": round(r.pocket_mm, 2),
            "travel_mm": round(r.travel, 2),
            "tip_mm": round(r.tip_depth, 2),
            "engage_mm": round(r.engage, 2),
            "protrude_mm": round(r.protrude, 2),
            "gap_mm": round(s.gap_mm, 2),
            "verdict": status,
        })
        m[f"{s.name}: 後退できる量 travel [mm]"] = round(r.travel, 2)
        m[f"{s.name}: 噛み合い engage [mm]"] = round(r.engage, 2)
        m[f"{s.name}: 緩めきったときの出しろ [mm]"] = round(r.protrude, 2)
        if s.note:
            details.append(f"{s.name}: {s.note}")

    m["ねじ本数"] = len(screws)
    cols = ["screw", "M", "seat_mm", "pocket_mm", "travel_mm", "tip_mm",
            "engage_mm", "protrude_mm", "gap_mm", "verdict"]
    details.extend(reasons)

    if worst == FAIL:
        return CheckResult(
            "captive", FAIL,
            f"捕捉が成立しないねじが {sum(1 for r in rows if r['verdict'] == FAIL)} 本"
            f"（{reasons[0] if reasons else ''}）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    if worst == WARN:
        return CheckResult(
            "captive", WARN,
            f"捕捉は成立するが余裕が乏しい（{reasons[0] if reasons else ''}）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    return CheckResult(
        "captive", PASS,
        f"ねじ {len(screws)} 本すべてが「落ちない・抜けきる・平らに座る」を満たす",
        m, details=details, table=rows, table_columns=cols, limits=LIMITS)


LIMITS = (
    "見逃すもの: **リテーナの保持力**。押しナットや止め輪が何 N で抜けるかは"
    "カタログ値も実測も入れていない。ここで見ているのは**寸法の連鎖だけ**である。"
    "**リテーナがねじ山の上を歩いて位置がずれる**失敗も見ていない"
    "（ゴムの O リングやねじ込みナットで起きる。止め輪・押しナットは軸方向の止めなので"
    "歩かないが、それは形式の選択であってここで検証してはいない）。"
    "**リテーナの厚みは申告値**（実測ではない）。厚いリテーナを使うと逃げがそのぶん減る。"
    "ねじの実長のばらつき（±0.5 mm 程度）、ヒートセットインサートの座面が沈む/"
    "飛び出す量、蓋の反りは入っていない。**噛み合いが数 mm しか無い設計では、"
    "この積み上げ公差が効く。**"
    "リテーナがポケットに実際に**入る**かは見ていない（径はカタログの推定値）。"
    "**面圧への影響も見ていない**。捕捉ポケットを彫れば蓋の断面は痩せるので、"
    "`seal` を必ず併せて回すこと。"
)
