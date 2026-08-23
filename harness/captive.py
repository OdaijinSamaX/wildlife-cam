"""捕捉式ねじ（脱落しないねじ）の成立条件.

**なぜ要るのか。** 現地でこの機材を保守するのは機械に強くない人で、屋久島の林床で
落としたねじは落ち葉の中で二度と見つからない（`docs/AGENTS.md` §4.9 原則 1）。
だから蓋を外したとき **蝶ねじは蓋に付いたまま残らなければならない。**

捕捉は「リテーナ（止め輪・押しナット）を軸に付け、蓋の内側のポケットで受け止める」
という**寸法の連鎖**で成立する。連鎖のどこか 1 つでも外れると、

  - リテーナが**蓋を抜けてしまう**（捕捉されない。現地でねじを落とす）
  - リテーナが**早く止まりすぎて**ねじが相手のインサートから抜けきらない（**蓋が開かない**）
  - ねじの先が**引っ込みきらず**、蓋を相手に平らに置けない（座らない・ねじ山を痛める）
  - ねじの先が**下穴の底を突く**（締めたつもりで面圧が出ない）

どれも「ねじを 1 本買い替える」「ポケットを 1 mm 深くする」で起きうるのに、
`wall` も `openings` も `layout` も**一切見ていない**。ここで数式にして毎回回す。

## 記号（すべて蓋のシール面 y=0 を原点に、+Y = 外側）

```
                                        頭（蝶）
     y=0 シール面                       ______
       |                               |      |
  -----+-------------------------------+------+----   蓋
       |  ポケット  |     通し穴        | 座ぐり |
       |<- float ->|<---------------- T ---------->|   T = 頭の座面までの深さ
       |
       |<-- gap -->|  相手のインサート座面
       |           |<-- engage -->|                    engage = ねじ込み代
       |<--------- tip_depth ---------->|              tip_depth = screw_len - T
```

  - `T`          … シール面から**頭が当たる座面**までの深さ。**build() から実測する**
  - `pocket`     … シール面から**ポケットの天井**までの深さ。**build() から実測する**
  - `travel`     … ねじが後退できる量 = `pocket - リテーナの厚み`。
                   **リテーナはシール面と面一まで押し込む**という組立の決めごとから出る
  - `tip_depth`  … 締め切ったときにねじ先がシール面より内側へ出る量 = `screw_len - T`
  - `engage`     … `tip_depth - gap`。相手のねじに噛んでいる長さ
  - `protrude`   … 目一杯緩めたときにねじ先がシール面より出る量 = `tip_depth - travel`

## 成立条件

| # | 条件 | 外すとどうなるか |
|---|---|---|
| 1 | `travel > 0` かつリテーナ径の位置に肉がある | **捕捉されない**（現地でねじを落とす） |
| 2 | `engage > 0` | ねじが相手に届かない |
| 3 | `engage <= insert_depth` | **下穴の底を突いて**面圧が出ない |
| 4 | `travel >= engage + release_margin` | **蓋が開かない**（抜けきる前にリテーナが止まる） |
| 5 | `protrude < gap` | **蓋を相手に平らに置けない**（先が当たる） |

条件 4 と 5 は互いに逆を向いている。`travel` は `engage + 余裕` 以上、かつ
`tip_depth - gap` より大きくなければならない。**この窓が閉じたら設計は成立しない。**

## 測り方（宣言と実物がずれないように）

ポケットの深さと座面の深さは PARAMS から読まず、**`build()` した形状に
ねじ軸と平行なレイを飛ばして実測する。**

  - **リテーナ probe**: 半径 `retainer_od/2 - 0.2`。最初に当たる肉までが `pocket`
  - **頭 probe**: 半径 `head_dia/2 - 0.2`。最後に肉が切れるところが `T`

半径を少し内側に取るのは、ポケット壁そのものを掴まないため。周方向に 4 本飛ばし、
**ばらつきが 0.2 mm を超えたら**「軸のまわりが円対称でない」として警告する。

## ここで見ないもの

  - **リテーナの保持力**（押しナットが何 N で抜けるか）。カタログ値も実測もしていない
  - リテーナがねじ山の上を**歩いて**位置がずれること（ゴム O リングや
    ねじ込み式のナットで起きる。止め輪・押しナットは軸方向の止めなので歩かない）
  - ねじの実長のばらつき、インサートの座面が沈む/飛び出す量
  - **面圧への影響**。ポケットを彫れば蓋の断面は痩せる。それは `seal` の仕事
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

_AXIS_INDEX = {"X": 0, "Y": 1, "Z": 2}


@dataclass(frozen=True)
class CaptiveScrew:
    """1 本の捕捉式ねじの申告.

    寸法は**すべて狙い寸法**（印刷後にこうなってほしい寸法）。
    `float`（ポケット深さ）と `T`（座面深さ）は申告せず、`build()` から実測する。
    """

    name: str
    #: 軸の位置。軸に垂直な 2 座標（axis="Y" なら (x, z)）
    at: tuple[float, float]
    #: ねじの呼び径（M4 なら 4.0）
    thread_dia: float
    #: 頭が当たる座面の径（座ぐり径）
    head_dia: float
    #: リテーナ（止め輪・押しナット）の外径
    retainer_od: float
    #: リテーナの厚み。**逃げがそのぶん減る**ので効く（E 形止め輪 呼び4 で 0.6）
    retainer_t: float
    #: 頭の下からねじ先までの長さ
    screw_len: float
    #: シール面から相手のインサート座面までの距離
    gap_mm: float
    #: 相手のインサートの有効深さ
    insert_depth_mm: float
    axis: str = "Y"
    #: 抜けきってからリテーナが止まるまでに残しておく余裕
    release_margin_mm: float = 1.0
    #: これを下回る噛み合いは WARN。0 なら呼び径（1D）を使う
    min_engage_mm: float = 0.0
    note: str = ""

    @property
    def min_engage(self) -> float:
        return self.min_engage_mm or self.thread_dia


@dataclass
class CaptiveResult:
    screw: CaptiveScrew
    #: シール面（軸方向の最小座標）
    face: float
    #: ポケットの天井までの深さ [mm]
    pocket_mm: float
    #: 頭の座面までの深さ [mm]
    seat_mm: float
    #: 周方向のばらつき [mm]
    scatter_mm: float
    #: リテーナが当たる肉が見つからなかった
    not_captive: bool

    @property
    def travel(self) -> float:
        """ねじが後退できる量。リテーナはシール面と面一に入れる約束."""
        return self.pocket_mm - self.screw.retainer_t

    @property
    def tip_depth(self) -> float:
        return self.screw.screw_len - self.seat_mm

    @property
    def engage(self) -> float:
        return self.tip_depth - self.screw.gap_mm

    @property
    def protrude(self) -> float:
        return self.tip_depth - self.travel

    def verdict(self) -> tuple[str, list[str]]:
        """(PASS|WARN|FAIL, 理由) を返す."""
        s = self.screw
        bad: list[str] = []
        warn: list[str] = []
        if self.not_captive or self.travel <= 0.05:
            bad.append(
                f"リテーナ径 φ{s.retainer_od} の位置に受ける肉が無い"
                "（**捕捉されない**。現地でねじを落とす）")
        if self.engage <= 0:
            bad.append(f"ねじが相手に届かない（噛み合い {self.engage:.2f} mm）")
        elif self.engage > s.insert_depth_mm:
            bad.append(
                f"噛み合い {self.engage:.2f} mm がインサートの深さ "
                f"{s.insert_depth_mm} mm を超える（**下穴の底を突いて面圧が出ない**）")
        elif self.engage < s.min_engage:
            warn.append(
                f"噛み合い {self.engage:.2f} mm が呼び径の 1 倍 "
                f"({s.min_engage:.1f} mm) に満たない")
        need = self.engage + s.release_margin_mm
        if not self.not_captive and self.travel < need:
            bad.append(
                f"後退できる量 {self.travel:.2f} mm が「噛み合い {max(self.engage, 0):.2f} + "
                f"余裕 {s.release_margin_mm}」に足りない（**蓋が開かない**）")
        if self.protrude >= s.gap_mm:
            bad.append(
                f"緩めきってもねじ先が {self.protrude:.2f} mm 出たままで、"
                f"隙間 {s.gap_mm} mm に収まらない（**蓋を平らに置けない**）")
        if self.scatter_mm > 0.2:
            warn.append(f"軸まわりのばらつき {self.scatter_mm:.2f} mm（円対称でない）")
        if bad:
            return "FAIL", bad
        if warn:
            return "WARN", warn
        return "PASS", []


def _probe_rays(mesh, at, axis: str, radius: float, n: int = 4):
    """軸に平行なレイを半径 radius の円周上に n 本飛ばし、肉に当たる区間を返す.

    戻り値は各レイについて、軸方向にソートした交点座標のリスト。
    """
    ai = _AXIS_INDEX[axis.upper()]
    other = [i for i in range(3) if i != ai]
    bb = mesh.bounds
    start = float(bb[0][ai]) - 1.0
    origins = []
    for k in range(n):
        th = 2 * math.pi * k / n
        p = [0.0, 0.0, 0.0]
        p[ai] = start
        p[other[0]] = at[0] + radius * math.cos(th)
        p[other[1]] = at[1] + radius * math.sin(th)
        origins.append(p)
    direction = [0.0, 0.0, 0.0]
    direction[ai] = 1.0
    origins = np.array(origins, dtype=float)
    dirs = np.tile(np.array(direction, dtype=float), (n, 1))
    locs, idx_ray, _ = mesh.ray.intersects_location(origins, dirs, multiple_hits=True)
    out: list[list[float]] = [[] for _ in range(n)]
    for loc, r in zip(locs, idx_ray):
        out[int(r)].append(float(loc[ai]))
    return [sorted(v) for v in out]


def measure(mesh, screw: CaptiveScrew) -> CaptiveResult:
    """build() した形状から float（逃げ）と T（座面深さ）を実測する."""
    ai = _AXIS_INDEX[screw.axis.upper()]
    face = float(mesh.bounds[0][ai])

    r_ret = screw.retainer_od / 2 - 0.2
    r_head = screw.head_dia / 2 - 0.2
    if r_ret <= screw.thread_dia / 2 or r_head <= screw.thread_dia / 2:
        raise ValueError(
            f"{screw.name}: リテーナ径/座ぐり径が呼び径に近すぎて probe を置けない")

    ret_hits = _probe_rays(mesh, screw.at, screw.axis, r_ret)
    head_hits = _probe_rays(mesh, screw.at, screw.axis, r_head)

    firsts = [h[0] for h in ret_hits if h]
    not_captive = len(firsts) < len(ret_hits)
    pocket_mm = (min(firsts) - face) if firsts else 0.0
    scatter = (max(firsts) - min(firsts)) if firsts else 0.0

    lasts = [h[-1] for h in head_hits if h]
    seat_mm = (min(lasts) - face) if lasts else 0.0
    scatter = max(scatter, (max(lasts) - min(lasts)) if lasts else 0.0)

    return CaptiveResult(
        screw=screw, face=face, pocket_mm=pocket_mm, seat_mm=seat_mm,
        scatter_mm=scatter, not_captive=not_captive,
    )
