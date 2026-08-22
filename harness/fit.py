"""寸法補正テーブル.

**設計スクリプトには「印刷後にこうなってほしい寸法（狙い寸法）」を書く。**
補正はここで一箇所にまとめて適用する。設計者が式の中で `+0.3` などと
足し引きするのは禁止（`docs/AGENTS.md`）。

## 使い方

```python
from harness import fit

FIT_TABLE = fit.ASA_P1S            # どのテーブルで刷るかを設計が宣言する

def build(p=PARAMS):
    # p["shaft_dias"] には狙い寸法 10.1 が入っている
    cq.Workplane("XY").circle(FIT_TABLE.hole(p["shaft_dias"][0]) / 2)
```

## 2 つのモード

同じ `build()` を 2 通りに評価する。切り替えるのは `load_design` の仕事で、
設計側は意識しなくてよい。

| モード | `hole(10.1)` の戻り値 | 何に使うか |
|---|---|---|
| `target` | **10.1**（狙い寸法そのまま） | チェックとレンダ。印刷後の形を検証したいので |
| `print`  | **10.4**（補正後） | STL / 3MF の書き出し。スライサに渡す形 |

こうしないと `clearance` や `wall` が「補正で膨らんだ穴」を測ってしまい、
実物と違う数字で PASS/FAIL を出すことになる。

## テーブルは材料と条件に紐づく

補正値は **材料・機種・ノズル径・造形姿勢** の組に対してしか意味がない。
別材料で刷るなら測り直してテーブルを追加すること。手順は
`designs/wildlife_cam/fit_coupon.md` にある。
"""

from __future__ import annotations

import math
from contextlib import contextmanager
from dataclasses import dataclass, field

WALL = "wall"
HOLE = "hole"
BOSS = "boss"
NONE_KIND = "uncompensated"

MODE_TARGET = "target"
MODE_PRINT = "print"


@dataclass(frozen=True)
class Rule:
    """ある種類・ある寸法帯に対する補正量.

    delta は **図面に足す量**。実測が狙いより 0.30 小さく出たなら delta = +0.30。
    """

    kind: str
    lo: float
    hi: float          # 上限は含まない
    delta: float
    samples: int = 0
    provisional: bool = False
    note: str = ""

    def covers(self, value: float) -> bool:
        return self.lo <= value < self.hi

    def distance(self, value: float) -> float:
        if self.covers(value):
            return 0.0
        return min(abs(value - self.lo), abs(value - self.hi))


@dataclass
class Applied:
    """1 回の補正の記録。report にそのまま出る."""

    kind: str
    target: float
    drawn: float
    delta: float
    provisional: bool = False
    extrapolated: bool = False
    note: str = ""

    @property
    def flags(self) -> str:
        f = []
        if self.provisional:
            f.append("暫定")
        if self.extrapolated:
            f.append("外挿")
        if self.kind == NONE_KIND:
            f.append("無補正")
        return " / ".join(f) or "-"


