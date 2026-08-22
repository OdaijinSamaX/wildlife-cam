"""parts/ の形状が壊れていないことの確認.

寸法そのものの正しさは実測でしか分からないが、
「メーカー公称値をコードが取り違えていない」ことだけは機械的に守れる。
"""

from __future__ import annotations

import pytest

import parts
from harness import geom
from parts import hcsr501, otg_cable
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


def test_onyx_overall_dimensions_match_the_measurement():
    bb = geom.as_shape(onyx.model()).BoundingBox()
    assert (round(bb.xlen, 2), round(bb.ylen, 2), round(bb.zlen, 2)) == (89.4, 35.8, 13.2)
    assert onyx.OVERALL_L == pytest.approx(onyx.BODY_L + onyx.PLUG_L, abs=1e-9)


def test_onyx_thin_region_matches_the_measurement():
    """後端 20.8 mm だけ厚みが 9.3 に落ちる面取り。脇に他の部品を寄せられる."""
    t0, t1 = onyx.thin_region_x()
    assert (round(t1 - t0, 2), onyx.THIN_H) == (20.8, 9.3)
    shape = geom.as_shape(onyx.model())
    # 薄い区間の中央で切ると、厚みが THIN_H になっている
    mid = (t0 + t1) / 2
    slab = shape.intersect(
        __import__("cadquery").Solid.makeBox(
            2.0, 60.0, 40.0, __import__("cadquery").Vector(mid - 1.0, -30.0, -20.0))
    )
    assert slab.BoundingBox().zlen == pytest.approx(onyx.THIN_H, abs=0.01)


def test_onyx_assembled_length_reconciles_with_the_parts():
    """組立実測 115.0 が 89.4 + 35.0 - 差し込み代 9.4 で辻褄が合うこと."""
    assert onyx.ASSEMBLED_WITH_OTG_L == pytest.approx(
        onyx.OVERALL_L + otg_cable.USB_A_L - onyx.PLUG_ENGAGEMENT, abs=1e-9
    )
    assert onyx.PLUG_ENGAGEMENT < onyx.PLUG_L, "差し込み代がプラグ長を超えている"


def test_onyx_is_a_usb_dongle_not_a_mini_pcie_card():
    assert onyx.DIM_SOURCE.startswith("measured:")
    assert onyx.PART_NUMBER == "SC-QGLC4-C1"
    assert "USB" in onyx.FORM_FACTOR
    assert onyx.total_length() == pytest.approx(89.4, abs=1e-9)


def test_onyx_ports_open_to_the_outside():
    """CRC9 の彫り込みが内部の閉じた空洞になっていないこと."""
    mesh = geom.to_mesh(geom.as_shape(onyx.model()))
    _labels, count, border = geom.air_components(geom.voxelize(mesh, 1.0))
    assert count - len(border) == 0, "閉じた空洞ができている"


def test_onyx_envelope_has_no_antenna_clearance_by_default():
    """外部アンテナは使わないと決まった（2026-08-22）ので既定では逃げを取らない."""
    bb = geom.as_shape(onyx.envelope(0.0)).BoundingBox()
    assert bb.ylen == pytest.approx(onyx.BODY_W, abs=0.01)
    assert bb.xmin == pytest.approx(-onyx.INSERT_TRAVEL, abs=0.01)


def test_onyx_envelope_still_supports_external_antenna_on_request():
    bb = geom.as_shape(onyx.envelope(0.0, external_antenna=True)).BoundingBox()
    reach = onyx.CRC9_PLUG_L + onyx.CABLE_BEND
    assert bb.ymin == pytest.approx(-(onyx.BODY_W / 2 + reach), abs=0.01)
    assert bb.ymax == pytest.approx(onyx.BODY_W / 2 + reach, abs=0.01)


def test_pi_zero_connector_spacing_fits_the_otg_housing():
    """データ口と電源口の間に OTG の micro-USB ハウジングが収まること."""
    from parts import pi_zero_2w

    pos = pi_zero_2w.connector_positions()
    assert pos["usb_data"][1] - pos["mini_hdmi"][0] == pytest.approx(38.8, abs=1e-9)
    assert pos["usb_power"][1] - pos["usb_data"][0] == pytest.approx(20.5, abs=1e-9)
    # ハウジングをデータ口の中心に合わせたとき、電源口の縁まで残るすきま
    half = otg_cable.MICRO_W / 2
    edge = pi_zero_2w.connector_center("usb_data") + half
    assert pos["usb_power"][0] - edge > 1.0


def _longest_dims() -> dict[str, float]:
    out = {}
    for mod in parts.ALL:
        bb = geom.as_shape(mod.model()).BoundingBox()
        out[mod.__name__.split(".")[-1]] = max(bb.xlen, bb.ylen, bb.zlen)
    return out


