"""チェックの登録と共通の戻り値型.

全てのチェックは PASS/FAIL だけでなく **実測値** を返す。
measurements に入れた値が report.md の表にそのまま出る。
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

PASS = "PASS"
FAIL = "FAIL"
WARN = "WARN"
SKIP = "SKIP"
ERROR = "ERROR"

#: 総合判定を FAIL にするステータス
BAD = (FAIL, ERROR)


@dataclass
class CheckResult:
    name: str
    status: str
    summary: str
    measurements: dict[str, Any] = field(default_factory=dict)
    details: list[str] = field(default_factory=list)
    table: list[dict[str, Any]] | None = None
    table_columns: list[str] | None = None
    limits: str = ""

    @property
    def ok(self) -> bool:
        return self.status not in BAD


REGISTRY: dict[str, Callable[[Any], CheckResult]] = {}
ORDER: list[str] = []


def register(name: str):
    def deco(fn):
        REGISTRY[name] = fn
        if name not in ORDER:
            ORDER.append(name)
        return fn

    return deco


def run_all(ctx, only: Iterable[str] | None = None) -> list[CheckResult]:
    names = list(only) if only else list(ORDER)
    results: list[CheckResult] = []
    for name in names:
        fn = REGISTRY.get(name)
        if fn is None:
            results.append(CheckResult(name, SKIP, f"未登録のチェック: {name}"))
            continue
        try:
            results.append(fn(ctx))
        except Exception as exc:  # チェック自身の事故で全体を止めない
            results.append(
                CheckResult(
                    name,
                    ERROR,
                    f"チェックが例外で停止: {type(exc).__name__}: {exc}",
                    details=traceback.format_exc().strip().splitlines()[-8:],
                )
            )
    return results


from . import bbox, clearance, interference, manifold, openings, overhang, wall  # noqa: E402,F401

#: レポートに出す順序（登録順ではなく意味の順）
ORDER[:] = ["manifold", "wall", "bbox", "interference", "clearance", "overhang", "openings"]
