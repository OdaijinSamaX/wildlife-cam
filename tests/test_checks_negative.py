"""ネガティブテスト — 意図的に壊した設計で各チェックが FAIL することの実証.

このリポジトリで一番危ないのは「チェックが常に PASS を返すだけの飾りになること」。
ここが落ちるようになったら、そのチェックはもう仕事をしていない。

各テストは PARAMS を上書きして「変種」を作る。実際の設計ファイルをそのまま使うので、
設計が育ってもテストの前提が腐りにくい。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness.checks import FAIL, run_all
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
COUPON = ROOT / "designs" / "wildlife_cam" / "fit_coupon.py"
BEZEL = ROOT / "designs" / "wildlife_cam" / "pir_bezel.py"
UNCLAIMED = ROOT / "tests" / "fixtures" / "unclaimed_hole.py"


def result(path, only, override=None):
    ctx = load_design(path, params_override=override)
    results = run_all(ctx, only=[only])
    assert len(results) == 1
    return results[0]


# --- 基準線: 手を入れていない設計は通る -----------------------------------


@pytest.mark.parametrize("path,check", [
    (COUPON, "wall"), (COUPON, "bbox"), (COUPON, "openings"), (COUPON, "layout"),
    (COUPON, "overhang"),
    (BEZEL, "wall"), (BEZEL, "clearance"), (BEZEL, "openings"), (BEZEL, "layout"),
])
def test_baseline_designs_pass(path, check):
    r = result(path, check)
    assert r.status != FAIL, f"{path.name} / {check}: {r.summary}"


# --- 1. 肉厚 0.8 mm の変種 -> wall が FAIL ---------------------------------


def test_wall_fails_on_thin_seal_land():
    """フェイス O リング溝を 2.5 mm 深く掘ると、溝底と PCB ポケットの間が 0.8 mm になる."""
    r = result(BEZEL, "wall", {"face_groove_d": 2.5})
    assert r.status == FAIL, r.summary
    assert r.measurements["robust_min_wall_mm"] == pytest.approx(0.8, abs=0.05)
    assert r.measurements["threshold_mm"] == 1.6


def test_wall_passes_on_baseline_bezel():
    r = result(BEZEL, "wall")
    assert r.measurements["robust_min_wall_mm"] >= 1.6 - 0.01


# --- 2. 部品を壁にめり込ませた変種 -> clearance が FAIL ---------------------


def test_clearance_fails_when_component_bites_into_wall():
    """内径をドームより細くすると、HC-SR501 のドームがキャリアに食い込む."""
    r = result(BEZEL, "clearance", {"bore_dia": 22.0})
    assert r.status == FAIL, r.summary
    assert r.measurements["violations"] >= 1
    rows = {row["component"]: row for row in r.table}
    row = rows["HC-SR501 PIR"]
    assert row["verdict"] == "実体が干渉"
    assert row["solid_overlap_mm3"] > 1.0


def test_clearance_fails_on_clearance_shortfall_only():
    """実体は当たらないがクリアランスだけ足りない場合も拾う."""
    r = result(BEZEL, "clearance", {"bore_dia": 23.05})
    assert r.status == FAIL, r.summary
    rows = {row["component"]: row for row in r.table}
    assert rows["HC-SR501 PIR"]["solid_overlap_mm3"] == pytest.approx(0.0, abs=1e-3)
    assert rows["HC-SR501 PIR"]["overlap_mm3"] > 0.0


# --- 3. 300 mm の変種 -> bbox が FAIL --------------------------------------


def test_bbox_fails_when_larger_than_build_volume():
    r = result(COUPON, "bbox", {"plate_l": 300.0})
    assert r.status == FAIL, r.summary
    assert r.measurements["x_mm"] == pytest.approx(300.0, abs=0.01)
    assert r.measurements["margin_mm"][0] < 0


# --- 4. 意図しない貫通穴 -> openings が検出 --------------------------------


def test_openings_detects_unintended_through_holes():
    """ヒートセット下穴の深さを板厚より深くすると、止まり穴が貫通穴に化ける."""
    base = result(COUPON, "openings")
    assert base.status != FAIL, base.summary
    base_through = {row["diameter_mm"] for row in base.table if row["through"]}

    broken = result(COUPON, "openings", {"heatset_depth": 20.0})
    assert broken.status == FAIL, broken.summary
    broken_through = {row["diameter_mm"] for row in broken.table if row["through"]}

    new = broken_through - base_through
    assert new == {4.0, 4.2, 4.4}, f"検出された新しい貫通穴: {sorted(new)}"
    assert broken.measurements["undeclared_openings"] == 3
    assert any("未宣言の貫通穴" in d for d in broken.details)


def test_openings_flags_missing_declared_opening():
    """宣言した開口が消えた場合も FAIL させる（穴の付け忘れを止める）."""
    r = result(COUPON, "openings", {"clear_dias": (3.2, 3.4, 3.4)})
    assert r.status == FAIL, r.summary
    assert r.measurements["missing_declared_openings"] >= 1


# --- 5. overhang が造形姿勢に反応することの確認 -----------------------------


def test_overhang_reacts_to_print_orientation():
    """クーポンを 90 度立てると、平置きでは無かった張り出しが出る."""
    ctx = load_design(COUPON)
    flat = run_all(ctx, only=["overhang"])[0]

    ctx2 = load_design(COUPON)
    ctx2.print_orientation = {"rotate": (90, 0, 0)}
    tilted = run_all(ctx2, only=["overhang"])[0]

    assert tilted.measurements["flagged_area_mm2"] > flat.measurements["flagged_area_mm2"]
    assert tilted.status == FAIL, tilted.summary


# --- 6. 単一ソリッド内のフィーチャの食い合い -> layout が FAIL ---------------
#
# 実際に出た不具合の再現。初版の fit_coupon では O リング溝の帯が基準ピン
# φ10.0 の根元を 0.95 mm 削っていた。interference は別ソリッド同士しか見ず、
# openings は溝を止まり穴としか見ないので、どちらにも掛からなかった。


def test_layout_fails_when_groove_undercuts_the_reference_pin():
    r = result(COUPON, "layout", {"oring_cx": 16.0, "oring_cy": -8.0})
    assert r.status == FAIL, r.summary
    pairs = {frozenset((row["a"], row["b"])) for row in r.table}
    assert frozenset(("shaft_ref_pin", "oring_groove")) in pairs, r.table
    hit = next(row for row in r.table
               if {row["a"], row["b"]} == {"shaft_ref_pin", "oring_groove"})
    assert hit["overlap_mm3"] > 1.0


def test_layout_catches_undercut_even_though_z_ranges_of_the_solids_differ():
    """ピン (z=8..20) と溝 (z=6.5..8) は体積が重ならない.

    claim を「フィーチャが所有すべき材料領域」として宣言しているからこそ
    捕まる、という規約そのもののテスト。
    """
    ctx = load_design(COUPON, params_override={"oring_cx": 16.0, "oring_cy": -8.0})
    pin = next(f for f in ctx.features if f.name == "shaft_ref_pin")
    groove = next(f for f in ctx.features if f.name == "oring_groove")
    # ピンの実体は板の上にしか無い
    assert pin.bbox.zmin < 1e-6          # claim は板の底まで伸びている
    assert groove.bbox.zmax <= ctx.params["plate_t"] + 1e-6
    assert pin.region.intersect(groove.region).Volume() > 1.0


def test_layout_fails_when_screws_bite_into_the_face_seal_groove():
    """ベゼルのねじピッチを詰めると、取付ねじがフェイス O リング溝を食う."""
    r = result(BEZEL, "layout", {"screw_pcd": 42.0})
    assert r.status == FAIL, r.summary
    pairs = {frozenset((row["a"], row["b"])) for row in r.table}
    assert any("face_oring_groove" in pair and any(n.startswith("screw_") for n in pair)
               for pair in pairs), r.table


def test_layout_detects_an_undeclared_hole():
    r = result(UNCLAIMED, "layout")
    assert r.status == FAIL, r.summary
    assert r.measurements["unclaimed_holes"] == 1
    assert any("宣言し忘れ" in row["note"] for row in r.table)


def test_layout_passes_when_every_hole_is_declared():
    r = result(UNCLAIMED, "layout", {"declare_both": True})
    assert r.status != FAIL, r.summary
    assert r.measurements["unclaimed_holes"] == 0


def test_layout_warns_when_nothing_is_declared():
    """宣言が無いときは黙って PASS せず WARN にする（気づかせるため）."""
    ctx = load_design(UNCLAIMED)
    ctx.features = []
    r = run_all(ctx, only=["layout"])[0]
    assert r.status == "WARN", r.summary


# --- 7. 造形姿勢の宣言が守られていること ------------------------------------


def test_pir_carrier_bore_axis_stays_parallel_to_the_build_direction():
    """内径の軸が造形方向に平行であること（docs/DECISIONS.md D-001 の宣言）.

    寝かせると内径の積層線が軸方向に走り、シール面／接着面を縦断する
    連続した漏れ経路になる。姿勢を勝手に変えたらここで止まる。
    """
    import numpy as np

    from harness import geom

    ctx = load_design(BEZEL)
    axis = np.array(ctx.module.BORE_AXIS, dtype=float)
    rot = ctx.print_orientation.get("rotate", (0, 0, 0))
    probe = geom.rotate_shape(
        __import__("cadquery").Solid.makeCylinder(1.0, 10.0), rot
    )
    bb = probe.BoundingBox()
    # 軸に沿った寸法だけが 10 mm になる = 軸が Z のままである
    assert (bb.xlen, bb.ylen) == pytest.approx((2.0, 2.0), abs=0.01)
    assert bb.zlen == pytest.approx(10.0, abs=0.01)
    assert tuple(axis) == (0.0, 0.0, 1.0)