def test_onyx_is_the_longest_rigid_part_in_the_bom():
    """筐体の内寸を決めるのはこの部品、という前提そのもののテスト.

    OTG ケーブル (150 mm) の方が長いが、可動部があるので折り返せる。
    折り返せない剛体で最長なのが Onyx。
    """
    longest = _longest_dims()
    rigid = {k: v for k, v in longest.items() if k != "otg_cable"}
    assert max(rigid, key=rigid.get) == "soracom_onyx", rigid
    assert rigid["soracom_onyx"] > rigid["pi_zero_2w"]


# --- HC-SR501: 実測値を取り違えていないこと ---------------------------------


def test_hcsr501_uses_measured_dimensions():
    assert hcsr501.DIM_SOURCE.startswith("measured:")
    assert (hcsr501.PCB_L, hcsr501.PCB_W, hcsr501.PCB_T) == (32.8, 24.4, 1.4)
    assert (hcsr501.DOME_DIA, hcsr501.DOME_H, hcsr501.SKIRT_H) == (23.0, 14.4, 3.3)
    assert (hcsr501.HOLE_DIA, hcsr501.HOLE_PITCH) == (2.2, 28.5)


def test_hcsr501_back_component_height_is_the_derived_value():
    """BACK_COMP_H は全高からの導出値。辻褄が合わなくなったら気づけるように."""
    assert hcsr501.BACK_COMP_H == pytest.approx(
        hcsr501.MODULE_H - hcsr501.DOME_H - hcsr501.PCB_T, abs=1e-9
    )
    bb = geom.as_shape(hcsr501.model()).BoundingBox()
    assert bb.zlen == pytest.approx(hcsr501.MODULE_H, abs=0.01)


def test_hcsr501_has_no_sealing_flange():
    """O リングを押し付けるツバが無いこと。pir_bezel の構成判断の前提."""
    assert hcsr501.FLANGE_DIA == hcsr501.DOME_DIA
    assert hcsr501.HAS_SEALING_FLANGE is False


def test_hcsr501_uncertain_dimensions_are_declared():
    """誤差の可能性ありと申告した項目が実在すること."""
    assert set(hcsr501.UNCERTAIN) == {"HOLE_DIA", "HOLE_PITCH"}
    for name in hcsr501.UNCERTAIN:
        assert hasattr(hcsr501, name)


def test_pcb_face_seal_is_impossible():
    """基板を使った面シールが成立しない、という計算そのもののテスト."""
    land = (hcsr501.PCB_W - hcsr501.DOME_DIA) / 2
    assert land == pytest.approx(0.70, abs=1e-9)
    for cord in (2.0, 1.5, 1.0):
        needed = cord * 1.35 + 2 * 1.6      # 溝幅 + 両側の land
        assert needed > land, f"phi{cord} なら成立してしまう"


# --- OTG ケーブル -----------------------------------------------------------


def test_otg_cable_dimensions_are_self_consistent():
    assert otg_cable.DIM_SOURCE.startswith("measured:")
    assert otg_cable.RIGID_TOTAL == pytest.approx(65.8, abs=1e-9)
    assert otg_cable.FLEX_LENGTH == pytest.approx(84.2, abs=1e-9)
    assert otg_cable.RIGID_TOTAL + otg_cable.FLEX_LENGTH == pytest.approx(
        otg_cable.TOTAL_L, abs=1e-9
    )
    bb = geom.as_shape(otg_cable.model()).BoundingBox()
    assert bb.xlen == pytest.approx(150.0, abs=0.01)


def test_serial_chain_exceeds_the_p1s_build_volume():
    """直列に並べると造形枠を超えるので折り返しが必須、という前提のテスト.

    実測が入って内訳が変わった: Pi 65 + micro ハウジング 30.8 + 可動 84.2 +
    Onyx+USB-A の剛体ブロック 115.0 = 295.0。
    """
    from parts import pi_zero_2w

    chain = (pi_zero_2w.PCB_L + otg_cable.MICRO_L + otg_cable.FLEX_LENGTH
             + onyx.ASSEMBLED_WITH_OTG_L)
    assert chain == pytest.approx(295.0, abs=1e-9)
    assert chain > 256.0, "折り返し配置が不要になったなら docs を直すこと"


def test_assembled_rigid_block_is_the_dominant_dimension():
    """箱の中を貫く曲がらない実長は 115.0。単体の 89.4 ではない."""
    assert onyx.ASSEMBLED_WITH_OTG_L == 115.0
    assert onyx.ASSEMBLED_WITH_OTG_L > onyx.OVERALL_L
    assert onyx.ASSEMBLED_WITH_OTG_L < 256.0, "剛体単体で造形枠を超えたら詰み"
