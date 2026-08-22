"""形状 <-> メッシュ <-> ボクセルの変換と、その周辺の共通処理.

このモジュールだけが OCC / trimesh / shapely の細部を知っている。
checks/ 以下はここが返す素直なデータ構造だけを見る。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

import cadquery as cq
import numpy as np
import trimesh
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.GeomAbs import GeomAbs_SurfaceType
from OCP.gp import gp_Pnt
from OCP.TopAbs import TopAbs_State
from scipy import ndimage
from shapely.geometry import MultiPolygon
import shapely

# --- テッセレーション既定値 ------------------------------------------------
# 線形公差 0.05 mm は「0.4 mm ノズルの造形誤差より十分細かく、かつ数万三角形に
# 爆発しない」ところ。角度公差 0.2 rad は φ3 の穴でも 30 角形以上になる。
TESS_LINEAR_TOL = 0.05
TESS_ANGULAR_TOL = 0.2


# --- 形状の取り出し --------------------------------------------------------


def as_shape(obj) -> cq.Shape:
    """Workplane / Assembly / Shape のいずれかを 1 個の cq.Shape にまとめる."""
    if isinstance(obj, cq.Assembly):
        return obj.toCompound()
    if isinstance(obj, cq.Workplane):
        solids = obj.vals()
        shapes = [s for s in solids if isinstance(s, cq.Shape)]
        if not shapes:
            raise ValueError("build() が返した Workplane に形状がありません")
        if len(shapes) == 1:
            return shapes[0]
        return cq.Compound.makeCompound(shapes)
    if isinstance(obj, cq.Shape):
        return obj
    raise TypeError(f"対応していない型です: {type(obj)!r}")


def named_solids(obj) -> list[tuple[str, cq.Shape]]:
    """(名前, ソリッド) の一覧。Assembly なら Assembly の名前を使う."""
    out: list[tuple[str, cq.Shape]] = []
    if isinstance(obj, cq.Assembly):
        for name, child in obj.traverse():
            if child.obj is None:
                continue
            shape = as_shape(child.obj).locate(child.loc)
            for i, sol in enumerate(shape.Solids()):
                label = name if len(shape.Solids()) == 1 else f"{name}[{i}]"
                out.append((label, sol))
        return out
    shape = as_shape(obj)
    solids = shape.Solids()
    for i, sol in enumerate(solids):
        out.append((f"solid[{i}]" if len(solids) > 1 else "solid", sol))
    return out


def rotate_shape(shape: cq.Shape, rotate: Sequence[float]) -> cq.Shape:
    """原点まわりに X, Y, Z の順で回す（造形姿勢の適用）."""
    rx, ry, rz = rotate
    out = shape
    if rx:
        out = out.rotate(cq.Vector(0, 0, 0), cq.Vector(1, 0, 0), rx)
    if ry:
        out = out.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 1, 0), ry)
    if rz:
        out = out.rotate(cq.Vector(0, 0, 0), cq.Vector(0, 0, 1), rz)
    return out


def drop_to_plate(shape: cq.Shape) -> cq.Shape:
    """z 最小がビルドプレート (z=0) に載るように平行移動する."""
    bb = shape.BoundingBox()
    return shape.translate(cq.Vector(0, 0, -bb.zmin))


def bbox_dims(shape: cq.Shape) -> tuple[float, float, float]:
    bb = shape.BoundingBox()
    return (bb.xlen, bb.ylen, bb.zlen)


# --- メッシュ --------------------------------------------------------------


def to_mesh(
    shape: cq.Shape,
    linear_tol: float = TESS_LINEAR_TOL,
    angular_tol: float = TESS_ANGULAR_TOL,
) -> trimesh.Trimesh:
    """B-rep を三角メッシュに落とす。頂点はマージして多様体判定に使えるようにする."""
    verts, tris = shape.tessellate(linear_tol, angular_tol)
    v = np.array([[p.x, p.y, p.z] for p in verts], dtype=float)
    f = np.array(tris, dtype=np.int64)
    mesh = trimesh.Trimesh(vertices=v, faces=f, process=True, validate=True)
    mesh.merge_vertices()
    return mesh


def mesh_of(obj, **kw) -> trimesh.Trimesh:
    return to_mesh(as_shape(obj), **kw)


# --- 点の内外判定 (B-rep, 厳密) --------------------------------------------


def point_inside(shape: cq.Shape, pt: Sequence[float], tol: float = 1e-6) -> bool:
    cls = BRepClass3d_SolidClassifier(shape.wrapped)
    cls.Perform(gp_Pnt(float(pt[0]), float(pt[1]), float(pt[2])), tol)
    return cls.State() in (TopAbs_State.TopAbs_IN, TopAbs_State.TopAbs_ON)


# --- ボクセル --------------------------------------------------------------


@dataclass
class VoxelGrid:
    """z スライス断面のラスタライズで作る中身の詰まったボクセル格子."""

    grid: np.ndarray  # bool (nx, ny, nz)  True = 材料
    origin: np.ndarray  # 格子 (0,0,0) のボクセル中心座標
    pitch: float

    @property
    def voxel_volume(self) -> float:
        return self.pitch**3

    def index_to_xyz(self, idx: Sequence[int]) -> np.ndarray:
        return self.origin + np.asarray(idx, dtype=float) * self.pitch

    def xyz_to_index(self, xyz: Sequence[float]) -> tuple[int, int, int]:
        i = np.rint((np.asarray(xyz, dtype=float) - self.origin) / self.pitch).astype(int)
        i = np.clip(i, 0, np.array(self.grid.shape) - 1)
        return tuple(int(x) for x in i)


def voxelize(mesh: trimesh.Trimesh, pitch: float, pad: int = 2) -> VoxelGrid:
    """z ごとに断面ポリゴンを取り、shapely で内外判定してラスタライズする.

    表面ボクセル化 + 穴埋めと違い「閉じた空洞」と「材料」を区別できるので、
    openings チェックがそのまま使える。
    """
    lo = mesh.bounds[0] - pad * pitch
    hi = mesh.bounds[1] + pad * pitch
    n = np.ceil((hi - lo) / pitch).astype(int) + 1
    nx, ny, nz = (int(v) for v in n)
    origin = lo + 0.5 * pitch
    xs = origin[0] + np.arange(nx) * pitch
    ys = origin[1] + np.arange(ny) * pitch
    zs = origin[2] + np.arange(nz) * pitch
    gx, gy = np.meshgrid(xs, ys, indexing="ij")
    px, py = gx.ravel(), gy.ravel()

    grid = np.zeros((nx, ny, nz), dtype=bool)
    for k, z in enumerate(zs):
        try:
            section = mesh.section(plane_origin=[0.0, 0.0, float(z)], plane_normal=[0, 0, 1])
        except Exception:
            section = None
        if section is None:
            continue
        try:
            planar, _ = section.to_2D(to_2D=np.eye(4))
            polys = list(planar.polygons_full)
        except Exception:
            continue
        if not polys:
            continue
        geom = polys[0] if len(polys) == 1 else MultiPolygon(polys)
        inside = shapely.contains_xy(geom, px, py)
        grid[:, :, k] = inside.reshape(nx, ny)
    return VoxelGrid(grid=grid, origin=origin, pitch=pitch)


CONN6 = ndimage.generate_binary_structure(3, 1)


def air_components(vg: VoxelGrid) -> tuple[np.ndarray, int, set[int]]:
    """空気側の連結成分。(ラベル配列, 個数, 外界に通じるラベル集合) を返す."""
    air = ~vg.grid
    labels, count = ndimage.label(air, structure=CONN6)
    border = set()
    for sl in (
        labels[0], labels[-1],
        labels[:, 0], labels[:, -1],
        labels[:, :, 0], labels[:, :, -1],
    ):
        border.update(int(v) for v in np.unique(sl))
    border.discard(0)
    return labels, int(count), border


def ball(radius_vox: float) -> np.ndarray:
    r = int(math.ceil(radius_vox))
    ax = np.arange(-r, r + 1)
    X, Y, Z = np.meshgrid(ax, ax, ax, indexing="ij")
    return (X**2 + Y**2 + Z**2) <= radius_vox**2 + 1e-9


def morph_close(grid: np.ndarray, radius_vox: float) -> np.ndarray:
    """半径 radius_vox のボールでクロージング（= 直径 2r 未満の隙間を塞ぐ）."""
    st = ball(radius_vox)
    dil = ndimage.binary_dilation(grid, structure=st)
    return ndimage.binary_erosion(dil, structure=st, border_value=1)


# --- B-rep の円筒面 --------------------------------------------------------


@dataclass
class CylFace:
    """内向き円筒面 = 穴の候補."""

    radius: float
    center: tuple[float, float, float]      # 円筒面上の点
    axis_point: tuple[float, float, float]  # 軸上の点
    axis: tuple[float, float, float]
    area: float
    faces: list = field(repr=False, default_factory=list)

    @property
    def diameter(self) -> float:
        return 2.0 * self.radius


def internal_cylinders(shape: cq.Shape, min_dia: float = 0.5) -> list[CylFace]:
    """材料が外側にある（= 穴の内壁である）円筒面を拾う."""
    out: list[CylFace] = []
    for face in shape.Faces():
        ad = BRepAdaptor_Surface(face.wrapped)
        if ad.GetType() != GeomAbs_SurfaceType.GeomAbs_Cylinder:
            continue
        cyl = ad.Cylinder()
        radius = float(cyl.Radius())
        if radius * 2 < min_dia:
            continue
        ax = cyl.Axis()
        loc = ax.Location()
        direction = ax.Direction()
        axis = np.array([direction.X(), direction.Y(), direction.Z()], dtype=float)
        # 面上の 1 点で法線の向きを見る。軸へ向いていれば穴の内壁。
        try:
            pt = face.positionAt(0.5, 0.5)  # 面上の点。Center() は軸上に来るので使えない
            normal = face.normalAt(pt)
        except Exception:
            continue
        base = np.array([loc.X(), loc.Y(), loc.Z()], dtype=float)
        p = np.array([pt.x, pt.y, pt.z], dtype=float)
        radial = (p - base) - np.dot(p - base, axis) * axis
        if np.linalg.norm(radial) < 1e-9:
            continue
        radial /= np.linalg.norm(radial)
        n = np.array([normal.x, normal.y, normal.z], dtype=float)
        if np.dot(n, radial) > 0:  # 法線が軸から外を向く = 丸棒の外周
            continue
        out.append(
            CylFace(
                radius=radius,
                center=(float(p[0]), float(p[1]), float(p[2])),
                axis_point=(float(base[0]), float(base[1]), float(base[2])),
                axis=(float(axis[0]), float(axis[1]), float(axis[2])),
                area=float(face.Area()),
                faces=[face],
            )
        )
    return out


def merge_coaxial(cyls: Iterable[CylFace], tol: float = 1e-3) -> list[CylFace]:
    """同軸・同径に分割された円筒面をひとつの穴にまとめる."""
    merged: list[CylFace] = []
    for c in cyls:
        hit = None
        for m in merged:
            if abs(m.radius - c.radius) > tol:
                continue
            a1 = np.array(m.axis)
            a2 = np.array(c.axis)
            if abs(abs(float(np.dot(a1, a2))) - 1.0) > 1e-6:
                continue
            d = np.array(c.center) - np.array(m.center)
            perp = d - np.dot(d, a1) * a1
            if np.linalg.norm(perp) > 1e-3:
                continue
            hit = m
            break
        if hit is None:
            merged.append(c)
        else:
            hit.area += c.area
            hit.faces.extend(c.faces)
    return merged
