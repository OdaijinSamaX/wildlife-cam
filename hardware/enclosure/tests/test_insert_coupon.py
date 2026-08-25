"""ヒートセット下穴クーポンのテスト.

**このクーポンの値打ちは「本番の柱と同じ条件で圧入できること」だけにある。**
`camera_unit` 側が動いたのにクーポンが取り残されると、**刷って圧入して合格しても、
その結果が本番に当てはまらない。** しかも見た目には何も起きないので気づけない。
だから **camera_unit の実値と毎回突き合わせる**。
"""

from __future__ import annotations

import importlib
from pathlib import Path

from harness.checks import BAD, run_all
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
COUPON = ROOT / "designs" / "wildlife_cam" / "insert_coupon.py"


def coupon():
    return importlib.import_module("designs.wildlife_cam.insert_coupon")


def unit():
    return importlib.import_module("designs.wildlife_cam.camera_unit")


def test_all_checks_pass():
    bad = [r for r in run_all(load_design(COUPON)) if r.status in BAD]
    assert not bad, [(r.name, r.summary) for r in bad]


def test_post_wall_matches_the_real_lid_posts():
    """**座の肉が `camera_unit` の柱の肉と同じであること.**

    D-024 の争点は下穴径そのものではなく「太った下穴のまわりに肉が残るか」だった。
    肉が本番と違うクーポンで「割れなかった」と言っても、本番の柱が割れない根拠に
    ならない。`camera_unit` が柱を太らせ直したら、ここで落ちて気づける。
    """
    c, p = coupon(), unit().PARAMS
    for boss, pilot, name in ((p["lid_boss_dia"], p["lid_screw_dia"], "M4"),
                              (p["lid_big_boss_dia"], p["lid_big_screw_dia"], "M5")):
        wall = (boss - pilot) / 2
        assert abs(wall - c.POST_WALL) < 1e-9, (
            f"{name} の柱の肉 {wall:.2f} mm に対し、クーポンの座は "
            f"{c.POST_WALL:.2f} mm。**揃えること**（insert_coupon.POST_WALL）")


def test_post_wall_clears_min_wall():
    """肉そのものが `min_wall` を割らないこと（D-024 と同じ不変条件）."""
    c = coupon()
    limit = c.PARAMS["min_wall"]
    assert c.POST_WALL >= limit, (
        f"座の肉 {c.POST_WALL} mm が min_wall {limit} を割る。"
        "**下穴を細くするのではなく座を太らせること**")


def test_pilot_depth_matches_the_real_lid_posts():
    """**下穴の深さが `camera_unit` の `lid_pilot_depth` と同じであること.**

    浅いとインサートが底を突いて、**本番では起きない詰まり方**をする。
    支配するのは長い方の M5（実測 全長 10.0）で、M4（8.0）ではない（D-024）。
    """
    c, p = coupon(), unit().PARAMS
    assert c.PILOT_DEPTH == p["lid_pilot_depth"], (
        f"クーポンの下穴 {c.PILOT_DEPTH} mm に対し camera_unit は "
        f"{p['lid_pilot_depth']} mm")
    assert c.PILOT_DEPTH >= 10.0 + 4.0, "M5 インサート 10.0 + 逃げ 4.0 に足りない"


def test_bands_bracket_the_current_design_values():
    """**帯が `camera_unit` の現行値を挟んでいること.**

    片側にしか振っていないと、答えが帯の外にあったときに**もう一度刷る**ことになる。
    今日の午後で終わらせるための試験なので、そこは機械で押さえる。
    """
    c, p = coupon(), unit().PARAMS
    for band, current, name in ((c.PARAMS["m4_pilots"], p["lid_screw_dia"], "M4"),
                                (c.PARAMS["m5_pilots"], p["lid_big_screw_dia"], "M5")):
        assert current in band, f"{name} の現行値 {current} が帯 {band} に無い"
        assert min(band) < current < max(band), (
            f"{name} の帯 {band} が現行値 {current} を挟んでいない（片側にしか振れていない）")


def test_pilot_holes_do_not_break_through_the_plate():
    """**下穴は止まり穴であること.**

    貫通すると圧入のときに溶けた樹脂が下へ逃げて、**本番（止まり）と条件が変わる。**
    `openings` も貫通を検出するが、ここでは寸法の関係として直接押さえる。
    """
    p = coupon().PARAMS
    floor = p["plate_t"] + p["post_h"] - p["pilot_depth"]
    assert floor >= p["min_wall"], (
        f"下穴の底に残る肉が {floor:.2f} mm しかない（min_wall {p['min_wall']}）。"
        "板を厚くするか座を高くすること")


def test_labels_are_large_enough_for_the_wall_threshold():
    """**刻印は size 10 以上であること.**

    `wall` は刻印の画の間に残る肉も測り、その肉は文字サイズに比例する。
    size 8 では 1 本ごとの最小が 1.316 mm で閾値 1.6 に届かない（実測。
    `_label_shape` の docstring）。**閾値を下げる方向で逃げると、座の肉 1.70 を
    本番と同じ厳しさで見られなくなる。**
    """
    p = coupon().PARAMS
    assert p["label_size"] >= 10.0, f"刻印 {p['label_size']} が小さい"
    assert p["title_size"] >= 10.0, f"表題 {p['title_size']} が小さい"


def test_wall_threshold_is_not_relaxed():
    """**`min_wall_mm` を本番と同じ 1.6 のまま通していること.**

    `fit_coupon` は薄板 0.8 を意図的に含むので 0.8 に緩めてある。**このクーポンは
    緩めない** —— 見たいものが「座の肉が本番と同じ余裕で通ること」だからで、
    緩めた瞬間にこの試験片の主目的が消える。
    """
    c = coupon()
    assert c.CHECK_CONFIG["min_wall_mm"] == unit().CHECK_CONFIG["min_wall_mm"] == 1.6
