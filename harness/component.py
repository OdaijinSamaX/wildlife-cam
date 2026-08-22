"""内蔵部品（プリントしない実物）を表す型.

clearance / interference チェックはこの型だけを見る。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import cadquery as cq

from . import geom


@dataclass
class Component:
    name: str
    shape: cq.Shape
    envelope_fn: Callable[[float], cq.Shape] | None = None
    notes: str = ""
    #: 寸法の出所。"datasheet" / "measured:2026-08-22" / "estimated" のいずれか。
    dimension_source: str = "estimated"
    warnings: list[str] = field(default_factory=list)

    def envelope(self, clearance: float) -> cq.Shape:
        """外形 + clearance の立体を返す.

        部品側が envelope_fn を持たない場合はバウンディングボックスを
        clearance だけ太らせたもので代用する（保守的だが粗い）。
        """
        if self.envelope_fn is not None:
            return self.envelope_fn(clearance)
        bb = self.shape.BoundingBox()
        c = clearance
        box = cq.Solid.makeBox(
            bb.xlen + 2 * c,
            bb.ylen + 2 * c,
            bb.zlen + 2 * c,
            cq.Vector(bb.xmin - c, bb.ymin - c, bb.zmin - c),
        )
        return box


def transform(shape: cq.Shape, at: Sequence[float], rotate: Sequence[float]) -> cq.Shape:
    return geom.rotate_shape(shape, rotate).translate(cq.Vector(*at))


def make_component(
    name: str,
    model_fn: Callable[..., object],
    envelope_fn: Callable[..., object] | None = None,
    *,
    at: Sequence[float] = (0.0, 0.0, 0.0),
    rotate: Sequence[float] = (0.0, 0.0, 0.0),
    notes: str = "",
    dimension_source: str = "estimated",
    **kw,
) -> Component:
    """parts/*.py の model()/envelope() から配置済み Component を作る."""
    shape = transform(geom.as_shape(model_fn(**kw)), at, rotate)
    fn = None
    if envelope_fn is not None:
        def fn(clearance: float, _kw=kw):
            return transform(geom.as_shape(envelope_fn(clearance=clearance, **_kw)), at, rotate)
    return Component(
        name=name,
        shape=shape,
        envelope_fn=fn,
        notes=notes,
        dimension_source=dimension_source,
    )


def coerce(obj, index: int = 0) -> Component:
    """COMPONENTS の要素を Component に正規化する.

    生の Workplane / Shape も受けるが、その場合 envelope はバウンディング
    ボックス近似になるので警告を付ける。
    """
    if isinstance(obj, Component):
        return obj
    shape = geom.as_shape(obj)
    c = Component(name=f"component[{index}]", shape=shape)
    c.warnings.append(
        "Component ではなく生の形状が渡されました。envelope はバウンディングボックス近似です"
    )
    return c
