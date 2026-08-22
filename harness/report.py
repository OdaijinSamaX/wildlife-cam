"""out/<design>/report.md の生成.

画像・実測値・PASS/FAIL を 1 枚にまとめる。AI が次の一手を決めるための紙でもあるので、
「何を見逃すか」(各チェックの limits) も必ず載せる。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .checks import BAD, CheckResult

BADGE = {"PASS": "✅ PASS", "FAIL": "❌ FAIL", "WARN": "⚠️ WARN", "SKIP": "➖ SKIP", "ERROR": "💥 ERROR"}


def _fmt(v) -> str:
    if isinstance(v, float):
        return f"{v:.4g}"
    if isinstance(v, (list, tuple)):
        return ", ".join(_fmt(x) for x in v)
    if v is None:
        return "-"
    if isinstance(v, bool):
        return "yes" if v else "no"
    return str(v)


def _table(rows, columns) -> list[str]:
    if not rows:
        return []
    cols = columns or list(rows[0].keys())
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---"] * len(cols)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(_fmt(r.get(c, "")) for c in cols) + " |")
    return out


def overall_status(results: list[CheckResult]) -> str:
    if any(r.status in BAD for r in results):
        return "FAIL"
    if any(r.status == "WARN" for r in results):
        return "WARN"
    return "PASS"


def write_report(
    ctx,
    results: list[CheckResult],
    out_dir: str | Path,
    artifacts: dict[str, Path] | None = None,
    render=None,
) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    L: list[str] = []
    status = overall_status(results)

    L.append(f"# {ctx.name} — 設計チェックレポート")
    L.append("")
    L.append(f"**総合判定: {BADGE[status]}**")
    L.append("")
    L.append(f"- 設計ファイル: `{ctx.path.relative_to(Path.cwd()) if str(ctx.path).startswith(str(Path.cwd())) else ctx.path}`")
    L.append(f"- 生成日時: {datetime.now().isoformat(timespec='seconds')}")
    L.append(f"- 造形姿勢 (rotate): {_fmt(ctx.print_orientation.get('rotate', (0, 0, 0)))}")
    if render is not None:
        L.append(f"- レンダ方式: `{render.backend}`")
    L.append("")

    L.append("## 判定サマリ")
    L.append("")
    L.append("| チェック | 判定 | 要約 |")
    L.append("|---|---|---|")
    for r in results:
        L.append(f"| {r.name} | {BADGE.get(r.status, r.status)} | {r.summary} |")
    L.append("")

    if ctx.warnings or (render and render.notes):
        L.append("## 注意")
        L.append("")
        for w in ctx.warnings:
            L.append(f"- {w}")
        for w in (render.notes if render else []):
            L.append(f"- {w}")
        L.append("")

    if artifacts:
        L.append("## 出力ファイル")
        L.append("")
        for k, p in artifacts.items():
            L.append(f"- {k.upper()}: `{Path(p).name}`")
        L.append("")

    if render and render.files:
        L.append("## 外観")
        L.append("")
        views = [f for f in render.files if not f.name.startswith("section_")]
        secs = [f for f in render.files if f.name.startswith("section_")]
        for f in views:
            L.append(f"### {f.stem}")
            L.append("")
            L.append(f"![{f.stem}](views/{f.name})")
            L.append("")
        if secs:
            L.append("## 断面")
            L.append("")
            L.append("防水筐体は溝と肉厚が中に隠れる。外観だけで判断しないこと。")
            L.append("")
            for f in secs:
                L.append(f"### {f.stem}")
                L.append("")
                L.append(f"![{f.stem}](views/{f.name})")
                L.append("")

    L.append("## 各チェックの詳細")
    L.append("")
    for r in results:
        L.append(f"### {r.name} — {BADGE.get(r.status, r.status)}")
        L.append("")
        L.append(r.summary)
        L.append("")
        if r.measurements:
            L.append("| 項目 | 値 |")
            L.append("|---|---|")
            for k, v in r.measurements.items():
                L.append(f"| {k} | {_fmt(v)} |")
            L.append("")
        if r.details:
            for d in r.details:
                L.append(f"- {d}")
            L.append("")
        if r.table:
            L.extend(_table(r.table, r.table_columns))
            L.append("")
        if r.limits:
            L.append(f"> **限界**: {r.limits}")
            L.append("")

    L.append("## PARAMS")
    L.append("")
    L.append("| キー | 値 |")
    L.append("|---|---|")
    for k, v in ctx.params.items():
        L.append(f"| {k} | {_fmt(v)} |")
    L.append("")

    if ctx.components:
        L.append("## COMPONENTS")
        L.append("")
        L.append("| 部品 | 寸法の出所 | 備考 |")
        L.append("|---|---|---|")
        for c in ctx.components:
            L.append(f"| {c.name} | {c.dimension_source} | {c.notes} |")
        L.append("")

    path = out_dir / "report.md"
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
    return path
