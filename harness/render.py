"""多視点 + 断面の PNG 生成.

方式の選択（README にも記載）:
  採用  : VTK のオフスクリーン (EGL)。GUI もヘッドレス用 apt パッケージも要らず、
          この母艦 (Ubuntu 26.04 + NVIDIA) でそのまま PNG が出た。
  予備  : numpy の Z バッファによるソフトウェアラスタライザ。GPU / EGL が使えない
          環境でも必ず絵が出るように残してある。ENCL_RENDERER=soft で強制できる。
  却下  : xvfb-run（apt が要る）、pyrender / OSMesa ホイール（依存が重い）。

断面は「手前半分を実際にブーリアンで切り落としたソリッド」を法線方向から見る。
切り口の面がそのままカメラ正面に来るので、パッキン溝や肉厚が読める。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import cadquery as cq

from . import geom

#: (名前, 視線方向 = カメラから被写体へ向かうベクトル, 上方向)
VIEWS: list[tuple[str, tuple[float, float, float], tuple[float, float, float]]] = [
    ("front", (0, 1, 0), (0, 0, 1)),
    ("back", (0, -1, 0), (0, 0, 1)),
    ("left", (1, 0, 0), (0, 0, 1)),
    ("right", (-1, 0, 0), (0, 0, 1)),
    ("top", (0, 0, -1), (0, 1, 0)),
    ("bottom", (0, 0, 1), (0, 1, 0)),
    ("iso", (-1, 1, -1), (0, 0, 1)),
]

IMG_SIZE = (900, 700)


@dataclass
class RenderResult:
    files: list[Path]
    backend: str
    notes: list[str]


# --- 断面 -------------------------------------------------------------------


def cut_half(shape: cq.Shape, origin: Sequence[float], normal: Sequence[float]) -> cq.Shape:
    """normal 側の半空間を削り落とす（= 残るのは -normal 側）."""
    bb = shape.BoundingBox()
    size = max(bb.xlen, bb.ylen, bb.zlen) * 3 + 10
    n = cq.Vector(*normal).normalized()
    plane = cq.Plane(origin=cq.Vector(*origin), normal=n)
    cutter = cq.Workplane(plane).box(size, size, size, centered=(True, True, False))
    return shape.cut(geom.as_shape(cutter))


# --- VTK --------------------------------------------------------------------


def _vtk_polydata(mesh):
    import vtk
    from vtk.util import numpy_support

    pts = vtk.vtkPoints()
    pts.SetData(numpy_support.numpy_to_vtk(np.ascontiguousarray(mesh.vertices), deep=True))
    faces = np.hstack(
        [np.full((len(mesh.faces), 1), 3, dtype=np.int64), mesh.faces.astype(np.int64)]
    ).ravel()
    cells = vtk.vtkCellArray()
    cells.SetCells(len(mesh.faces), numpy_support.numpy_to_vtkIdTypeArray(faces, deep=True))
    pd = vtk.vtkPolyData()
    pd.SetPoints(pts)
    pd.SetPolys(cells)
    return pd


def _vtk_render(mesh, direction, up, path, label):
    import vtk

    pd = _vtk_polydata(mesh)
    normals = vtk.vtkPolyDataNormals()
    normals.SetInputData(pd)
    normals.SplittingOn()
    normals.SetFeatureAngle(30)
    normals.Update()

    mapper = vtk.vtkPolyDataMapper()
    mapper.SetInputConnection(normals.GetOutputPort())
    mapper.ScalarVisibilityOff()
    actor = vtk.vtkActor()
    actor.SetMapper(mapper)
    actor.GetProperty().SetColor(0.78, 0.80, 0.84)
    actor.GetProperty().SetAmbient(0.28)
    actor.GetProperty().SetDiffuse(0.75)
    actor.GetProperty().SetSpecular(0.12)

    edges = vtk.vtkFeatureEdges()
    edges.SetInputData(pd)
    edges.BoundaryEdgesOn()
    edges.FeatureEdgesOn()
    edges.SetFeatureAngle(25)
    edges.NonManifoldEdgesOn()
    edges.ManifoldEdgesOff()
    emapper = vtk.vtkPolyDataMapper()
    emapper.SetInputConnection(edges.GetOutputPort())
    emapper.ScalarVisibilityOff()
    eactor = vtk.vtkActor()
    eactor.SetMapper(emapper)
    eactor.GetProperty().SetColor(0.1, 0.1, 0.12)
    eactor.GetProperty().SetLineWidth(1.4)

    ren = vtk.vtkRenderer()
    ren.SetBackground(1.0, 1.0, 1.0)
    ren.AddActor(actor)
    ren.AddActor(eactor)

    txt = vtk.vtkTextActor()
    txt.SetInput(label)
    txt.GetTextProperty().SetFontSize(20)
    txt.GetTextProperty().SetColor(0.1, 0.1, 0.1)
    txt.SetPosition(12, 10)
    ren.AddActor2D(txt)

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetSize(*IMG_SIZE)
    rw.AddRenderer(ren)

    d = np.array(direction, dtype=float)
    d /= np.linalg.norm(d)
    center = mesh.bounds.mean(axis=0)
    radius = float(np.linalg.norm(mesh.bounds[1] - mesh.bounds[0])) / 2 + 1e-6
    cam = ren.GetActiveCamera()
    cam.ParallelProjectionOn()
    cam.SetFocalPoint(*center)
    cam.SetPosition(*(center - d * radius * 4))
    cam.SetViewUp(*up)
    ren.ResetCamera()
    cam.SetParallelScale(radius * 1.12)

    rw.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(rw)
    w2i.ReadFrontBufferOff()
    w2i.Update()
    writer = vtk.vtkPNGWriter()
    writer.SetFileName(str(path))
    writer.SetInputConnection(w2i.GetOutputPort())
    writer.Write()
    rw.Finalize()

    from PIL import Image

    arr = np.array(Image.open(path).convert("RGB"))
    if len(np.unique(arr.reshape(-1, 3), axis=0)) < 3:
        raise RuntimeError("VTK が真っ白/真っ黒の画像を返した")


# --- ソフトウェアラスタライザ（予備） ---------------------------------------


def _soft_render(mesh, direction, up, path, label):
    from PIL import Image, ImageDraw

    w, h = IMG_SIZE
    d = np.array(direction, dtype=float)
    d /= np.linalg.norm(d)
    upv = np.array(up, dtype=float)
    right = np.cross(d, upv)
    if np.linalg.norm(right) < 1e-9:
        right = np.cross(d, np.array([1.0, 0.0, 0.0]))
    right /= np.linalg.norm(right)
    true_up = np.cross(right, d)

    v = mesh.vertices
    center = mesh.bounds.mean(axis=0)
    rel = v - center
    x = rel @ right
    y = rel @ true_up
    z = rel @ d  # 大きいほど奥
    radius = max(float(np.abs(x).max()), float(np.abs(y).max())) * 1.12 + 1e-6
    scale = min(w, h) / (2 * radius)
    px = (x * scale + w / 2).astype(np.float64)
    py = (-y * scale + h / 2).astype(np.float64)

    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)
    shade = 0.30 + 0.70 * np.clip(mesh.face_normals @ light, 0, 1)

    zbuf = np.full((h, w), np.inf)
    img = np.ones((h, w, 3), dtype=np.float64)

    tri_px = px[mesh.faces]
    tri_py = py[mesh.faces]
    tri_z = z[mesh.faces]
    order = np.argsort(-tri_z.mean(axis=1))  # 奥から手前へ

    for fi in order:
        ax, bx, cx = tri_px[fi]
        ay, by, cy = tri_py[fi]
        az, bz, cz = tri_z[fi]
        x0 = max(int(math.floor(min(ax, bx, cx))), 0)
        x1 = min(int(math.ceil(max(ax, bx, cx))) + 1, w)
        y0 = max(int(math.floor(min(ay, by, cy))), 0)
        y1 = min(int(math.ceil(max(ay, by, cy))) + 1, h)
        if x1 <= x0 or y1 <= y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(det) < 1e-12:
            continue
        l1 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / det
        l2 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / det
        l3 = 1.0 - l1 - l2
        inside = (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        if not inside.any():
            continue
        depth = l1 * az + l2 * bz + l3 * cz
        sub = zbuf[y0:y1, x0:x1]
        upd = inside & (depth < sub)
        if not upd.any():
            continue
        sub[upd] = depth[upd]
        img[y0:y1, x0:x1][upd] = shade[fi] * np.array([0.78, 0.80, 0.84])

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    ImageDraw.Draw(out).text((12, h - 24), label, fill=(20, 20, 20))
    out.save(path)


# --- 入口 -------------------------------------------------------------------


def _label(name, mesh):
    lo, hi = mesh.bounds
    dims = hi - lo
    return f"{name}   bbox {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm"


def render_design(ctx, out_dir: str | Path) -> RenderResult:
    out_dir = Path(out_dir) / "views"
    out_dir.mkdir(parents=True, exist_ok=True)
    forced = os.environ.get("ENCL_RENDERER", "").lower()
    backend = "vtk" if forced != "soft" else "soft"
    notes: list[str] = []
    files: list[Path] = []

    jobs: list[tuple[str, object]] = [(name, ctx.mesh) for name, _, _ in VIEWS]
    dirs = {name: (d, u) for name, d, u in VIEWS}

    for name, mesh in jobs:
        d, u = dirs[name]
        path = out_dir / f"{name}.png"
        backend, note = _render_one(mesh, d, u, path, _label(name, mesh), backend)
        notes.extend(note)
        files.append(path)

    for sec in ctx.sections:
        name = sec["name"]
        cut = cut_half(ctx.shape, sec["origin"], sec["normal"])
        try:
            mesh = geom.to_mesh(cut)
        except Exception as exc:  # 断面が空になった等
            notes.append(f"断面 {name} を生成できませんでした: {exc}")
            continue
        d = tuple(-np.array(sec["normal"], dtype=float))
        up = sec.get("up", (0, 0, 1))
        if abs(float(np.dot(np.array(d) / np.linalg.norm(d), np.array(up, dtype=float)))) > 0.99:
            up = (0, 1, 0)
        path = out_dir / f"section_{name}.png"
        backend, note = _render_one(mesh, d, up, path, _label(f"section {name}", mesh), backend)
        notes.extend(note)
        files.append(path)

    return RenderResult(files=files, backend=backend, notes=notes)


def _render_one(mesh, d, up, path, label, backend):
    notes = []
    if backend == "vtk":
        try:
            _vtk_render(mesh, d, up, path, label)
            return backend, notes
        except Exception as exc:
            notes.append(f"VTK レンダに失敗したのでソフトウェアに切り替え: {exc}")
            backend = "soft"
    _soft_render(mesh, d, up, path, label)
    return backend, notes
