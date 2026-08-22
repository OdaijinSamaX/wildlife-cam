"""5. layout — 単一ソリッド内のフィーチャ同士の食い合い.

`interference` は別ソリッド同士しか見ない。`openings` は溝を止まり穴としか見ない。
そのため「O リング溝が基準ピンの根元を削っている」ような、**1 個のソリッドの中で
フィーチャが場所を奪い合っている**状態を検出する手段が無かった。

このチェックは設計側の宣言（`FEATURES` / `features(p)`）を突き合わせる。

  1. claim を総当たりでブーリアン積し、体積が 0 でなければ FAIL
  2. B-rep から見つかった穴（内向き円筒面）が、どの claim にも入っていなければ FAIL
     — 宣言し忘れたフィーチャは衝突判定の対象外になってしまうため

claim の作り方の規約は `harness/feature.py` の docstring にある。要点は
**claim はフィーチャ自身の体積ではなく「所有すべき材料領域」**であること。
台座から立つピンは足元の板を厚み方向いっぱいまで claim する。そうしないと、
まさに今回の不具合（ピン z=8..20 と溝 z=6.5..8 が z で重ならない）を取り逃がす。
"""

from __future__ import annotations

from itertools import combinations

from .. import geom
from ..feature import bboxes_overlap
from . import FAIL, PASS, WARN, CheckResult, register


@register("layout")
def check(ctx) -> CheckResult:
    feats = ctx.features
    tol = float(ctx.config("layout_volume_tol_mm3", 1e-3))
    min_dia = float(ctx.config("openings_min_diameter_mm", 0.8))

    if not feats:
        return CheckResult(
            "layout", WARN,
            "FEATURES が未宣言 — 単一ソリッド内のフィーチャ同士の食い合いは検出できない",
            {"features": 0},
            details=[
                "designs/*.py に `def features(p)` を足すと、フィーチャの占有領域"
                "（claim）を総当たりで突き合わせる。書き方は harness/feature.py 参照",
            ],
            limits=LIMITS,
        )

    rows = []
    worst = 0.0
    pairs = 0
    skipped = 0
    for a, b in combinations(feats, 2):
        if not bboxes_overlap(a.bbox, b.bbox):
            skipped += 1
            continue
        pairs += 1
        try:
            common = a.region.intersect(b.region)
            vol = float(common.Volume()) if common is not None else 0.0
        except Exception as exc:
            rows.append({"a": a.name, "b": b.name, "overlap_mm3": "ERROR",
                         "note": type(exc).__name__})
            continue
        worst = max(worst, vol)
        if vol > tol:
            c = common.Center()
            rows.append({
                "a": a.name,
                "b": b.name,
                "overlap_mm3": round(vol, 3),
                "note": f"重なり中心 ({c.x:.1f}, {c.y:.1f}, {c.z:.1f})",
            })

    # 宣言し忘れたフィーチャ（穴）の検出
    unclaimed = []
    cyls = geom.merge_coaxial(geom.internal_cylinders(ctx.shape, min_dia=min_dia))
    for c in cyls:
        # 穴の内壁の少し内側・軸方向中央。claim は必ずこの点を含むはず。
        pt = c.probe_point(inset=0.02 * c.radius)
        if not any(geom.point_inside(f.region, pt) for f in feats):
            unclaimed.append({
                "a": f"phi{c.diameter:.2f} @ ({pt[0]:.1f}, {pt[1]:.1f}, {pt[2]:.1f})",
                "b": "-",
                "overlap_mm3": "-",
                "note": "どの claim にも入っていない（宣言し忘れ）",
            })

    m = {
        "features": len(feats),
        "pairs_checked": pairs,
        "pairs_skipped_by_bbox": skipped,
        "overlapping_pairs": len([r for r in rows if r["overlap_mm3"] != "ERROR"]),
        "max_overlap_mm3": round(worst, 3),
        "unclaimed_holes": len(unclaimed),
        "margins_mm": sorted({round(f.margin, 3) for f in feats}),
    }
    cols = ["a", "b", "overlap_mm3", "note"]

    if rows or unclaimed:
        n = len(rows) + len(unclaimed)
        head = []
        if rows:
            head.append(f"フィーチャが {len(rows)} 組で食い合っている")
        if unclaimed:
            head.append(f"宣言されていない穴が {len(unclaimed)} 個")
        return CheckResult(
            "layout", FAIL, " / ".join(head), m,
            table=rows + unclaimed, table_columns=cols, limits=LIMITS,
        )

    return CheckResult(
        "layout", PASS,
        f"フィーチャ {len(feats)} 個、{pairs} 組を実測して食い合いなし"
        f"（bbox で {skipped} 組を除外）",
        m, limits=LIMITS,
    )


LIMITS = (
    "見逃すもの: 宣言が実物とずれていれば当然すり抜ける。build() と features() は"
    "必ず同じ PARAMS から組み立てること。穴以外のフィーチャ（ボス・刻印・溝の内壁）は"
    "宣言し忘れても検出できない（穴だけは B-rep の内向き円筒面から突き合わせている）。"
    "部品の外形線からの距離（縁までの肉）は見ていない。claim は Z 軸方向の円柱・円環・"
    "直方体と、任意形状のバウンディングボックスしか作れないので、斜めの穴や複雑な"
    "ポケットは過大に包むことになる。"
)
