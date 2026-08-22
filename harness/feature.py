"""フィーチャの占有領域（claim）.

単一ソリッドの中でフィーチャ同士が食い合うのを止めるための宣言。
`interference` は別ソリッド同士しか見ず、`openings` は溝を止まり穴としか見ない。
「O リング溝が基準ピンの根元を削っていた」ような事故はどちらにも掛からないので、
設計側が各フィーチャの占有領域を宣言し、重なったら FAIL にする。

## claim は「フィーチャ自身の体積」ではなく「そのフィーチャが所有すべき材料領域」

ここを取り違えると検出できない。実例:

  基準ピン (z=8..20) と O リング溝 (z=6.5..8) は、自分の体積だけを claim すると
  z が重ならないので「重なっていない」ことになる。しかし実際にはピンの真下の板を
  溝が削っており、ピンの根元が宙に浮いていた。

したがって:

  - 台座から立つボス・ピン・フィン -> **足元の板を厚み方向いっぱいまで claim する**
  - 止まり穴 -> 空洞 + その下に残すべき肉 (min_wall) まで claim する
  - 貫通穴 -> 板厚いっぱい
  - 刻印 -> 彫り込む深さぶん

## マージン

既定は `min_wall / 2`。2 つの claim が重なった時点で、フィーチャ間に残る材料が
min_wall を下回っている、という意味になる。マージンは **横方向にだけ** 効く
（z 方向は上の規約どおり設計側が明示する）。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

import cadquery as cq

from . import geom

_AXES = {"X": (1.0, 0.0, 0.0), "Y": (0.0, 1.0, 0.0), "Z": (0.0, 0.0, 1.0)}


@dataclass
class Feature:
    name: str
    region: cq.Shape = field(repr=False)
    margin: float = 0.0
    note: str = ""

    @property
    def bbox(self):
        return self.region.BoundingBox()


def _wp(shape) -> cq.Shape:
    return geom.as_shape(shape)


def cylinder(
    name: str,
    center: Sequence[float],
    dia: float,
    z0: float,
    z1: float,
    margin: float = 0.0,
    axis: str = "Z",
    note: str = "",
) -> Feature:
    """円柱の claim。center は軸に垂直な 2 座標、z0/z1 は軸方向の範囲."""
    r = dia / 2 + margin
    h = z1 - z0
    if h <= 0:
        raise ValueError(f"{name}: z1 は z0 より大きいこと ({z0} -> {z1})")
    d = _AXES[axis.upper()]
    base = {
        "Z": (center[0], center[1], z0),
        "X": (z0, center[0], center[1]),
        "Y": (center[0], z0, center[1]),
    }[axis.upper()]
    solid = cq.Solid.makeCylinder(r, h, cq.Vector(*base), cq.Vector(*d))
    return Feature(name=name, region=solid, margin=margin, note=note)


def ring(
    name: str,
    center: Sequence[float],
    mean_dia: float,
    width: float,
    z0: float,
    z1: float,
    margin: float = 0.0,
    note: str = "",
) -> Feature:
    """円環（溝）の claim。中心径と幅で帯を作り、内外に margin を足す.

    バウンディングボックスで包むと帯の内側の広い land まで占有したことになり、
    そこに何も置けなくなるので、必ず環として扱う。
    """
    r_out = mean_dia / 2 + width / 2 + margin
    r_in = mean_dia / 2 - width / 2 - margin
    if r_in <= 0:
        return cylinder(name, center, 2 * r_out, z0, z1, 0.0, note=note)
    h = z1 - z0
    outer = cq.Solid.makeCylinder(r_out, h, cq.Vector(center[0], center[1], z0))
    inner = cq.Solid.makeCylinder(r_in, h + 2, cq.Vector(center[0], center[1], z0 - 1))
    return Feature(name=name, region=outer.cut(inner), margin=margin, note=note)


def box(
    name: str,
    center: Sequence[float],
    size: Sequence[float],
    z0: float,
    z1: float,
    margin: float = 0.0,
    note: str = "",
) -> Feature:
    """直方体の claim。size は (x, y)、margin は横方向にだけ効く."""
    sx = size[0] + 2 * margin
    sy = size[1] + 2 * margin
    h = z1 - z0
    solid = cq.Solid.makeBox(
        sx, sy, h, cq.Vector(center[0] - sx / 2, center[1] - sy / 2, z0)
    )
    return Feature(name=name, region=solid, margin=margin, note=note)


def from_shape(
    name: str,
    shape,
    margin: float = 0.0,
    z0: float | None = None,
    z1: float | None = None,
    note: str = "",
) -> Feature:
    """任意形状のバウンディングボックスから claim を作る.

    刻印文字のように形が複雑で、外形が分かればよいものに使う。
    z 範囲は省略すると元の形状のものを使う。
    """
    bb = _wp(shape).BoundingBox()
    zz0 = bb.zmin if z0 is None else z0
    zz1 = bb.zmax if z1 is None else z1
    return box(
        name,
        ((bb.xmin + bb.xmax) / 2, (bb.ymin + bb.ymax) / 2),
        (bb.xlen, bb.ylen),
        zz0,
        zz1,
        margin=margin,
        note=note,
    )


def bboxes_overlap(a, b, eps: float = 1e-9) -> bool:
    return not (
        a.xmax < b.xmin - eps or b.xmax < a.xmin - eps
        or a.ymax < b.ymin - eps or b.ymax < a.ymin - eps
        or a.zmax < b.zmin - eps or b.zmax < a.zmin - eps
    )
