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
LID = ROOT / "designs" / "wildlife_cam" / "camera_unit_lid.py"
TRAY = ROOT / "designs" / "wildlife_cam" / "pcb_tray.py"


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
    (LID, "seal"),
    (TRAY, "underside"),
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


# --- 8. 締結点を四隅 4 点に戻した変種 -> seal が FAIL ------------------------


def test_seal_fails_when_the_lid_is_held_only_at_the_four_corners():
    """**人間の指摘そのもの。** 長辺 198 mm を四隅 4 点で押さえると中央が浮く.

    支点だけを元の 2 段（z=12 と 186）に戻す。形状は変えていないので、
    「締結点の間隔が広すぎる」ことだけが FAIL の原因になる。
    """
    r = result(LID, "seal", {"support_z": (12.0, 186.0)})
    assert r.status == FAIL, r.summary
    assert r.measurements["lid_long_edges: 締結点の最大間隔 [mm]"] == 174.0
    assert r.measurements["lid_long_edges: 最小圧縮率 [%]"] < 15.0
    # 浮くのは長辺の中央
    assert r.table[0]["at_z"] == pytest.approx(99.0, abs=4.0)


def test_seal_warns_when_the_gasket_is_harder_than_declared():
    """硬いゴムほど蓋を押し開く力が強い。材質の申告が効いていることの確認.

    90 Shore A でも 6 点なら下限 15% は割らない（15.5%）。**そこが余裕の正体**で、
    「余裕が無い」ことは WARN として出る。黙って PASS にはしない。
    """
    hard = result(LID, "seal", {"gasket_shore_a": 90.0})
    soft = result(LID, "seal", {"gasket_shore_a": 50.0})
    assert hard.status == "WARN", hard.summary
    assert soft.status == "PASS", soft.summary
    assert (hard.measurements["lid_long_edges: 最小圧縮率 [%]"]
            < soft.measurements["lid_long_edges: 最小圧縮率 [%]"])


def test_seal_passes_with_the_middle_pair_added():
    r = result(LID, "seal")
    assert r.status == "PASS", r.summary
    assert r.measurements["lid_long_edges: 最小圧縮率 [%]"] >= 20.0


# --- 12. 捕捉式ねじ -> captive が FAIL -------------------------------------
#
# **捕捉は「寸法の連鎖」でしか成立しない。** 連鎖のどこが切れても現地で困るので、
# 切れ方ごとに 1 本ずつ壊して落ちることを実証する。
# ここが全部 PASS しか返さなくなったら、captive はもう仕事をしていない。


def test_captive_fails_when_the_retainer_pocket_is_missing():
    """**ポケットを彫り忘れた蓋。** リテーナを受ける肉が無い = ねじは抜けて落ちる.

    現地で落としたねじは落ち葉の中で二度と見つからない（AGENTS.md §4.9 原則 1）。
    """
    r = result(LID, "captive", {"retainer_pocket_d": 0.0})
    assert r.status == FAIL, r.summary
    assert "捕捉されない" in " ".join(r.details), r.details


def test_captive_fails_when_the_pocket_is_too_shallow_to_release():
    """**ポケットが浅すぎる蓋。** ねじが相手から抜けきる前にリテーナが止まる.

    これは「ねじが落ちる」の逆で、**現地で蓋が開かない**。
    浅い方が安全そうに見えるので、間違えやすい向きである。
    """
    r = result(LID, "captive", {"retainer_pocket_d": 3.0})
    assert r.status == FAIL, r.summary
    assert "蓋が開かない" in " ".join(r.details), r.details


def test_captive_fails_when_the_screw_bottoms_out_in_the_pilot_hole():
    """**長すぎる蝶ねじ。** 先端が下穴の底を突くと、締めたつもりで面圧が出ない.

    ねじを買い替えるだけで起きる。外から見て分からないのが厄介なところ。
    """
    r = result(LID, "captive", {"screw_len": 40.0, "big_screw_len": 40.0})
    assert r.status == FAIL, r.summary
    assert "下穴の底" in " ".join(r.details), r.details


def test_captive_fails_when_the_screw_is_too_short_to_reach():
    """**短すぎる蝶ねじ。** 蓋を通り抜けた先で相手に届かない."""
    r = result(LID, "captive", {"screw_len": 20.0, "big_screw_len": 20.0})
    assert r.status == FAIL, r.summary
    assert "届かない" in " ".join(r.details), r.details


