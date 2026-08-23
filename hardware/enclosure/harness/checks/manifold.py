"""1. manifold — 水密・多様体か.

メッシュ側 (trimesh) と B-rep 側 (OCC BRepCheck_Analyzer) の両方を見る。
片方だけだと「B-rep は正しいがテッセレーションが破綻」「メッシュは閉じているが
B-rep が自己交差」のどちらかを取り逃がす。
"""

from __future__ import annotations

from OCP.BRepCheck import BRepCheck_Analyzer

from . import FAIL, PASS, WARN, CheckResult, register


@register("manifold")
def check(ctx) -> CheckResult:
    mesh = ctx.mesh
    shape = ctx.shape

    analyzer = BRepCheck_Analyzer(shape.wrapped)
    brep_valid = bool(analyzer.IsValid())

    watertight = bool(mesh.is_watertight)
    winding = bool(mesh.is_winding_consistent)
    n_boundary = int(len(mesh.edges) - len(mesh.edges_unique) * 0)  # placeholder, 下で上書き
    # 境界エッジ = 隣接三角形が 1 枚しかないエッジ
    import numpy as np

    counts = np.bincount(mesh.faces_unique_edges.ravel(), minlength=len(mesh.edges_unique))
    n_boundary = int((counts == 1).sum())
    n_nonmanifold = int((counts > 2).sum())

    brep_volume = float(shape.Volume())
    mesh_volume = float(mesh.volume) if watertight else float("nan")
    if watertight and brep_volume > 0:
        vol_err = abs(mesh_volume - brep_volume) / brep_volume
    else:
        vol_err = float("nan")

    m = {
        "brep_valid": brep_valid,
        "mesh_watertight": watertight,
        "winding_consistent": winding,
        "boundary_edges": n_boundary,
        "nonmanifold_edges": n_nonmanifold,
        "solids": len(shape.Solids()),
        "triangles": int(len(mesh.faces)),
        "brep_volume_mm3": round(brep_volume, 3),
        "mesh_volume_mm3": None if mesh_volume != mesh_volume else round(mesh_volume, 3),
        "volume_error": None if vol_err != vol_err else round(vol_err, 5),
    }

    if not brep_valid:
        return CheckResult(
            "manifold", FAIL, "B-rep が不正 (BRepCheck_Analyzer)", m,
            details=["自己交差・不正な面境界などが疑われる。build() のブーリアン順序を見直す"],
            limits=LIMITS,
        )
    if not watertight or n_boundary > 0 or n_nonmanifold > 0:
        return CheckResult(
            "manifold", FAIL,
            f"メッシュが閉じていない (境界エッジ {n_boundary} / 非多様体エッジ {n_nonmanifold})",
            m, limits=LIMITS,
        )
    if not winding:
        return CheckResult("manifold", WARN, "面の向きが一貫していない", m, limits=LIMITS)
    if vol_err == vol_err and vol_err > 0.02:
        return CheckResult(
            "manifold", WARN,
            f"メッシュ体積が B-rep と {vol_err*100:.1f}% ずれている（テッセレーション粗すぎ）",
            m, limits=LIMITS,
        )
    return CheckResult(
        "manifold", PASS,
        f"水密・多様体 (ソリッド {m['solids']} 個 / 三角形 {m['triangles']})",
        m, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: テッセレーション公差 (既定 0.05 mm) より細かい破綻、"
    "および複数ソリッドが「接しているだけ」の状態。"
)
