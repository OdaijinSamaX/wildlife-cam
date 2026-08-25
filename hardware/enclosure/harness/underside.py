"""基板の**下**に出ている実装部品と、それを受ける面のあいだの隙間.

**なぜ要るのか。** `clearance` は部品の envelope と筐体のブーリアン積を見るが、
**基板を受ける座面には envelope を太らせない**という規約がある
（`docs/AGENTS.md` §4「envelope は意図した接触面にはクリアランスを足さない」）。
基板はボスの天面に**接するのが正しい**からで、そこを太らせると正しい設計が
clearance FAIL になってしまう。

ところが**その免除が、基板の下にぶら下がっているものを丸ごと飲み込む。**
座面側の隙間はもともと 0 が正しいことになっているので、そこに 2.7 mm の
ナットがあっても、`clearance` は「意図した接触」としか読まない。

実際に起きたこと（2026-08-23）:

    CSI レスキューブラケットは Pi の CSI 側の取付穴 2 個を
    **ねじ + ナット**で占有していて、**基板下面から 2.7 mm 出ている。**
    `parts/pi_zero_2w.BOT_COMP_H = 0.4` / `CAN_SIT_FLAT = True` を前提に
    立てたボスは 0.4 mm ぶんしか逃げていない。**基板が座らない。**

`wall` は薄肉しか見ない。`interference` は別ソリッド同士しか見ない。
`layout` は 1 つのソリッドの中の claim しか見ない。`openings` は貫通しか見ない。
**12 種のどれも、この失敗を捕まえない。**

## 何を測るか

設計が `UNDER_BOARD` を宣言すると、**`build()` した形状に基板の法線と平行な
レイを footprint の格子状に飛ばして**、

    gap = 基板下面 - 「基板下面**以下**で一番基板に近い材料の座標」

を実測し、`gap >= protrusion + clearance` を要求する。

**PARAMS の数字ではなく形から測る**ので、ボスを 0.5 mm 縮めれば数字が動く。
格子で飛ばすのは、逃げが**部分的にしか彫られていない**（ポケットが小さい /
位置がずれている）ケースを拾うため。1 点だけ見ると真ん中を通り抜けてしまう。

**「以下」であって「より下」ではない。** 受け面が基板下面とちょうど同じ高さに
あるのは「接している = 隙間 0」であって、「もっと下の面までが隙間」ではない。
ここを `depth > 0` で除外すると、その面が飛ばされて嘘の値が出る
（実装当初そう書いて取り逃がした。`tests/test_checks_negative.py` に回帰テストあり）。

**footprint は矩形（既定）と円（`shape="circle"`）から選ぶ。**
六角ナットのような丸い突起を矩形で宣言すると、角が逃げの外へはみ出して誤検出になる。

## ここで見ないもの

  - **突出量そのものは申告値**（部品側の実測）。部品が嘘をつけば通る
  - footprint の外は見ない。**宣言し忘れた突起は検出できない**
  - 締結したときに基板がたわんで下がる量、基板の反り
  - 熱で座面がクリープして沈む量
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}

#: 実質「材料が無い」とみなす距離。レポートにはこの値で頭打ちにして出す。
FAR = 1e6


@dataclass(frozen=True)
class UnderBoard:
    """基板の下に出ている 1 個の突起と、その真下に要る逃げ."""

    name: str
    #: 基板下面の座標（`axis` 方向）
    board: float
    #: 基板下面より下へ出ている量（**部品側の実測値**）
    protrusion_mm: float
    #: `axis` に垂直な 2 座標での中心
    at: tuple[float, float]
    #: 同じ平面での footprint の大きさ。`shape="circle"` なら size[0] が直径
    size: tuple[float, float]
    #: footprint の形。"rect" | "circle"
    #: **六角ナットのような丸い突起を矩形で宣言すると、角が逃げの外へはみ出して
    #: 誤検出になる。** その場合は "circle" を使う（外接円で包む）。
    shape: str = "rect"
    #: 基板の法線。"X" | "Y" | "Z"
    axis: str = "Y"
    #: 基板が座面から見てどちら側にあるか（+1 なら axis の正側）
    sign: int = 1
    #: 突起の先端と受け面のあいだに残したい隙間
    clearance_mm: float = 0.4
    note: str = ""

    @property
    def required(self) -> float:
        return self.protrusion_mm + self.clearance_mm


@dataclass
class UndersideResult:
    spec: UnderBoard
    #: 格子の中で**一番狭かった**隙間
    gap_mm: float
    #: 一番狭かった点（axis に垂直な 2 座標）
    worst_at: tuple[float, float]
    #: 材料がまったく当たらなかった格子点の割合
    open_frac: float
    #: 格子点の数
    samples: int

    def verdict(self) -> tuple[str, list[str]]:
        s = self.spec
        if self.gap_mm >= FAR:
            return "PASS", []
        if self.gap_mm < s.required - 1e-6:
            short = s.required - self.gap_mm
            if self.gap_mm <= 1e-6:
                why = (f"受け面が基板下面に達している（隙間 {self.gap_mm:.2f} mm）。"
                       f"**{s.protrusion_mm:.2f} mm の突起が確実に当たる**")
            else:
                why = (f"隙間 {self.gap_mm:.2f} mm が "
                       f"「突出 {s.protrusion_mm:.2f} + 逃げ {s.clearance_mm:.2f} "
                       f"= {s.required:.2f} mm」に {short:.2f} mm 足りない")
            return "FAIL", [f"{why}（x/z = {self.worst_at[0]:.1f}, {self.worst_at[1]:.1f}）"]
        if self.gap_mm < s.required + 0.2:
            return "WARN", [f"隙間 {self.gap_mm:.2f} mm は要求 {s.required:.2f} mm の"
                            "すぐ上（0.2 mm 未満の余裕）"]
        return "PASS", []


def measure(mesh, spec: UnderBoard, grid: int = 5) -> UndersideResult:
    """build() した形状から、footprint の真下に空いている隙間を実測する."""
    ai = _AXIS_INDEX[spec.axis.upper()]
    other = [i for i in range(3) if i != ai]
    sign = 1.0 if spec.sign >= 0 else -1.0

    # footprint の格子（縁を 0.1 mm 内側に寄せる。角を掠めて拾わないため）
    inset = min(0.1, max(spec.size) / 10)
    uv: list[tuple[float, float]] = []
    if spec.shape == "circle":
        r = spec.size[0] / 2 - inset
        n = max(grid, 2)
        uv.append((spec.at[0], spec.at[1]))
        for i in range(1, n):
            rr = r * i / (n - 1)
            for k in range(max(4 * i, 1)):
                th = 2 * math.pi * k / max(4 * i, 1)
                uv.append((spec.at[0] + rr * math.cos(th),
                           spec.at[1] + rr * math.sin(th)))
    else:
        (u0, u1) = (spec.at[0] - spec.size[0] / 2, spec.at[0] + spec.size[0] / 2)
        (v0, v1) = (spec.at[1] - spec.size[1] / 2, spec.at[1] + spec.size[1] / 2)
        for u in np.linspace(u0 + inset, u1 - inset, max(grid, 2)):
            for v in np.linspace(v0 + inset, v1 - inset, max(grid, 2)):
                uv.append((float(u), float(v)))

    bb = mesh.bounds
    far = float(bb[0][ai]) - 10.0 if sign > 0 else float(bb[1][ai]) + 10.0

    origins = []
    for u, v in uv:
        pt = [0.0, 0.0, 0.0]
        pt[ai] = far
        pt[other[0]] = u
        pt[other[1]] = v
        origins.append(pt)
    direction = [0.0, 0.0, 0.0]
    direction[ai] = sign

    origins = np.asarray(origins, dtype=float)
    dirs = np.tile(np.asarray(direction, dtype=float), (len(origins), 1))
    locs, idx_ray, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)

    # レイごとに「基板下面より下」で一番基板に近い交点を拾う
    # レイごとに「基板下面**以下**で一番基板に近い交点」を拾う。
    # **`depth > 0` にしてはいけない。** 受け面が基板下面とちょうど同じ高さに
    # あると、その面が除外されて「もっと下の面までが隙間」という嘘の値
    # （例: 板の前面までの 5.9 mm）が出る。**接している = 隙間 0** が正しい。
    best: list[float] = [-math.inf] * len(origins)
    for loc, r in zip(locs, idx_ray):
        c = float(loc[ai])
        depth = sign * (spec.board - c)          # 基板下面からの距離（正なら下側）
        if depth > -1e-6 and depth < FAR:
            best[int(r)] = max(best[int(r)], -max(depth, 0.0))

    gaps = [(-b if b > -math.inf else FAR) for b in best]
    worst_i = int(min(range(len(gaps)), key=lambda i: gaps[i]))
    open_frac = sum(1 for g in gaps if g >= FAR) / len(gaps)

    return UndersideResult(
        spec=spec, gap_mm=float(gaps[worst_i]), worst_at=uv[worst_i],
        open_frac=open_frac, samples=len(gaps),
    )