def test_captive_passes_on_the_designed_lid():
    """基準線。設計どおりの蓋は「落ちない・抜けきる・平らに座る」を満たす."""
    from harness.checks import PASS

    r = result(LID, "captive")
    assert r.status == PASS, (r.summary, r.details)
    assert r.measurements["screw_1: 噛み合い engage [mm]"] == pytest.approx(8.0, abs=0.05)
    assert r.measurements["screw_1: 緩めきったときの出しろ [mm]"] < 3.0


def test_captive_measures_the_pocket_from_the_built_shape_not_the_params():
    """**宣言ではなく build() した形から測っていること。**

    PARAMS を触ればチェックの実測値が動く。動かなければ、それは形を見ていない証拠。
    """
    a = result(LID, "captive", {"retainer_pocket_d": 10.5})
    b = result(LID, "captive", {"retainer_pocket_d": 12.0})
    ka = "screw_1: 後退できる量 travel [mm]"
    assert b.measurements[ka] - a.measurements[ka] == pytest.approx(1.5, abs=0.05)


# --- 13. 基板の下の突起 -> underside が FAIL --------------------------------
#
# **12 種のどれも「実装部品が基板の下に出ている」ことを捕まえなかった。**
# `clearance` は座面のクリアランスを 0 にしてよい規約（AGENTS.md §4）なので、
# 基板の下にぶら下がっているものを「意図した接触」として飲み込んでしまう。
# 実際に CSI レスキューのナット（基板下面から 2.7 mm。実測 2026-08-23）で
# それが起きた。ここが全部 PASS しか返さなくなったら、underside はもう仕事をしていない。


def test_underside_fails_when_the_standoff_is_shorter_than_the_nut():
    """**座面を 2.0 mm に縮めると、2.7 mm のナットが板に当たる。**

    現物では「基板が座らない / ねじを締めると基板が反る」になる。
    """
    r = result(TRAY, "underside", {"boss_h": 2.0})
    assert r.status == FAIL, r.summary
    rows = {row["突起"]: row for row in r.table}
    assert rows["rescue_nut_0"]["verdict"] == FAIL
    assert rows["rescue_nut_0"]["実測隙間_mm"] == pytest.approx(2.0, abs=0.05)
    assert rows["rescue_nut_0"]["要求_mm"] == pytest.approx(3.1)
    # 0.4 mm しか出ていない Pi 自身の実装部品は、2.0 mm あれば当たらない
    assert rows["pi_bot_comp"]["verdict"] == "PASS"


def test_underside_fails_when_the_pocket_is_missing_entirely():
    """**ポケットを塞ぐと、パッドの天面が基板下面と同じ高さに来る。**

    これは「受け面が基板にちょうど接している = 隙間 0」であって、
    **「その下の板の前面までが隙間」ではない。** レイの交点を
    `depth > 0` で拾うと、ちょうど基板面にある面が除外されて
    **5.9 mm という嘘の隙間**が出る（実際にそう書いて取り逃がした）。
    ここはその回帰テストでもある。
    """
    r = result(TRAY, "underside", {"nut_bore": 0.0})
    assert r.status == FAIL, r.summary
    rows = {row["突起"]: row for row in r.table}
    assert rows["rescue_nut_0"]["verdict"] == FAIL
    assert rows["rescue_nut_0"]["実測隙間_mm"] == pytest.approx(0.0, abs=0.01), \
        "基板面にある受け面を『隙間ゼロ』と読めていない"
    assert "当たる" in " ".join(r.details)


def test_underside_measures_the_shape_not_the_declared_numbers():
    """**PARAMS の数字ではなく形から測っていること。**

    座面を 0.5 mm 伸ばしたら、実測の隙間もちょうど 0.5 mm 増えること。
    """
    a = result(TRAY, "underside", {"boss_h": 3.4})
    b = result(TRAY, "underside", {"boss_h": 3.9})
    ga = a.measurements["rescue_nut_0: 実測の隙間 [mm]"]
    gb = b.measurements["rescue_nut_0: 実測の隙間 [mm]"]
    assert gb - ga == pytest.approx(0.5, abs=0.05), (ga, gb)


def test_underside_passes_on_the_designed_tray():
    r = result(TRAY, "underside")
    assert r.status == "PASS", r.summary
    assert r.measurements["宣言した突起の数"] == 3
