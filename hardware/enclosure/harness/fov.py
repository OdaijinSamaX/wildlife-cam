"""視野（カメラが見る円錐）を表す型.

カメラの前に置いた構造が視野を遮っていないかを `fov` チェックが見る。
レイアウト専用ではなくハーネスの一般機能で、設計は `VIEW_CONES` を宣言する。

```python
from harness import fov
from parts import cam_module3

VIEW_CONES = [fov.Cone.from_camera(cam_module3, apex=(0, 0, -11.6), axis=(0, 0, 1))]
```

## 円錐の頂点をどこに置くか

厳密にはエントランスピトー（入射瞳）が頂点だが、その位置は測っていない。
**入射瞳はレンズ前面より後ろにある**ので、前面を頂点に取ると円錐が細く出て
判定が甘くなる。そこで既定では **センサ面（レンズ前面から LENS_H だけ後ろ）** を
頂点に置く。円錐が最も太くなる側なので、判定は保守側に倒れる。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import cadquery as cq


@dataclass
class Cone:
    """カメラの視野円錐."""

    name: str
    apex: tuple[float, float, float]
    axis: tuple[float, float, float]
    half_angle_deg: float
    length: float = 300.0
    #: 頂点からこの距離までは判定しない。カメラ自身のレンズ鏡体が円錐に
    #: 掛かるのは当たり前なので、そこを除くために使う。
    start: float = 0.0
    note: str = ""

    @classmethod
    def from_camera(cls, cam, apex, axis, name="camera", length=300.0,
                    half_angle_deg=None, start=None, note=""):
        """parts/cam_module3.py の諸元から作る.

        start の既定は LENS_H + 0.5。カメラ自身のレンズ鏡体を判定から外す。
        """
        half = half_angle_deg if half_angle_deg is not None else cam.half_angle_deg()
        return cls(
            name=name, apex=tuple(apex), axis=tuple(axis),
            half_angle_deg=half, length=length,
            start=(cam.LENS_H + 0.5) if start is None else start,
            note=note or (
                f"焦点距離 {cam.FOCAL_LENGTH_MM} / センサ対角 {cam.SENSOR_DIAG_MM} "
                f"から導出した対角半角 {half:.2f} 度"
            ),
        )

    @property
    def tan_half(self) -> float:
        return math.tan(math.radians(self.half_angle_deg))

    def radius_at(self, distance: float) -> float:
        """頂点から distance の位置での円錐半径."""
        return distance * self.tan_half

    def max_straight_tube_length(self, inner_radius: float) -> float:
        """内半径 r の**真っ直ぐな筒**が成立する最大長 L = r / tan(半角).

        L がこれを超えると筒の縁が視野に入る。対角 76 度クラスでは
        L < 1.28 r 程度で、細長い筒は成立しない。
        """
        return inner_radius / self.tan_half

    def solid(self) -> cq.Shape:
        """判定に使う立体。start から length までの円錐台."""
        import numpy as np

        d = np.array(self.axis, dtype=float)
        d = d / np.linalg.norm(d)
        base = np.array(self.apex, dtype=float) + d * self.start
        return cq.Solid.makeCone(
            self.radius_at(self.start), self.radius_at(self.length),
            self.length - self.start,
            cq.Vector(*base), cq.Vector(*d),
        )

    def angle_of(self, point) -> float:
        """頂点から見た点の、軸からの角度（度）."""
        import numpy as np

        a = np.array(self.apex, dtype=float)
        d = np.array(self.axis, dtype=float)
        d = d / np.linalg.norm(d)
        v = np.array(point, dtype=float) - a
        n = float(np.linalg.norm(v))
        if n < 1e-9:
            return 0.0
        cos = float(np.dot(v, d)) / n
        return math.degrees(math.acos(max(-1.0, min(1.0, cos))))
