"""カメラユニット本体と蓋のテスト.

指示で与えられた**ハードな制約**を機械で押さえる。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from harness.checks import BAD, run_all
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "designs" / "wildlife_cam" / "camera_unit.py"
LID = ROOT / "designs" / "wildlife_cam" / "camera_unit_lid.py"


def unit():
    return importlib.import_module("designs.wildlife_cam.camera_unit")


def lid():
    return importlib.import_module("designs.wildlife_cam.camera_unit_lid")


@pytest.mark.parametrize("path", [BODY, LID], ids=lambda p: p.stem)
def test_all_checks_pass(path):
    bad = [r for r in run_all(load_design(path)) if r.status in BAD]
    assert not bad, [(r.name, r.summary) for r in bad]


@pytest.mark.parametrize("path", [BODY, LID], ids=lambda p: p.stem)
def test_print_height_is_under_the_hard_limit(path):
    """**造形時の Z が 229 を超えないこと**（指示の最優先制約）."""
    ctx = load_design(path)
    z = ctx.oriented_print_shape.BoundingBox().zlen
    assert z <= 229.0, f"造形 Z が {z:.1f} mm"
    # 開口を上にして刷るので、造形 Z は箱の奥行きになる
    assert z < 60.0, f"造形 Z が {z:.1f} mm。姿勢が想定と違う"


def test_design_height_was_reduced_from_the_layout_study():
    """余裕は安全のためにある。案D の 229 から減らしたこと."""
    assert unit().PARAMS["height"] == 198.0
    assert unit().PARAMS["height"] < 229.0


def test_overhang_from_trunk_is_reported_and_bounded():
    """幅を増やしたぶんの張り出しを数値で押さえる."""
    m = unit()
    assert m.PARAMS["width"] == 84.0
    assert m.overhang_from_trunk_mm(trunk_dia=48.0) == pytest.approx(18.0)
    # 案D 検討時は 14.5。ドームの口径で決まる下限なので、これ以上増やさない
    assert m.overhang_from_trunk_mm(trunk_dia=48.0) <= 18.0


def test_lens_stays_within_16mm_of_the_dome_window():
    """ドームの平窓から 16.0 mm 以内。ポッド側の fov が別途検証している."""
    from parts import dome_lid

    assert unit().lens_to_dome_window_mm() <= dome_lid.max_lens_distance()


def test_body_is_one_solid():
    """浮いた柱やリブがあると造形できない."""
    assert len(load_design(BODY).shape.Solids()) == 1


def test_body_has_exactly_four_penetrations():
    """貫通は漏水の第一原因。増えたら気づけるようにする."""
    decl = unit().CHECK_CONFIG["expected_openings"]
    assert sum(d["count"] for d in decl) == 4


def test_saddle_seats_the_measured_trunk_range():
    """幹 φ48〜64 が V 溝の壁の中で 2 線接触になること."""
    m = lid()
    assert m.PARAMS["saddle_half_angle_deg"] == 54.0
    half = m.saddle_half_width(m.PARAMS["saddle_depth"])
    assert half == pytest.approx(22.0, abs=0.1)
    for dia in (48.0, 64.0):
        h = m.trunk_center_height(dia)
        # 中心が V の頂点より上にあり、幹の最下点も頂点に届かない
        assert h > dia / 2, f"φ{dia} が V の底に当たっている"


def test_belt_grooves_are_wide_enough_to_wrap_several_times():
    m = lid()
    assert m.PARAMS["belt_w"] >= 30.0
    assert len(m.PARAMS["belt_frac"]) == 2
    assert m.PARAMS["belt_extra_depth"] == 3.0


def test_lid_has_a_poka_yoke_screw():
    """1 本だけ径が違う。180 度回すと締まらない."""
    u, l = unit(), lid()
    assert u.PARAMS["lid_big_screw_dia"] > u.PARAMS["lid_screw_dia"]
    assert l.PARAMS["big_screw_dia"] > l.PARAMS["screw_dia"]
    assert 0 <= u.PARAMS["lid_big_index"] < len(u.PARAMS["lid_bosses"])


def test_lid_screw_counterbores_clear_the_gasket_groove():
    """座ぐりがパッキン溝を破ると、そこが漏れ経路になる."""
    u, l = unit(), lid()
    groove_in = l.PARAMS["gasket_x"] - l.PARAMS["gasket_w"] / 2
    for i, (x, _z) in enumerate(u.PARAMS["lid_bosses"]):
        head = (l.PARAMS["big_head_dia"] if i == u.PARAMS["lid_big_index"]
                else l.PARAMS["screw_head_dia"])
        assert abs(x) + head / 2 <= groove_in - 1.6, f"柱 {i} が溝に近すぎる"


def test_slide_axis_is_declared_and_horizontal_when_printed():
    """摺動面の積層段差が摺動方向と平行になる姿勢であること."""
    import numpy as np

    from harness import geom

    m = unit()
    ctx = load_design(BODY)
    axis = np.array(m.SLIDE_AXIS, dtype=float)
    probe = geom.rotate_shape(
        __import__("cadquery").Solid.makeCylinder(1.0, 10.0),
        ctx.print_orientation["rotate"])
    bb = probe.BoundingBox()
    # 設計 Z が造形時に水平に寝ていること（造形 Z にならない）
    assert bb.zlen == pytest.approx(2.0, abs=0.01), "摺動方向が造形方向と平行"
    assert tuple(axis) == (0.0, 0.0, 1.0)
