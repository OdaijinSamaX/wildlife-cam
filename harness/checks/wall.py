"""2. wall — 最小肉厚.

手法: 表面を面積重み付きでサンプリングし、各点から内向き法線方向にレイを飛ばして
最初に当たる裏面までの距離を肉厚とみなす（レイキャスト法）。

凹角では「隣の壁」に当たって偽の薄肉が出るので、当たった面の法線がレイと
おおむね平行（= 向かい合う壁）である場合だけ採用する。
"""

from __future__ import annotations

import numpy as np
import trimesh

from . import FAIL, PASS, CheckResult, register

EPS = 1e-3


@register("wall")
def check(ctx) -> CheckResult:
    mesh = ctx.mesh
    threshold = float(ctx.config("min_wall_mm", 1.6))
    n_samples = int(ctx.config("wall_samples", 6000))
    parallel_deg = float(ctx.config("wall_parallel_tol_deg", 25.0))
    min_samples = int(ctx.config("wall_min_samples", 5))
    # テッセレーション公差ぶんの測定ノイズ。閾値ちょうどの肉厚を FAIL にしないため。
    tol = float(ctx.config("wall_tolerance_mm", 0.01))
    seed = int(ctx.config("wall_seed", 12345))

    rng = np.random.default_rng(seed)
    pts, face_idx = trimesh.sample.sample_surface(mesh, n_samples, seed=seed)
    normals = mesh.face_normals[face_idx]
    origins = pts - normals * EPS
    directions = -normals

    loc, ray_idx, tri_idx = mesh.ray.intersects_location(
        origins, directions, multiple_hits=False
    )
    if len(ray_idx) == 0:
        return CheckResult(
            "wall", FAIL, "レイが 1 本も裏面に当たらなかった（形状が開いている可能性）",
            {"samples": n_samples}, limits=LIMITS,
        )

    dist = np.linalg.norm(loc - origins[ray_idx], axis=1) + EPS
    hit_normals = mesh.face_normals[tri_idx]
    cos_par = np.abs(np.einsum("ij,ij->i", hit_normals, directions[ray_idx]))
    keep = cos_par >= np.cos(np.radians(parallel_deg))

    if not keep.any():
        return CheckResult(
            "wall", FAIL, "向かい合う壁面を 1 つも検出できなかった",
            {"samples": n_samples}, limits=LIMITS,
        )

    dist = dist[keep]
    hit_pts = origins[ray_idx][keep]
    order = np.argsort(dist)
    min_wall = float(dist[order[0]])
    # 判定に使うのは「min_samples 本以上のレイが下回る厚み」。
    # 刻印文字の鋭角部やフィレットの端では 1 本だけ極端に薄い値が出るが、
    # それは構造としての薄肉ではないので、そこで FAIL させない。
    k = min(min_samples, len(dist)) - 1
    robust_min = float(dist[order[k]])
    below = dist < threshold - tol

    rows = []
    for i in order[:8]:
        rows.append(
            {
                "thickness_mm": round(float(dist[i]), 3),
                "x": round(float(hit_pts[i][0]), 2),
                "y": round(float(hit_pts[i][1]), 2),
                "z": round(float(hit_pts[i][2]), 2),
            }
        )

    m = {
        "min_wall_mm": round(min_wall, 3),
        "robust_min_wall_mm": round(robust_min, 3),
        "threshold_mm": threshold,
        "min_samples": min_samples,
        "tolerance_mm": tol,
        "parallel_tol_deg": parallel_deg,
        "p01_mm": round(float(np.percentile(dist, 1)), 3),
        "p05_mm": round(float(np.percentile(dist, 5)), 3),
        "median_mm": round(float(np.median(dist)), 3),
        "rays_used": int(len(dist)),
        "rays_below_threshold": int(below.sum()),
        "fraction_below": round(float(below.mean()), 4),
    }

    status = PASS if robust_min >= threshold - tol else FAIL
    summary = (
        f"min_wall = {robust_min:.3f} mm (閾値 {threshold:.2f}) "
        f"/ 単発の最小値 {min_wall:.3f} mm"
    )
    if status == FAIL:
        summary += f" / 閾値未満のサンプル {int(below.sum())} 本"
    return CheckResult(
        "wall", status, summary, m,
        table=rows,
        table_columns=["thickness_mm", "x", "y", "z"],
        limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: サンプル点が乗らないほど小さい薄肉パッチ（既定 6000 点）、"
    "および向かい合う面の角度差が 25 度を超える楔形の薄肉。"
    "レイは法線方向にしか飛ばさないので、斜め方向が最短になる形状は過大評価する。"
    "刻印文字の鋭角部やフィレット端では 1 本だけ極端に薄い値が出るので、"
    "判定には min_samples (既定 5) 本以上が下回る厚み (robust_min_wall_mm) を使い、"
    "単発の最小値 (min_wall_mm) は参考値として併記する。"
)
