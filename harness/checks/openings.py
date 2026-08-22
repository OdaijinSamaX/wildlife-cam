"""7. openings — 内外を貫通する開口の一覧.

屋外筐体で「気づかないうちに水の入る穴が空いていた」を止めるための網。
2 通りの見方を併用する。

A. B-rep パス
   内向き円筒面（= 穴の内壁）を拾い、軸方向に少し外へ出た点が材料の中かどうかで
   貫通穴 / 止まり穴を分ける。丸穴なら径と開口面積が厳密に出る。

B. ボクセルパス
   形状をボクセル化して空気側の連結成分を取る。閉じた空洞（= 密閉された内部空間）
   と外界を区別し、内部空間が外界とつながっていれば「漏れ経路あり」と判定する。
   さらにボール半径を増やしながらクロージングを掛け、内部が外界から切れる半径から
   最大の喉径（= 一番大きい隙間の直径）を推定する。丸穴でないスリットや隙間は
   こちら側でしか見つからない。

CHECK_CONFIG:
  expected_openings: [{"diameter_mm": 6.0, "count": 1, "note": "ケーブルグランド PG7"}]
      宣言があれば、宣言と一致しない貫通穴を FAIL にする。宣言が無ければ WARN。
  expect_sealed: True にすると、内部空間が外界とつながっていた時点で FAIL。
  interior_point: 内部空間の代表点 (x, y, z)。省略時は最大の閉空洞を使う。
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

from .. import geom
from . import FAIL, PASS, WARN, CheckResult, register

AXIS_PROBE_MM = 0.5
PROBE_INSET_MM = 0.2
SWEEP_RADII_MM = (0.25, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0, 8.0)


def _brep_openings(shape, min_dia):
    cyls = geom.merge_coaxial(geom.internal_cylinders(shape, min_dia=min_dia))
    rows = []
    for i, c in enumerate(cyls):
        axis = np.array(c.axis, dtype=float)
        base = np.array(c.axis_point, dtype=float)   # 軸上の点
        t_lo, t_hi = c.axial_extent()
        # 軸上ではなく「穴の内壁のすぐ内側」で探る。軸上だと、貫通穴の中に
        # 掘った O リング溝まで貫通扱いになってしまう。
        offset = c.radial_dir() * max(c.radius - PROBE_INSET_MM, 0.0)
        p_lo = base + (t_lo - AXIS_PROBE_MM) * axis + offset
        p_hi = base + (t_hi + AXIS_PROBE_MM) * axis + offset
        lo_solid = geom.point_inside(shape, p_lo)
        hi_solid = geom.point_inside(shape, p_hi)
        through = (not lo_solid) and (not hi_solid)
        rows.append(
            {
                "id": f"hole{i}",
                "kind": "貫通" if through else "止まり",
                "diameter_mm": round(c.diameter, 3),
                "aperture_mm2": round(np.pi * c.radius**2, 2),
                "axis": tuple(round(float(v), 2) for v in axis),
                "center": tuple(round(float(v), 1) for v in c.probe_point(c.radius)),
                "through": through,
            }
        )
    rows.sort(key=lambda r: (-r["diameter_mm"], r["id"]))
    return rows


def _leak_analysis(ctx):
    vg = ctx.voxels
    labels, count, border = geom.air_components(vg)
    pitch = vg.pitch
    vox_vol = vg.voxel_volume

    cavities = []
    for lab in range(1, count + 1):
        if lab in border:
            continue
        mask = labels == lab
        n = int(mask.sum())
        if n < 2:
            continue
        idx = np.argwhere(mask)
        centroid = vg.index_to_xyz(idx.mean(axis=0))
        cavities.append(
            {
                "label": lab,
                "volume_mm3": round(n * vox_vol, 2),
                "centroid": tuple(round(float(v), 1) for v in centroid),
                "voxels": n,
            }
        )
    cavities.sort(key=lambda c: -c["volume_mm3"])

    seed = ctx.config("interior_point", None)
    seed_source = "CHECK_CONFIG.interior_point"
    if seed is None:
        if cavities:
            seed = cavities[0]["centroid"]
            seed_source = "最大の閉空洞の重心"
        else:
            return {
                "cavities": cavities,
                "seed": None,
                "seed_source": "なし",
                "leaking": None,
                "throat_diameter_mm": None,
                "pitch_mm": pitch,
            }

    i = vg.xyz_to_index(seed)
    seed_label = int(labels[i])
    if seed_label == 0:
        return {
            "cavities": cavities,
            "seed": tuple(round(float(v), 1) for v in seed),
            "seed_source": seed_source,
            "leaking": None,
            "throat_diameter_mm": None,
            "pitch_mm": pitch,
            "note": "内部代表点が材料の中にある。interior_point を見直すこと",
        }

    leaking = seed_label in border
    throat = None
    if leaking:
        for r_mm in SWEEP_RADII_MM:
            r_vox = r_mm / pitch
            if r_vox < 0.75:
                continue
            closed = geom.morph_close(vg.grid, r_vox)
            lab2, n2 = ndimage.label(~closed, structure=geom.CONN6)
            b2 = set()
            for sl in (
                lab2[0], lab2[-1], lab2[:, 0], lab2[:, -1], lab2[:, :, 0], lab2[:, :, -1]
            ):
                b2.update(int(v) for v in np.unique(sl))
            b2.discard(0)
            l2 = int(lab2[i])
            if l2 != 0 and l2 not in b2:
                throat = 2.0 * r_mm
                break
    return {
        "cavities": cavities,
        "seed": tuple(round(float(v), 1) for v in seed),
        "seed_source": seed_source,
        "leaking": leaking,
        "throat_diameter_mm": throat,
        "pitch_mm": pitch,
    }


def _match_expected(rows, expected, tol):
    """宣言と検出を突き合わせ、(未宣言の穴, 見つからなかった宣言) を返す."""
    remaining = [r for r in rows if r["through"]]
    unmatched_expected = []
    for e in expected:
        d = float(e["diameter_mm"])
        want = int(e.get("count", 1))
        etol = float(e.get("tol_mm", tol))
        got = 0
        for r in list(remaining):
            if got >= want:
                break
            if abs(r["diameter_mm"] - d) <= etol:
                r["expected"] = e.get("note", f"phi{d}")
                remaining.remove(r)
                got += 1
        if got < want:
            unmatched_expected.append({**e, "found": got})
    return remaining, unmatched_expected


@register("openings")
def check(ctx) -> CheckResult:
    min_dia = float(ctx.config("openings_min_diameter_mm", 0.8))
    tol = float(ctx.config("openings_match_tol_mm", 0.3))
    expected = ctx.config("expected_openings", None)
    expect_sealed = ctx.config("expect_sealed", None)

    rows = _brep_openings(ctx.shape, min_dia)
    leak = _leak_analysis(ctx)

    through = [r for r in rows if r["through"]]
    m = {
        "cylindrical_openings": len(through),
        "blind_holes": len(rows) - len(through),
        "total_aperture_mm2": round(sum(r["aperture_mm2"] for r in through), 2),
        "largest_diameter_mm": max((r["diameter_mm"] for r in through), default=0.0),
        "sealed_cavities": len(leak["cavities"]),
        "sealed_cavity_volume_mm3": round(sum(c["volume_mm3"] for c in leak["cavities"]), 1),
        "interior_seed": leak["seed"],
        "interior_seed_source": leak["seed_source"],
        "interior_leaks_to_outside": leak["leaking"],
        "leak_throat_diameter_mm": leak["throat_diameter_mm"],
        "voxel_pitch_mm": leak["pitch_mm"],
    }

    details = []
    if leak.get("note"):
        details.append(leak["note"])
    for c in leak["cavities"][:5]:
        details.append(
            f"閉じた内部空洞: {c['volume_mm3']} mm3 @ {c['centroid']}"
        )
    if leak["leaking"]:
        t = leak["throat_diameter_mm"]
        details.append(
            "内部空間は外界とつながっている"
            + (f"（最大の喉径 ≈ φ{t:.1f} mm）" if t else "（喉径はスイープ範囲外）")
        )

    problems = []
    if expect_sealed and leak["leaking"]:
        problems.append("expect_sealed=True だが内部空間が外界に通じている")

    cols = ["id", "kind", "diameter_mm", "aperture_mm2", "axis", "center"]
    if expected is not None:
        extra, missing = _match_expected(rows, expected, tol)
        cols.append("expected")
        for r in rows:
            r.setdefault("expected", "未宣言" if r["through"] else "-")
        m["undeclared_openings"] = len(extra)
        m["missing_declared_openings"] = len(missing)
        for r in extra:
            problems.append(
                f"未宣言の貫通穴 φ{r['diameter_mm']} mm @ {r['center']}"
            )
        for e in missing:
            problems.append(
                f"宣言した開口が見つからない: φ{e['diameter_mm']} x{e.get('count',1)} "
                f"({e.get('note','')}) 検出 {e['found']} 個"
            )
        if problems:
            return CheckResult(
                "openings", FAIL,
                f"開口の宣言と実物が食い違う ({len(problems)} 件)",
                m, details=details + problems, table=rows,
                table_columns=cols, limits=LIMITS,
            )
        return CheckResult(
            "openings", PASS,
            f"貫通開口 {len(through)} 箇所・合計 {m['total_aperture_mm2']} mm2、"
            f"すべて宣言どおり",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS,
        )

    if problems:
        return CheckResult(
            "openings", FAIL, problems[0], m,
            details=details + problems, table=rows, table_columns=cols, limits=LIMITS,
        )
    return CheckResult(
        "openings", WARN,
        f"貫通開口 {len(through)} 箇所・合計 {m['total_aperture_mm2']} mm2 "
        "— CHECK_CONFIG['expected_openings'] が未宣言なので人が意図を確認すること",
        m, details=details, table=rows, table_columns=cols, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: B-rep パスは円筒面しか見ないので、角穴・スリット・分割線の隙間は"
    "表に出ない（ボクセルパスの漏れ判定でしか捕まらない）。ボクセルパスは既定ピッチ "
    "0.6 mm なので、それ未満の隙間は塞がっているように見える。喉径のスイープは "
    "0.5〜16 mm の離散値で、その間は上側に丸める。O リングやガスケットの"
    "「締めれば塞がる」隙間も開口として数える。"
)
