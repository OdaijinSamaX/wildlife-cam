"""多視点 + 断面の PNG 生成.

方式の選択（README にも記載）:
  採用  : VTK のオフスクリーン (EGL)。GUI もヘッドレス用 apt パッケージも要らず、
          この母艦 (Ubuntu 26.04 + NVIDIA) でそのまま PNG が出た。
  予備  : numpy の Z バッファによるソフトウェアラスタライザ。GPU / EGL が使えない
          環境でも必ず絵が出るように残してある。ENCL_RENDERER=soft で強制できる。
  却下  : xvfb-run（apt が要る）、pyrender / OSMesa ホイール（依存が重い）。

## 内蔵部品を描く

`COMPONENTS` がある設計では、**印刷される部品と内蔵部品を描き分ける**。

  views/*.png         印刷される部品だけ（不透明）
  views/assy_*.png    外殻を半透明にして内蔵部品を色分けで重ねた図
  views/section_*.png 断面。**外殻も内蔵部品も同じ面で切る**ので、部品の断面が見える

防水筐体は中が隠れるので、断面が唯一の確認手段になる。だから断面には必ず
内蔵部品を入れる。部品には色を割り当て、凡例と 3D ラベルで名前が分かるようにする。

断面は「手前半分を実際にブーリアンで切り落としたソリッド」を法線方向から見る。
切り口の面がそのままカメラ正面に来るので、パッキン溝や肉厚が読める。
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import cadquery as cq
import numpy as np

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

#: 内蔵部品つきで描く視点（増やすとレンダ時間がそのまま伸びる）
ASSY_VIEWS = ["iso", "front", "top", "right"]

IMG_SIZE = (900, 700)

SHELL_COLOR = (0.78, 0.80, 0.84)
SHELL_OPACITY_IN_ASSY = 0.22

# VTK の既定フォントは日本語を出せない（空白になる）。図に焼き込む文字列は
# 必ず ASCII にすること。説明は report.md 側の日本語で補う。

#: 内蔵部品に順番に割り当てる色。見分けが付くことだけを狙っている。
PART_COLORS = [
    (0.85, 0.33, 0.29),   # 赤
    (0.24, 0.52, 0.78),   # 青
    (0.35, 0.66, 0.36),   # 緑
    (0.92, 0.68, 0.20),   # 黄土
    (0.60, 0.40, 0.72),   # 紫
    (0.20, 0.70, 0.70),   # シアン
    (0.85, 0.50, 0.70),   # ピンク
    (0.55, 0.45, 0.30),   # 茶
    (0.45, 0.55, 0.60),   # 青灰
]


def color_for(index: int) -> tuple[float, float, float]:
    return PART_COLORS[index % len(PART_COLORS)]


@dataclass
class Item:
    """1 つの描画対象."""

    mesh: object
    color: tuple[float, float, float]
    opacity: float = 1.0
    name: str = ""
    edges: bool = True
    label_at: tuple[float, float, float] | None = None


@dataclass
class RenderResult:
    files: list[Path]
    backend: str
    notes: list[str] = field(default_factory=list)
    legend: list[tuple[str, tuple[float, float, float]]] = field(default_factory=list)
    assembly_files: list[Path] = field(default_factory=list)
    section_files: list[Path] = field(default_factory=list)


# --- 断面 -------------------------------------------------------------------


def cut_half(shape: cq.Shape, origin: Sequence[float], normal: Sequence[float]) -> cq.Shape:
    """normal 側の半空間を削り落とす（= 残るのは -normal 側）."""
    bb = shape.BoundingBox()
    size = max(bb.xlen, bb.ylen, bb.zlen) * 3 + 10
    n = cq.Vector(*normal).normalized()
    plane = cq.Plane(origin=cq.Vector(*origin), normal=n)
    cutter = cq.Workplane(plane).box(size, size, size, centered=(True, True, False))
    return shape.cut(geom.as_shape(cutter))


def _cut_or_none(shape: cq.Shape, origin, normal, size_hint: float):
    """断面で切った残り。空になったら None."""
    try:
        bb = shape.BoundingBox()
        n = cq.Vector(*normal).normalized()
        plane = cq.Plane(origin=cq.Vector(*origin), normal=n)
        big = max(bb.xlen, bb.ylen, bb.zlen, size_hint) * 3 + 10
        cutter = cq.Workplane(plane).box(big, big, big, centered=(True, True, False))
        rest = shape.cut(geom.as_shape(cutter))
        if rest is None or not rest.Solids() or rest.Volume() < 1e-6:
            return None
        return rest
    except Exception:
        return None


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


def _vtk_render(items, direction, up, path, label, legend=None):
    import vtk

    ren = vtk.vtkRenderer()
    ren.SetBackground(1.0, 1.0, 1.0)
    ren.SetUseDepthPeeling(1)          # 半透明の重なりを正しく出すため
    ren.SetMaximumNumberOfPeels(8)
    ren.SetOcclusionRatio(0.0)

    all_bounds = []
    for it in items:
        pd = _vtk_polydata(it.mesh)
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
        actor.GetProperty().SetColor(*it.color)
        actor.GetProperty().SetOpacity(it.opacity)
        actor.GetProperty().SetAmbient(0.30)
        actor.GetProperty().SetDiffuse(0.72)
        actor.GetProperty().SetSpecular(0.10)
        ren.AddActor(actor)
        all_bounds.append(it.mesh.bounds)

        if it.edges and it.opacity > 0.5:
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
            eactor.GetProperty().SetLineWidth(1.3)
            ren.AddActor(eactor)

        if it.label_at is not None and it.name:
            txt = vtk.vtkBillboardTextActor3D()
            txt.SetPosition(*it.label_at)
            txt.SetInput(it.name)
            tp = txt.GetTextProperty()
            tp.SetFontSize(15)
            tp.SetColor(*(min(1.0, c * 0.65) for c in it.color))
            tp.SetBold(True)
            tp.SetJustificationToCentered()
            ren.AddActor(txt)

    caption = vtk.vtkTextActor()
    caption.SetInput(label)
    caption.GetTextProperty().SetFontSize(20)
    caption.GetTextProperty().SetColor(0.1, 0.1, 0.1)
    caption.SetPosition(12, 10)
    ren.AddViewProp(caption)

    for i, (name, col) in enumerate(legend or []):
        entry = vtk.vtkTextActor()
        entry.SetInput(f"■ {name}")
        entry.GetTextProperty().SetFontSize(16)
        entry.GetTextProperty().SetColor(*(min(1.0, c * 0.8) for c in col))
        entry.GetTextProperty().SetBold(True)
        entry.SetPosition(12, IMG_SIZE[1] - 24 - i * 20)
        ren.AddViewProp(entry)

    rw = vtk.vtkRenderWindow()
    rw.SetOffScreenRendering(1)
    rw.SetAlphaBitPlanes(1)
    rw.SetMultiSamples(0)
    rw.SetSize(*IMG_SIZE)
    rw.AddRenderer(ren)

    lo = np.min([b[0] for b in all_bounds], axis=0)
    hi = np.max([b[1] for b in all_bounds], axis=0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2 + 1e-6

    d = np.array(direction, dtype=float)
    d /= np.linalg.norm(d)
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


def _soft_render(items, direction, up, path, label, legend=None):
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

    lo = np.min([it.mesh.bounds[0] for it in items], axis=0)
    hi = np.max([it.mesh.bounds[1] for it in items], axis=0)
    center = (lo + hi) / 2
    radius = float(np.linalg.norm(hi - lo)) / 2 + 1e-6
    scale = min(w, h) / (2 * radius * 1.12)

    light = np.array([0.4, -0.5, 0.75])
    light /= np.linalg.norm(light)

    zbuf = np.full((h, w), np.inf)
    img = np.ones((h, w, 3), dtype=np.float64)

    # 不透明を先に、半透明を後ろから手前へ
    ordered = sorted(items, key=lambda it: (it.opacity < 1.0,))
    for it in ordered:
        mesh = it.mesh
        rel = mesh.vertices - center
        px = (rel @ right) * scale + w / 2
        py = -(rel @ true_up) * scale + h / 2
        pz = rel @ d
        shade = 0.30 + 0.70 * np.clip(mesh.face_normals @ light, 0, 1)
        tri_px, tri_py, tri_z = px[mesh.faces], py[mesh.faces], pz[mesh.faces]
        order = np.argsort(-tri_z.mean(axis=1))
        base = np.array(it.color, dtype=float)
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
            col = shade[fi] * base
            if it.opacity >= 1.0:
                sub[upd] = depth[upd]
                img[y0:y1, x0:x1][upd] = col
            else:
                a = it.opacity
                tgt = img[y0:y1, x0:x1]
                tgt[upd] = tgt[upd] * (1 - a) + col * a

    out = Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8))
    draw = ImageDraw.Draw(out)
    draw.text((12, h - 24), label, fill=(20, 20, 20))
    for i, (name, col) in enumerate(legend or []):
        draw.text((12, 8 + i * 14), f"■ {name}",
                  fill=tuple(int(min(1.0, c * 0.8) * 255) for c in col))
    out.save(path)


# --- 入口 -------------------------------------------------------------------


def _label(name, items):
    lo = np.min([it.mesh.bounds[0] for it in items], axis=0)
    hi = np.max([it.mesh.bounds[1] for it in items], axis=0)
    dims = hi - lo
    return f"{name}   bbox {dims[0]:.1f} x {dims[1]:.1f} x {dims[2]:.1f} mm"


def _component_items(components, cut=None, size_hint=100.0, notes=None):
    """COMPONENTS を色分けした Item にする。cut を渡すと同じ面で切る."""
    items = []
    legend = []
    for i, comp in enumerate(components):
        col = color_for(i)
        shape = comp.shape
        if cut is not None:
            shape = _cut_or_none(shape, cut["origin"], cut["normal"], size_hint)
            if shape is None:
                continue          # 断面の向こう側に全部行った部品は描かない
        try:
            mesh = geom.to_mesh(shape)
        except Exception as exc:
            if notes is not None:
                notes.append(f"部品 {comp.name} をメッシュ化できませんでした: {exc}")
            continue
        items.append(Item(
            mesh=mesh, color=col, opacity=1.0, name=comp.name,
            edges=True, label_at=tuple(mesh.bounds.mean(axis=0)),
        ))
        legend.append((comp.name, col))
    return items, legend


def render_design(ctx, out_dir: str | Path) -> RenderResult:
    out_dir = Path(out_dir) / "views"
    out_dir.mkdir(parents=True, exist_ok=True)
    forced = os.environ.get("ENCL_RENDERER", "").lower()
    backend = "vtk" if forced != "soft" else "soft"
    notes: list[str] = []
    files: list[Path] = []
    assy_files: list[Path] = []
    sec_files: list[Path] = []

    components = list(getattr(ctx, "components", []) or [])
    bb = ctx.shape.BoundingBox()
    size_hint = max(bb.xlen, bb.ylen, bb.zlen)
    dirs = {name: (d, u) for name, d, u in VIEWS}

    shell_mesh = ctx.mesh
    legend: list[tuple[str, tuple[float, float, float]]] = []

    # 1. 印刷される部品だけ（不透明）
    for name, _d, _u in VIEWS:
        d, u = dirs[name]
        item = Item(mesh=shell_mesh, color=SHELL_COLOR, name="printed")
        path = out_dir / f"{name}.png"
        backend, note = _render_one([item], d, u, path, _label(name, [item]), backend)
        notes.extend(note)
        files.append(path)

    # 2. 内蔵部品つき（外殻を半透明にして重ねる）
    if components:
        comp_items, legend = _component_items(components, notes=notes)
        shell_item = Item(mesh=shell_mesh, color=SHELL_COLOR,
                          opacity=SHELL_OPACITY_IN_ASSY, name="printed", edges=False)
        for name in ASSY_VIEWS:
            if name not in dirs:
                continue
            d, u = dirs[name]
            path = out_dir / f"assy_{name}.png"
            items = [shell_item] + comp_items
            backend, note = _render_one(
                items, d, u, path, _label(f"assy {name}", items), backend,
                legend=[("printed (translucent shell)", SHELL_COLOR)] + legend,
            )
            notes.extend(note)
            assy_files.append(path)

    # 3. 断面（外殻も内蔵部品も同じ面で切る）
    for sec in ctx.sections:
        name = sec["name"]
        cut = {"origin": sec["origin"], "normal": sec["normal"]}
        try:
            shell_cut = geom.to_mesh(cut_half(ctx.shape, sec["origin"], sec["normal"]))
        except Exception as exc:
            notes.append(f"断面 {name} を生成できませんでした: {exc}")
            continue
        items = [Item(mesh=shell_cut, color=SHELL_COLOR, name="printed")]
        sec_legend: list[tuple[str, tuple[float, float, float]]] = []
        if components:
            comp_cut, sec_legend = _component_items(
                components, cut=cut, size_hint=size_hint, notes=notes)
            items += comp_cut
        d = tuple(-np.array(sec["normal"], dtype=float))
        up = sec.get("up", (0, 0, 1))
        if abs(float(np.dot(np.array(d) / np.linalg.norm(d), np.array(up, dtype=float)))) > 0.99:
            up = (0, 1, 0)
        path = out_dir / f"section_{name}.png"
        backend, note = _render_one(
            items, d, up, path, _label(f"section {name}", items), backend,
            legend=([("printed", SHELL_COLOR)] + sec_legend) if sec_legend else None,
        )
        notes.extend(note)
        sec_files.append(path)

    return RenderResult(
        files=files + assy_files + sec_files, backend=backend, notes=notes,
        legend=legend, assembly_files=assy_files, section_files=sec_files,
    )


def _render_one(items, d, up, path, label, backend, legend=None):
    notes = []
    if backend == "vtk":
        try:
            _vtk_render(items, d, up, path, label, legend=legend)
            return backend, notes
        except Exception as exc:
            notes.append(f"VTK レンダに失敗したのでソフトウェアに切り替え: {exc}")
            backend = "soft"
    _soft_render(items, d, up, path, label, legend=legend)
    return backend, notes