@dataclass
class FitTable:
    id: str
    material: str
    printer: str
    nozzle_mm: float
    layer_mm: float
    orientation: str
    measured_on: str
    source: str
    rules: tuple[Rule, ...] = ()
    note: str = ""
    identity: bool = False

    mode: str = MODE_PRINT
    log: list[Applied] = field(default_factory=list, repr=False)

    # --- provenance -------------------------------------------------------
    @property
    def provenance(self) -> str:
        return (
            f"{self.material} / {self.printer} / ノズル {self.nozzle_mm} mm / "
            f"層 {self.layer_mm} mm / {self.orientation} / 実測 {self.measured_on}"
        )

    # --- モード -----------------------------------------------------------
    @contextmanager
    def using(self, mode: str):
        prev = self.mode
        self.mode = mode
        try:
            yield self
        finally:
            self.mode = prev

    def reset_log(self) -> None:
        self.log.clear()

    # --- 適用 -------------------------------------------------------------
    def _apply(self, kind: str, target: float) -> float:
        if self.identity:
            rec = Applied(kind, target, target, 0.0, note=self.note or "補正なし")
            self.log.append(rec)
            return target

        candidates = [r for r in self.rules if r.kind == kind]
        exact = [r for r in candidates if r.covers(target)]
        if exact:
            rule, extrapolated = exact[0], False
        elif candidates:
            rule = min(candidates, key=lambda r: r.distance(target))
            extrapolated = True
        else:
            rec = Applied(kind, target, target, 0.0, extrapolated=True,
                          note=f"{kind} の規則がテーブルに無い")
            self.log.append(rec)
            return target

        drawn = round(target + rule.delta, 4)
        rec = Applied(
            kind=kind, target=target, drawn=drawn, delta=rule.delta,
            provisional=rule.provisional, extrapolated=extrapolated,
            note=rule.note if not extrapolated
            else f"{rule.note}（{rule.lo}〜{rule.hi} の規則から外挿）",
        )
        self.log.append(rec)
        return drawn if self.mode == MODE_PRINT else target

    # --- 設計から呼ぶ入口 --------------------------------------------------
    def hole(self, diameter: float) -> float:
        """内径（円筒穴）の狙い直径 -> 図面に描く直径."""
        return self._apply(HOLE, diameter)

    def boss(self, diameter: float) -> float:
        """外形の突起（ピン・ボス）の狙い直径 -> 図面に描く直径."""
        return self._apply(BOSS, diameter)

    def wall(self, thickness: float) -> float:
        """肉厚の狙い値 -> 図面に描く値."""
        return self._apply(WALL, thickness)

    def uncompensated(self, value: float, why: str) -> float:
        """テーブルに根拠が無いので補正しない、と明示的に宣言する.

        黙って素通しするのではなく記録に残す。report に「無補正」として出る。
        """
        self.log.append(Applied(NONE_KIND, value, value, 0.0, note=why))
        return value


# ---------------------------------------------------------------------------
# 実測から起こしたテーブル
# ---------------------------------------------------------------------------

#: 2026-08-22 に fit_coupon v1 を実際に印刷して測った結果から起こしたテーブル。
#: 生の実測値と、そこから delta を導いた計算は
#: designs/wildlife_cam/fit_coupon.md に残してある。
ASA_P1S = FitTable(
    id="asa-p1s-0.4mm-2026-08-22",
    material="ASA",
    printer="Bambu Lab P1S",
    nozzle_mm=0.4,
    layer_mm=0.2,
    orientation="平置き",
    measured_on="2026-08-22",
    source="designs/wildlife_cam/fit_coupon.md",
    rules=(
        Rule(
            kind=WALL, lo=0.0, hi=math.inf, delta=0.0, samples=4,
            note="薄板 0.8/1.2/1.6/2.0 が 4 点とも誤差 0.00。補正不要",
        ),
        Rule(
            kind=HOLE, lo=8.0, hi=math.inf, delta=0.30, samples=4,
            note="軸穴 10.1/10.2/10.3/10.4 が 4 点とも誤差 -0.30 で一定。刻みも一致",
        ),
        Rule(
            kind=HOLE, lo=2.0, hi=5.0, delta=0.25, samples=6, provisional=True,
            note="小穴の誤差は -0.10 〜 -0.30 とばらつく。"
                 "小径の内径はノギスの読み取り確度が低いので暫定値",
        ),
        Rule(
            kind=BOSS, lo=0.0, hi=math.inf, delta=0.25, samples=1,
            note="基準ピン phi10.0 が 9.7〜9.8（採用 9.75）で誤差 -0.25。実測点は 1 種類のみ",
        ),
    ),
    note="fit_coupon v1 の実測から起こした最初のテーブル",
)

#: 補正を入れない、と明示的に宣言するためのテーブル。
#: 「まだ測っていない」ではなく「意図して補正しない」ときに使う。
NONE = FitTable(
    id="none",
    material="-",
    printer="-",
    nozzle_mm=0.0,
    layer_mm=0.0,
    orientation="-",
    measured_on="-",
    source="-",
    identity=True,
    note="補正なし（明示的に宣言）",
)

TABLES: dict[str, FitTable] = {t.id: t for t in (ASA_P1S, NONE)}
DEFAULT = ASA_P1S
