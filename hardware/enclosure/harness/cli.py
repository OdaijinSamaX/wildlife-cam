"""コマンドライン入口.

    uv run python -m harness check designs/wildlife_cam/fit_coupon.py
    uv run python -m harness check <design.py> --only wall,openings --no-render
    uv run python -m harness list
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import build as build_mod
from . import checks as checks_mod
from . import render as render_mod
from . import report as report_mod
from .design import load_design

REPO_ROOT = Path(__file__).resolve().parent.parent


def cmd_check(args) -> int:
    ctx = load_design(args.design)
    out_dir = Path(args.out or (REPO_ROOT / "out" / ctx.name))
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.pitch:
        ctx.check_config["voxel_pitch_mm"] = args.pitch

    artifacts = {}
    if not args.no_export:
        artifacts = build_mod.export_all(ctx, out_dir)

    render = None
    if not args.no_render:
        render = render_mod.render_design(ctx, out_dir)

    only = [s.strip() for s in args.only.split(",")] if args.only else None
    results = checks_mod.run_all(ctx, only=only)
    path = report_mod.write_report(ctx, results, out_dir, artifacts, render)

    status = report_mod.overall_status(results)
    for r in results:
        print(f"{r.status:5s}  {r.name:13s} {r.summary}")
    for w in ctx.warnings:
        print(f"WARN   {w}")
    print(f"\n総合: {status}")
    print(f"レポート: {path}")
    return 0 if status != "FAIL" else 1


def cmd_list(args) -> int:
    for p in sorted((REPO_ROOT / "designs").rglob("*.py")):
        if p.name.startswith("_"):
            continue
        print(p.relative_to(REPO_ROOT))
    print()
    print("チェック:", ", ".join(checks_mod.ORDER))
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="harness", description="筐体設計ハーネス")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("check", help="build + render + checks + report")
    c.add_argument("design", help="設計スクリプトのパス")
    c.add_argument("--out", help="出力ディレクトリ (既定 out/<design>)")
    c.add_argument("--only", help="実行するチェックをカンマ区切りで指定")
    c.add_argument("--no-render", action="store_true", help="PNG を作らない")
    c.add_argument("--no-export", action="store_true", help="STEP/STL/3MF を作らない")
    c.add_argument("--pitch", type=float, help="ボクセルピッチ mm を上書き")
    c.set_defaults(func=cmd_check)

    l = sub.add_parser("list", help="設計とチェックの一覧")
    l.set_defaults(func=cmd_list)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
