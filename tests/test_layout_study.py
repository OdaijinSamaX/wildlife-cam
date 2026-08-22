"""レイアウト検討 3 案のテスト.

比較の軸そのものを機械で押さえる。docs/layout-study.md の表と推奨は
ここが通っていることを前提にしている。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from harness.checks import BAD, run_all
from harness.design import load_design
from parts import otg_cable, soracom_onyx

ROOT = Path(__file__).resolve().parent.parent
CASES = ["a", "b", "c"]


def study(letter: str):
    return importlib.import_module(f"designs.wildlife_cam.layout_study_{letter}")


def ctx(letter: str):
    return load_design(ROOT / "designs" / "wildlife_cam" / f"layout_study_{letter}.py")


@pytest.mark.parametrize("letter", CASES)
def test_every_case_passes_all_checks(letter):
    results = run_all(ctx(letter))
    bad = [r for r in results if r.status in BAD]
    assert not bad, [(r.name, r.summary) for r in bad]


@pytest.mark.parametrize("letter", CASES)
def test_cable_route_fits_the_flexible_length(letter):
    """可動長 84.2 mm を超えたら、その案は組み立てられない."""
    m = study(letter).METRICS
    used = m["otg_flex 経路長 (mm)"]
    assert used <= otg_cable.FLEX_LENGTH, f"経路 {used} > 可動長 {otg_cable.FLEX_LENGTH}"


@pytest.mark.parametrize("letter", CASES)
def test_cable_bends_can_be_filleted_at_r15(letter):
    """最大折れ角を R15 で丸めるのに要る接線長が、常識的な範囲に収まること."""
    m = study(letter).METRICS
    assert m["otg_flex 最大折れ角 (deg, 0=直線)"] < 90.0, "折り返しに近い"
    assert m["otg_flex R15 に要る接線長 (mm)"] < 15.0


@pytest.mark.parametrize("letter", CASES)
def test_internal_antenna_placement_rule_is_met(letter):
    """外部アンテナを使わないと決めた以上、壁際 + 他基板から離す は必須."""
    m = study(letter).METRICS
    assert m["アンテナ配置ルール"] == "OK", m


@pytest.mark.parametrize("letter", CASES)
def test_penetration_count(letter):
    """貫通は グランド / PIR / ベント の 3 つ + カメラ窓 1 = 4.

    カメラ窓を 3 つに数えるかは docs/layout-study.md 0.3 節の未決事項。
    """
    assert study(letter).METRICS["貫通の数"] == 4


@pytest.mark.parametrize("letter", CASES)
def test_rigid_block_is_declared_as_one_claim(letter):
    """115.0 mm の剛体ブロックは接するのが正しいので 1 つの claim にまとめる."""
    names = [f.name for f in ctx(letter).features]
    assert "part_onyx_assembly" in names
    assert not [n for n in names if n.startswith("part_assy_")]


@pytest.mark.parametrize("letter", CASES)
def test_layout_is_driven_by_the_assembled_rigid_length(letter):
    """箱の最長辺は 115.0 mm の剛体ブロックより短くなりえない."""
    sizes = [float(v) for v in study(letter).METRICS["外形 X/Y/Z (mm)"].split(" x ")]
    assert max(sizes) >= soracom_onyx.ASSEMBLED_WITH_OTG_L


def test_case_a_is_the_smallest_which_is_why_it_is_recommended():
    """docs/layout-study.md の推奨（案A）の根拠そのもの."""
    vols = {L: study(L).METRICS["外形体積 (cm3)"] for L in CASES}
    assert min(vols, key=vols.get) == "a", vols
    assert vols["a"] < 0.8 * vols["b"]


def test_case_b_has_almost_no_cable_margin():
    """案B を推奨しない最大の理由。余裕が個体差を吸収できない."""
    margin = otg_cable.FLEX_LENGTH - study("b").METRICS["otg_flex 経路長 (mm)"]
    assert margin < 5.0, f"案B の余裕が {margin} mm に増えたなら docs を直すこと"
    assert otg_cable.FLEX_LENGTH - study("a").METRICS["otg_flex 経路長 (mm)"] > 40.0


@pytest.mark.parametrize("letter", CASES)
def test_declared_contacts_are_only_mechanical_connections(letter):
    """接触を宣言してよいのは、機械的に繋がっている組だけ."""
    allowed = {
        frozenset(p) for p in study(letter).CHECK_CONFIG["layout_allow_contact"]
    }
    expected = {
        frozenset(("part_pi", "part_otg_micro")),
        frozenset(("part_otg_micro", "otg_flex")),
        frozenset(("part_onyx_assembly", "otg_flex")),
    }
    assert allowed == expected
