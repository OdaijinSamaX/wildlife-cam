"""harness/seal.py の梁モデルそのものの検証.

**モデルが間違っていれば、それを使った判定も全部間違っている。**
だから閉じた式で答えが分かる問題を解かせて突き合わせる。
"""

from __future__ import annotations

import cadquery as cq
import pytest

from harness import seal


class ConstantGasket:
    """潰し量によらず一定の線圧を出すダミー（= 剛体パッキン）.

    これを使うと弾性床が消えて、ただの等分布荷重の梁になるので、
    5wL^4/384EI と突き合わせられる。
    """

    lines = 1
    cord_mm = 2.0
    material = "test"
    shore_a = 0.0
    groove_depth_mm = 1.5
    seated_squeeze_mm = 0.5
    seated_squeeze_frac = 0.25

    def __init__(self, w: float):
        self.w = w

    def load(self, squeeze_mm: float) -> float:
        return self.w

    def stiffness(self, squeeze_mm: float) -> float:
        return 0.0


def uniform_bar(width=20.0, height=22.0, length=200.0):
    """z 方向に伸びる角材。断面は一定なので I が手計算できる."""
    return cq.Solid.makeBox(width, height, length, cq.Vector(-width / 2, 0, 0))


def test_section_props_matches_the_formula():
    """断面二次モーメントを実物から測る部分の検証: b h^3 / 12."""
    bar = uniform_bar()
    area, i = seal.section_props(bar, 100.0)
    assert area == pytest.approx(20.0 * 22.0, rel=1e-3)
    assert i == pytest.approx(20.0 * 22.0 ** 3 / 12.0, rel=2e-3)


def test_simply_supported_udl_matches_closed_form():
    """支点 2 点・等分布荷重・一定断面 -> 5 w L^4 / (384 E I)."""
    w, length = 4.0, 200.0
    bar = uniform_bar(length=length)
    span = seal.SealSpan(
        name="bar", z0=0.0, z1=length, supports=(0.0, length),
        gasket=ConstantGasket(w), end_run_mm=0.0,
        modulus_mpa=2000.0, knockdown=1.0, stations=80)
    r = span.solve(bar)
    ei = 2000.0 * 20.0 * 22.0 ** 3 / 12.0
    assert r.max_lift_mm == pytest.approx(
        5 * w * length ** 4 / (384 * ei), rel=0.01)
    # 支点の反力は左右で半分ずつ
    assert sum(r.support_force_n.values()) == pytest.approx(w * length, rel=0.01)


def test_halving_the_span_cuts_deflection_by_sixteen():
    """L^4 で効くことの確認。**この性質が締結点を増やす根拠**になっている."""
    w, length = 4.0, 200.0
    bar = uniform_bar(length=length)

    def lift(supports):
        return seal.SealSpan(
            name="bar", z0=0.0, z1=length, supports=supports,
            gasket=ConstantGasket(w), end_run_mm=0.0,
            modulus_mpa=2000.0, knockdown=1.0, stations=80).solve(bar).max_lift_mm

    two = lift((0.0, length))
    three = lift((0.0, length / 2, length))
    # 等スパン 2 連梁は 0.0054/0.0130 = 0.415 倍、さらに L^4 で 1/16
    assert three == pytest.approx(two * 0.415 / 16.0, rel=0.05)


def test_oring_load_matches_published_order_of_magnitude():
    """φ2.0 / 70 Shore A / 圧縮率 25% で 1.9 N/mm 前後（Parker のグラフと同じ桁）."""
    w = seal.oring_line_load(0.5, 2.0, 70.0)
    assert 1.5 < w < 2.3
    # 硬度を下げれば必要な力は下がる（材質を変える案の根拠）
    assert seal.oring_line_load(0.5, 2.0, 50.0) < w * 0.6
    # 潰すほど急に硬くなる（線形バネではない）
    assert (seal.oring_line_load(0.6, 2.0, 70.0) / seal.oring_line_load(0.3, 2.0, 70.0)
            > 2.0)


def test_shore_to_modulus_matches_gent():
    assert seal.shore_a_to_young_mpa(70.0) == pytest.approx(5.52, abs=0.05)
    assert seal.shore_a_to_young_mpa(50.0) == pytest.approx(2.46, abs=0.05)


def test_the_gasket_pushes_less_as_the_lid_lifts():
    """弾性床の効き目。剛体パッキンと仮定した粗い上限より必ず小さく出る."""
    from designs.wildlife_cam import camera_unit_lid as lid

    from harness.design import load_design

    ctx = load_design(lid.__file__.replace(".pyc", ".py"))
    span = lid.SEAL_SPANS(ctx.params)[0]
    r = span.solve(ctx.shape)
    gap = max(b - a for a, b in zip(span.supports, span.supports[1:]))
    bound = seal.rigid_gasket_bound(
        span.gasket.load(span.gasket.seated_squeeze_mm), gap, r.ei_min)
    assert 0.0 < r.max_lift_mm < bound
