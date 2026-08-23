"""寸法補正テーブルのテスト.

実測から起こした値そのものと、「設計が必ずテーブルを通る」という約束を守る。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from harness import fit
from harness.checks import FAIL, PASS, WARN, run_all
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
#: 先頭が "_" のファイルは設計ではなく共通モジュール（harness list と同じ規則）
DESIGNS = sorted(p for p in (ROOT / "designs").rglob("*.py")
                 if not p.name.startswith("_"))
COUPON_V1 = ROOT / "designs" / "wildlife_cam" / "fit_coupon.py"
COUPON_V2 = ROOT / "designs" / "wildlife_cam" / "fit_coupon_v2.py"
BEZEL = ROOT / "designs" / "wildlife_cam" / "pir_bezel.py"
UNCLAIMED = ROOT / "tests" / "fixtures" / "unclaimed_hole.py"


# --- テーブルの値そのもの（fit_coupon.md の実測から起こした） ---------------


def test_table_provenance_is_complete():
    t = fit.ASA_P1S
    assert t.id == "asa-p1s-0.4mm-2026-08-22"
    assert t.material == "ASA"
    assert t.printer == "Bambu Lab P1S"
    assert t.nozzle_mm == 0.4
    assert t.layer_mm == 0.2
    assert t.orientation == "平置き"
    assert t.measured_on == "2026-08-22"
    assert t.source.endswith("fit_coupon.md")


@pytest.mark.parametrize("target,drawn", [
    (10.1, 10.4), (10.2, 10.5), (10.3, 10.6), (10.4, 10.7), (18.0, 18.3),
])
def test_large_holes_get_plus_030(target, drawn):
    """軸穴 4 点が誤差 -0.30 で一定だったので +0.30."""
    assert fit.ASA_P1S.hole(target) == pytest.approx(drawn, abs=1e-9)


@pytest.mark.parametrize("target,drawn", [
    (3.2, 3.45), (3.4, 3.65), (3.6, 3.85), (4.0, 4.25), (4.2, 4.45), (4.4, 4.65),
])
def test_small_holes_get_plus_025_provisionally(target, drawn):
    t = fit.ASA_P1S
    t.reset_log()
    assert t.hole(target) == pytest.approx(drawn, abs=1e-9)
    assert t.log[-1].provisional is True, "小穴の補正は暫定として扱うこと"


def test_boss_gets_plus_025():
    """基準ピン phi10.0 -> 9.75 の実測から."""
    assert fit.ASA_P1S.boss(10.0) == pytest.approx(10.25, abs=1e-9)


@pytest.mark.parametrize("t", [0.8, 1.2, 1.6, 2.0])
def test_walls_are_not_compensated(t):
    """薄板 4 点が誤差ゼロだったので補正不要."""
    assert fit.ASA_P1S.wall(t) == pytest.approx(t, abs=1e-9)


def test_uncovered_diameter_band_is_flagged_as_extrapolated():
    """phi5 〜 phi8 は実測点が無い。黙って埋めずに外挿と記録する."""
    t = fit.ASA_P1S
    t.reset_log()
    t.hole(6.0)
    assert t.log[-1].extrapolated is True


def test_uncompensated_is_recorded_not_silently_passed():
    t = fit.ASA_P1S
    t.reset_log()
    assert t.uncompensated(2.7, "溝幅は未実測") == 2.7
    assert t.log[-1].kind == "uncompensated"
    assert "無補正" in t.log[-1].flags


def test_none_table_is_identity():
    assert fit.NONE.identity is True
    assert fit.NONE.hole(10.1) == 10.1
    assert fit.NONE.boss(10.0) == 10.0


# --- 2 モード評価 -----------------------------------------------------------


def test_target_mode_returns_the_design_intent():
    t = fit.ASA_P1S
    with t.using(fit.MODE_TARGET):
        assert t.hole(10.1) == pytest.approx(10.1, abs=1e-9)
    assert t.hole(10.1) == pytest.approx(10.4, abs=1e-9)


def test_checks_see_the_target_shape_and_stl_sees_the_compensated_one():
    """チェックは狙い形状、STL は補正済み形状。ここが入れ替わると全部が狂う."""
    from harness import geom

    ctx = load_design(COUPON_V2)
    target = {round(c.diameter, 2)
              for c in geom.merge_coaxial(geom.internal_cylinders(ctx.shape))}
    printed = {round(c.diameter, 2)
               for c in geom.merge_coaxial(geom.internal_cylinders(ctx.print_shape))}

    assert {10.1, 10.2, 10.3, 10.4} <= target, target
    assert {10.4, 10.5, 10.6, 10.7} <= printed, printed
    assert 10.1 not in printed, "補正済み形状に狙い寸法の穴が残っている"
    # 穴が広がるぶん、補正済み形状の方が体積が小さい
    assert ctx.print_shape.Volume() < ctx.shape.Volume()


# --- 「全設計がテーブルを通る」という約束 -----------------------------------


@pytest.mark.parametrize("path", DESIGNS, ids=lambda p: p.stem)
def test_every_design_declares_a_fit_table(path):
    ctx = load_design(path)
    assert ctx.fit is not None, (
        f"{path.name} が FIT_TABLE を宣言していない。"
        "意図して補正しない場合も fit.NONE と明示すること"
    )


def test_fit_check_fails_when_no_table_is_declared():
    r = run_all(load_design(UNCLAIMED), only=["fit"])[0]
    assert r.status == FAIL, r.summary
    assert "FIT_TABLE" in r.summary


def test_v1_is_frozen_as_the_as_printed_record():
    """v1 は実測の根拠。補正なしのまま凍結してあること."""
    ctx = load_design(COUPON_V1)
    assert ctx.fit is fit.NONE
    assert ctx.print_shape.Volume() == pytest.approx(ctx.shape.Volume(), abs=1e-6)
    r = run_all(ctx, only=["fit"])[0]
    assert r.status == PASS, r.summary


@pytest.mark.parametrize("path", [COUPON_V2, BEZEL], ids=lambda p: p.stem)
def test_designs_on_the_measured_table_report_their_compensations(path):
    ctx = load_design(path)
    assert ctx.fit is fit.ASA_P1S
    r = run_all(ctx, only=["fit"])[0]
    assert r.status in (PASS, WARN), r.summary
    assert r.measurements["applications"] > 0
    assert r.measurements["table"] == "asa-p1s-0.4mm-2026-08-22"


# --- v2 の折り取りピン ------------------------------------------------------


def test_v2_reference_pin_can_be_broken_off():
    """タブの高さぶんを取り除くと、ピンが台座から分離すること.

    v1 の設計ミス（ピンが台座と一体で軸穴に挿せない）が直っていることの実証。
    """
    import cadquery as cq

    ctx = load_design(COUPON_V2)
    p = ctx.params
    assert len(ctx.shape.Solids()) == 1, "刷る時点では 1 個の部品であること"

    bb = ctx.shape.BoundingBox()
    # タブの高さぶん + 少しを削り取る（ちょうど同じ高さだと 0 厚で繋がったままになる）
    tab_zone = cq.Solid.makeBox(
        bb.xlen + 2, bb.ylen + 2, p["tab_h"] + 0.05,
        cq.Vector(bb.xmin - 1, bb.ymin - 1, bb.zmin - 0.01),
    )
    broken = ctx.shape.cut(tab_zone)
    # 台座 1 + 基準ピン 1 + スライド嵌合のレール 4 = 6
    solids = len(broken.Solids())
    assert solids == 2 + len(p["slide_gaps"]), (
        f"タブを折ったあとのソリッド数が {solids}。"
        "基準ピンとスライドレールが台座から分離していない"
    )


def test_v2_break_off_tab_is_thin_enough_to_snap():
    ctx = load_design(COUPON_V2)
    p = ctx.params
    section = p["tab_w"] * p["tab_h"] * p["tab_count"]
    assert section == pytest.approx(2.4, abs=1e-9)
    assert p["tab_h"] >= 0.8, "クーポンの min_wall_mm 0.8 を下回らないこと"


def test_v2_pin_clears_its_socket_after_compensation():
    """補正後の図面寸法でも、ピンがソケットから抜けること."""
    f = fit.ASA_P1S
    ctx = load_design(COUPON_V2)
    p = ctx.params
    gap = (f.hole(p["pin_socket_dia"]) - f.boss(p["pin_dia"])) / 2
    assert gap > 2.0, f"ソケットとピンの片側すきま {gap} mm"


# --- スライド嵌合の試験（角形状の補正は丸穴と別物） -------------------------


def test_v2_has_slide_fit_coupons_with_four_gaps():
    """丸穴の補正値が角形状に効く保証が無いので、隙間を振った試験を持つこと."""
    ctx = load_design(COUPON_V2)
    gaps = ctx.params["slide_gaps"]
    assert gaps == (0.2, 0.3, 0.4, 0.5)
    names = {f.name for f in ctx.features}
    for g in gaps:
        assert f"slide_{g:.1f}_recv" in names
        assert f"slide_{g:.1f}_rail" in names


def test_v2_slide_rails_are_separate_pieces():
    """レールが受けと一体だと嵌めて確かめられない（v1 の基準ピンと同じ失敗）."""
    import cadquery as cq

    ctx = load_design(COUPON_V2)
    p = ctx.params
    bb = ctx.shape.BoundingBox()
    tab_zone = cq.Solid.makeBox(
        bb.xlen + 2, bb.ylen + 2, p["tab_h"] + 0.05,
        cq.Vector(bb.xmin - 1, bb.ymin - 1, bb.zmin - 0.01),
    )
    assert len(ctx.shape.cut(tab_zone).Solids()) >= 1 + len(p["slide_gaps"])


def test_v2_dovetail_flank_is_printable_without_support():
    """アリのフランクが 45 度以下ならサポートが要らない."""
    import math

    ctx = load_design(COUPON_V2)
    p = ctx.params
    flank = (p["slide_base_w"] - p["slide_top_w"]) / 2
    angle = math.degrees(math.atan(flank / p["slide_depth"]))
    assert angle <= 45.0 + 1e-9, f"フランクが {angle:.1f} 度で立ちすぎ"
