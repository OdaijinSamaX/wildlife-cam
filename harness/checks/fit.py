"""0. fit — 寸法補正テーブルの素性と、実際に適用された補正.

このリポジトリの設計スクリプトは **狙い寸法**（印刷後にこうなってほしい寸法）を
書き、補正は `harness/fit.py` のテーブルが一箇所で当てる。そのテーブルが
どれで、どの寸法にいくら足されたのかを毎回レポートに出して監査できるようにする。

補正値は材料・機種・ノズル径・造形姿勢の組にしか意味がない。だから
テーブルの素性（材料 / 機種 / ノズル / 層厚 / 姿勢 / 実測日）を必ず表示する。
"""

from __future__ import annotations

from . import FAIL, PASS, WARN, CheckResult, register


@register("fit")
def check(ctx) -> CheckResult:
    table = ctx.fit
    if table is None:
        return CheckResult(
            "fit", FAIL,
            "FIT_TABLE が宣言されていない — この設計は寸法補正を通っていない",
            {"table": None},
            details=[
                "設計ファイルに `FIT_TABLE = fit.ASA_P1S` のように宣言すること。",
                "意図して補正しない場合も `FIT_TABLE = fit.NONE` と明示する。",
                "使い方は harness/fit.py の docstring と docs/AGENTS.md を参照。",
            ],
            limits=LIMITS,
        )

    log = ctx.fit_log
    provisional = [a for a in log if a.provisional]
    extrapolated = [a for a in log if a.extrapolated]
    uncompensated = [a for a in log if a.kind == "uncompensated"]

    # 狙い形状と補正済み形状の差。補正が本当に効いているかの実測値。
    tb = ctx.shape.BoundingBox()
    pb = ctx.print_shape.BoundingBox()
    m = {
        "table": table.id,
        "material": table.material,
        "printer": table.printer,
        "nozzle_mm": table.nozzle_mm,
        "layer_mm": table.layer_mm,
        "orientation": table.orientation,
        "measured_on": table.measured_on,
        "source": table.source,
        "applications": len(log),
        "provisional": len(provisional),
        "extrapolated": len(extrapolated),
        "uncompensated": len(uncompensated),
        "target_volume_mm3": round(float(ctx.shape.Volume()), 2),
        "print_volume_mm3": round(float(ctx.print_shape.Volume()), 2),
        "bbox_delta_mm": [
            round(pb.xlen - tb.xlen, 3),
            round(pb.ylen - tb.ylen, 3),
            round(pb.zlen - tb.zlen, 3),
        ],
    }

    # 同じ (種類, 狙い値) は 1 行にまとめる
    seen: dict[tuple[str, float], dict] = {}
    for a in log:
        key = (a.kind, a.target)
        row = seen.get(key)
        if row is None:
            seen[key] = {
                "kind": a.kind,
                "target_mm": a.target,
                "drawn_mm": a.drawn,
                "delta_mm": round(a.delta, 3),
                "flags": a.flags,
                "note": a.note,
                "n": 1,
            }
        else:
            row["n"] += 1
    rows = sorted(seen.values(), key=lambda r: (r["kind"], r["target_mm"]))
    cols = ["kind", "target_mm", "drawn_mm", "delta_mm", "n", "flags", "note"]

    details = [f"テーブル素性: {table.provenance}"]
    if table.source and table.source != "-":
        details.append(f"実測値の出所: `{table.source}`")

    if table.identity:
        return CheckResult(
            "fit", PASS,
            f"補正なし（`{table.id}` を明示的に宣言）— 適用 {len(log)} 件",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS,
        )

    if not log:
        return CheckResult(
            "fit", WARN,
            f"テーブル `{table.id}` を宣言しているが、補正を 1 度も通していない",
            m,
            details=details + [
                "build() の中で FIT_TABLE.hole() / .boss() / .wall() を使っているか確認すること",
            ],
            table=rows, table_columns=cols, limits=LIMITS,
        )

    if provisional or extrapolated or uncompensated:
        parts = []
        if provisional:
            parts.append(f"暫定値 {len(provisional)} 件")
        if extrapolated:
            parts.append(f"外挿 {len(extrapolated)} 件")
        if uncompensated:
            parts.append(f"無補正 {len(uncompensated)} 件")
        return CheckResult(
            "fit", WARN,
            f"`{table.id}` で {len(log)} 件補正 — " + " / ".join(parts) + " を含む",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS,
        )

    return CheckResult(
        "fit", PASS,
        f"`{table.id}` で {len(log)} 件の寸法を補正（暫定・外挿なし）",
        m, details=details, table=rows, table_columns=cols, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 設計が FIT_TABLE を呼ばずに書いた寸法は、当然この表に出ない。"
    "テーブルを網羅的に強制する仕組みではなく、**通した寸法の記録**である。"
    "補正値は材料・機種・ノズル径・造形姿勢の組にしか意味がない。"
    "テーブルの素性と実際の印刷条件が一致しているかは人が確認すること。"
    "溝幅・角穴・ポケットなど、まだ実測していない種類の形状には規則が無い。"
)
