"""STEP / STL / 3MF の書き出し.

STEP は寸法をそのまま持つ交換用、STL はチェックとスライサ用、
3MF は P1S (Bambu Studio) にそのまま投げる用。
3MF と STL は造形姿勢を適用した向きで出す（そのままプレートに載る）。
"""

from __future__ import annotations

from pathlib import Path

import cadquery as cq
from cadquery.occ_impl.exporters import ExportTypes

from . import geom
from .geom import TESS_ANGULAR_TOL, TESS_LINEAR_TOL


def _wp(shape: cq.Shape) -> cq.Workplane:
    return cq.Workplane("XY").newObject([shape])


def export_all(ctx, out_dir: str | Path) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = ctx.name
    written: dict[str, Path] = {}

    step = out_dir / f"{name}.step"
    cq.exporters.export(_wp(ctx.shape), str(step), ExportTypes.STEP)
    written["step"] = step

    oriented = ctx.oriented_shape
    stl = out_dir / f"{name}.stl"
    cq.exporters.export(
        _wp(oriented), str(stl), ExportTypes.STL,
        tolerance=TESS_LINEAR_TOL, angularTolerance=TESS_ANGULAR_TOL,
    )
    written["stl"] = stl

    tmf = out_dir / f"{name}.3mf"
    cq.exporters.export(
        _wp(oriented), str(tmf), ExportTypes.THREEMF,
        tolerance=TESS_LINEAR_TOL, angularTolerance=TESS_ANGULAR_TOL,
    )
    written["3mf"] = tmf
    return written
