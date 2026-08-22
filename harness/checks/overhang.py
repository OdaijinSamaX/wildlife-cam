"""6. overhang — 造形姿勢を適用したあとの下向き面.

定義: 面法線 n に対して overhang_deg = degrees(asin(-n.z))。
垂直な壁 = 0 度、水平な天井 = 90 度。閾値 (既定 50 度) を超える面を集計する。

ビルドプレートに接する第 1 層 (z <= zmin + first_layer_mm) は除外する。
残ったパッチは連結成分ごとにまとめ、XY 方向の差し渡し (span) が
bridge_span_mm 以下なら「ブリッジで渡せる」として WARN に留める。
"""

from __future__ import annotations

import numpy as np
import trimesh

from . import FAIL, PASS, WARN, CheckResult, register


def _unsupported_span(tri_xy) -> float:
    """パッチが実際に渡さなければならない幅 = XY 投影の最大内接円の直径.

    バウンディングボックスの対角だと、幅 1 mm のリング状のひさしを
    「直径 30 mm の張り出し」と誤判定してしまうのでこちらを使う。
    """
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    polys = []
    for t in tri_xy:
        p = Polygon(t)
        if p.is_valid and p.area > 1e-9:
            polys.append(p)
    if not polys:
        return 0.0
    shape = unary_union(polys).buffer(0)
    lo = 0.0
    hi = float(max(shape.bounds[2] - shape.bounds[0], shape.bounds[3] - shape.bounds[1])) / 2 + 1e-6
    for _ in range(24):
        mid = (lo + hi) / 2
        if shape.buffer(-mid).is_empty:
            hi = mid
        else:
            lo = mid
    return 2.0 * lo


@register("overhang")
def check(ctx) -> CheckResult:
    mesh = ctx.oriented_mesh
    max_deg = float(ctx.config("max_overhang_deg", 50.0))
    first_layer = float(ctx.config("first_layer_mm", 0.25))
    bridge_span = float(ctx.config("bridge_span_mm", 10.0))
    min_area = float(ctx.config("overhang_min_patch_mm2", 1.0))

    n = mesh.face_normals
    areas = mesh.area_faces
    nz = np.clip(n[:, 2], -1.0, 1.0)
    overhang_deg = np.degrees(np.arcsin(np.clip(-nz, -1.0, 1.0)))
    overhang_deg[nz >= 0] = 0.0

    zmin = float(mesh.bounds[0][2])
    tri_zmax = mesh.vertices[mesh.faces][:, :, 2].max(axis=1)
    on_plate = tri_zmax <= zmin + first_layer

    flagged = (overhang_deg > max_deg) & (~on_plate)
    total_area = float(areas[flagged].sum())
    plate_area = float(areas[(overhang_deg > max_deg) & on_plate].sum())

    m = {
        "max_overhang_deg": max_deg,
        "flagged_area_mm2": round(total_area, 2),
        "build_plate_area_mm2": round(plate_area, 2),
        "flagged_faces": int(flagged.sum()),
        "print_orientation_deg": list(ctx.print_orientation.get("rotate", (0, 0, 0))),
    }

    if not flagged.any():
        return CheckResult(
            "overhang", PASS,
            f"閾値 {max_deg:.0f} 度を超える下向き面なし（プレート接地面 {plate_area:.1f} mm2 は除外）",
            m, limits=LIMITS,
        )

    adj = mesh.face_adjacency
    keep = flagged[adj].all(axis=1)
    comps = trimesh.graph.connected_components(
        adj[keep], nodes=np.flatnonzero(flagged), min_len=1
    )

    rows = []
    worst_span = 0.0
    for comp in comps:
        comp = np.asarray(comp)
        a = float(areas[comp].sum())
        if a < min_area:
            continue
        verts = mesh.vertices[mesh.faces[comp]].reshape(-1, 3)
        span = _unsupported_span(mesh.vertices[mesh.faces[comp]][:, :, :2])
        worst_span = max(worst_span, span if span > bridge_span else 0.0)
        rows.append(
            {
                "area_mm2": round(a, 2),
                "xy_span_mm": round(span, 2),
                "max_deg": round(float(overhang_deg[comp].max()), 1),
                "z_mm": round(float(verts[:, 2].mean()), 2),
                "verdict": "要サポート" if span > bridge_span else "ブリッジ可",
            }
        )
    rows.sort(key=lambda r: -r["area_mm2"])
    m["patches"] = len(rows)
    m["max_unbridgeable_span_mm"] = round(worst_span, 2)

    cols = ["area_mm2", "xy_span_mm", "max_deg", "z_mm", "verdict"]
    if not rows:
        return CheckResult(
            "overhang", PASS,
            f"閾値超の面はあるが、いずれも {min_area} mm2 未満の微小パッチ",
            m, limits=LIMITS,
        )
    if worst_span > 0:
        return CheckResult(
            "overhang", FAIL,
            f"サポートが要る張り出し {len([r for r in rows if r['verdict']=='要サポート'])} 箇所 "
            f"(最大 span {worst_span:.1f} mm / 合計 {total_area:.1f} mm2)",
            m, table=rows[:12], table_columns=cols, limits=LIMITS,
        )
    return CheckResult(
        "overhang", WARN,
        f"下向き面 {len(rows)} 箇所 (合計 {total_area:.1f} mm2) — いずれも span "
        f"{bridge_span:.0f} mm 以下でブリッジ可",
        m, table=rows[:12], table_columns=cols, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 面の傾きしか見ていないので「下に支えがあるかどうか」は判定していない。"
    "階段状に少しずつ張り出す形状（各面は閾値以下）は素通しする。span は XY バウンディング"
    "ボックスの対角なので、細長い穴の天井を過大評価する。サポート材の実際の可否は"
    "スライサでしか分からない。"
)
