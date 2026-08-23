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
    assert len(m.PARAMS["belt_z"]) == 2
    assert m.PARAMS["belt_extra_depth"] == 3.0
    # 支点間はできるだけ広い方が揺れに強い。中央の締結点を避けた結果 114.8 mm。
    z0, z1 = m.PARAMS["belt_z"]
    assert z1 - z0 >= 99.0


def test_belts_do_not_cover_the_thumbscrews_or_the_labels():
    """ベルトの下に来た蝶ねじは現地で回せない。刻印も読めない.

    蓋は幹に巻いたベルトで押さえられているので、**ベルトを外さずに蓋を開ける**。
    座ぐりと刻印がベルト帯に掛かっていないことを機械で押さえる。
    """
    u, m = unit(), lid()
    bands = [(zc - m.PARAMS["belt_w"] / 2, zc + m.PARAMS["belt_w"] / 2)
             for zc in m.PARAMS["belt_z"]]
    for i, (x, z) in enumerate(u.PARAMS["lid_bosses"]):
        head = (m.PARAMS["big_head_dia"] if i == u.PARAMS["lid_big_index"]
                else m.PARAMS["screw_head_dia"])
        lo, hi = z - head / 2, z + head / 2
        for b0, b1 in bands:
            assert hi < b0 or lo > b1, f"締結点 {i+1} (z={z}) がベルト帯 {b0}〜{b1} の下"
        # 刻印はねじと同じ z（側面に彫る）。同じ判定で足りる。
    up_z = m.PARAMS["height"] - 4.0
    for b0, b1 in bands:
        assert not (b0 - 4 < up_z < b1 + 4), "UP の刻印がベルト帯の下"


def test_body_land_carries_the_whole_gasket_groove():
    """**パッキンの帯が本体の合わせ面から外れていないこと。**

    2026-08-23 に実際にあった不具合の再現テスト。背面リムの押し出し量に
    切り抜き用の「+1」が入っていて、**land だけが背面より 1 mm 飛び出し、
    合わせ面の幅が 5 mm から 2 mm に痩せていた。** 蓋の溝 (x 37.65〜40.35) は
    その段差の縁 (x 39) に跨がり、外側半分は 1 mm の空中に浮いていた。
    どのチェックにも掛からない（穴でもソリッド同士の干渉でもないので）。
    """
    import cadquery as cq

    u, m = unit(), lid()
    p = m.PARAMS
    gw = p["gasket_w"]
    zc = p["height"] / 2
    half_z = p["height"] / 2 - p["gasket_z_margin"]
    t = 0.4
    outer = cq.Solid.makeBox(
        2 * p["gasket_x"] + gw, t, 2 * half_z + gw,
        cq.Vector(-(p["gasket_x"] + gw / 2), u.Y_BACK - t, zc - half_z - gw / 2))
    inner = cq.Solid.makeBox(
        2 * p["gasket_x"] - gw, t + 1, 2 * half_z - gw,
        cq.Vector(-(p["gasket_x"] - gw / 2), u.Y_BACK - t - 0.5, zc - half_z + gw / 2))
    band = outer.cut(inner)
    body = load_design(BODY).shape
    assert band.Volume() > 100.0
    assert band.cut(body).Volume() < 1e-3, "パッキンの帯が合わせ面から外れている"
    # 合わせ面は背面と面一（land だけが飛び出していない）
    assert body.BoundingBox().ymax == pytest.approx(u.Y_BACK, abs=1e-3)


def test_lid_fastening_keeps_the_gasket_squeezed():
    """**四隅 4 点では長辺中央でパッキンが浮く**（人間の指摘）ことへの答え.

    seal チェックが梁モデルで出す最小圧縮率が、静的シールの目標 20% 以上あること。
    根拠と比較した案は docs/lid-fastening.md。
    """
    from harness.checks import PASS, run_all

    r = [x for x in run_all(load_design(LID), only=["seal"])][0]
    assert r.status == PASS, r.summary
    assert r.measurements["lid_long_edges: 最小圧縮率 [%]"] >= 20.0
    assert r.measurements["lid_long_edges: 締結点の最大間隔 [mm]"] <= 130.0


