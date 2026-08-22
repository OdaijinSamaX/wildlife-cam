"""parts/ の形状が壊れていないことの確認.

寸法そのものの正しさは実測でしか分からないが、
「メーカー公称値をコードが取り違えていない」ことだけは機械的に守れる。
"""

from __future__ import annotations

import pytest

import parts
from harness import geom
from parts import soracom_onyx as onyx


@pytest.mark.parametrize("mod", parts.ALL, ids=lambda m: m.__name__.split(".")[-1])
def test_every_part_builds_a_closed_solid(mod):
    shape = geom.as_shape(mod.model())
    assert shape.Volume() > 0
    assert geom.to_mesh(shape).is_watertight


@pytest.mark.parametrize("mod", parts.ALL, ids=lambda m: m.__name__.split(".")[-1])
def test_envelope_contains_the_model(mod):
    """envelope は実体を包んでいること（clearance チェックが成り立つ前提）."""
    model = geom.as_shape(mod.model())
    env = geom.as_shape(mod.envelope(0.5))
    outside = model.cut(env)
    vol = 0.0 if outside is None else float(outside.Volume())
    assert vol < 1e-3, f"{mod.__name__}: 実体が envelope からはみ出している ({vol} mm3)"


@pytest.mark.parametrize("mod", parts.ALL, ids=lambda m: m.__name__.split(".")[-1])
def test_dimension_source_is_declared(mod):
    assert mod.DIM_SOURCE
    assert mod.DIM_SOURCE.startswith(
        ("datasheet", "measured:", "estimated", "standard", "engineering-rule")
    )


# --- SORACOM Onyx: メーカー公称値を取り違えていないこと ---------------------


def test_onyx_overall_dimensions_match_the_datasheet():
    bb = geom.as_shape(onyx.model()).BoundingBox()
    assert (round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)) == (95.0, 36.0, 13.0)


def test_onyx_is_a_usb_dongle_not_a_mini_pcie_card():
    assert onyx.DIM_SOURCE == "datasheet"
    assert onyx.PART_NUMBER == "SC-QGLC4-C1"
    assert "USB" in onyx.FORM_FACTOR
    assert onyx.total_length() == 95.0


def test_onyx_ports_open_to_the_outside():
    """CRC9 の彫り込みが内部の閉じた空洞になっていないこと."""
    mesh = geom.to_mesh(geom.as_shape(onyx.model()))
    _labels, count, border = geom.air_components(geom.voxelize(mesh, 1.0))
    assert count - len(border) == 0, "閉じた空洞ができている"


def test_onyx_envelope_reserves_room_on_both_long_sides():
    """CRC9 がどちらの長辺か未確定なので、envelope は両側に逃げを取る."""
    bb = geom.as_shape(onyx.envelope(0.0)).BoundingBox()
    reach = onyx.CRC9_PLUG_L + onyx.CABLE_BEND
    assert bb.ymin == pytest.approx(-(onyx.BODY_W / 2 + reach), abs=0.01)
    assert bb.ymax == pytest.approx(onyx.BODY_W / 2 + reach, abs=0.01)
    # 抜き差し代
    assert bb.xmin == pytest.approx(-onyx.INSERT_TRAVEL, abs=0.01)


def test_onyx_is_the_longest_part_in_the_bom():
    """筐体の内寸を決めるのはこの部品、という前提そのもののテスト."""
    longest = {}
    for mod in parts.ALL:
        bb = geom.as_shape(mod.model()).BoundingBox()
        longest[mod.__name__.split(".")[-1]] = max(bb.xlen, bb.ylen, bb.zlen)
    winner = max(longest, key=longest.get)
    assert winner == "soracom_onyx", longest
    assert longest["soracom_onyx"] > longest["pi_zero_2w"]