def test_support_z_is_derived_from_the_posts_not_duplicated():
    """梁モデルの支点と実際の柱がずれたら、検証は意味を失う."""
    u, m = unit(), lid()
    assert tuple(m.PARAMS["support_z"]) == tuple(sorted({z for _x, z in u.PARAMS["lid_bosses"]}))
    assert len(u.PARAMS["lid_bosses"]) == 6


def test_tightening_order_starts_at_the_middle_pair():
    """刻印の 1..6 は締める順序。**中央から外へ、対角に**が正しい順序.

    フランジと同じで、端から順に締めるとパッキンが片側に寄る。
    """
    order = unit().PARAMS["lid_bosses"]
    mid_z = sorted({z for _x, z in order})[1]
    assert {order[0][1], order[1][1]} == {mid_z}, "1 と 2 は中央の対であること"
    assert order[2][0] * order[3][0] < 0 and order[2][1] != order[3][1], "3-4 は対角"
    assert order[4][0] * order[5][0] < 0 and order[4][1] != order[5][1], "5-6 は対角"


def test_lid_has_a_poka_yoke_screw():
    """1 本だけ径が違う。180 度回すと締まらない."""
    u, l = unit(), lid()
    assert u.PARAMS["lid_big_screw_dia"] > u.PARAMS["lid_screw_dia"]
    assert l.PARAMS["big_screw_dia"] > l.PARAMS["screw_dia"]
    assert 0 <= u.PARAMS["lid_big_index"] < len(u.PARAMS["lid_bosses"])


def test_lid_screw_counterbores_clear_the_gasket_groove():
    """**座ぐりと捕捉ポケットがパッキン溝を破ると、そこが漏れ経路になる。**

    捕捉ポケット（φ9.8 / φ11.8）は座ぐり（φ9.0 / φ10.5）より**大きい**ので、
    ここを見落とすと溝に一番近いのはポケットの方になる。
    """
    u, l = unit(), lid()
    groove_in = l.PARAMS["gasket_x"] - l.PARAMS["gasket_w"] / 2
    for i, (x, _z) in enumerate(u.PARAMS["lid_bosses"]):
        d = l.screw_dims(i)
        widest = max(d["head"], d["pocket"])
        assert abs(x) + widest / 2 <= groove_in - 1.6, \
            f"締結点 {i + 1} の φ{widest} が溝に近すぎる"


def test_thumbscrews_stay_with_the_lid_when_it_comes_off():
    """**蓋を外したとき蝶ねじ 6 本が蓋に付いたまま残ること**（AGENTS.md §4.9 原則 1）.

    屋久島の林床で落としたねじは落ち葉の中で二度と見つからない。
    寸法の連鎖は `captive` チェックが解く。ここでは「6 本ぶん宣言されていること」と
    「本体側の隙間・インサート深さを二重に持っていないこと」を押さえる。
    """
    from harness.checks import PASS, run_all

    u, l = unit(), lid()
    screws = l.CAPTIVE_SCREWS()
    assert len(screws) == len(u.PARAMS["lid_bosses"]) == 6
    assert {s.at for s in screws} == set(u.PARAMS["lid_bosses"])
    # 本体から導出していること（PARAMS に直値を書いていない）
    assert l.PARAMS["post_gap"] == pytest.approx(u.Y_BACK - u.Y_CAVITY_1)
    assert l.PARAMS["insert_depth"] == u.PARAMS["lid_boss_depth"]
    # 下穴はインサートより深いこと（先端が底を突くと面圧が出ない）
    assert u.PARAMS["lid_pilot_depth"] > u.PARAMS["lid_boss_depth"]
    r = run_all(load_design(LID), only=["captive"])[0]
    assert r.status == PASS, (r.summary, r.details)


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
