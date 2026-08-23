"""レンダのテスト.

**内蔵部品が図に出ること**を守る。部品が見えないレンダはレイアウト検討の
目的を果たさないので、ここが落ちたら成果物が壊れている。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from harness import render
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
STUDY = ROOT / "designs" / "wildlife_cam" / "layout_study_a.py"
COUPON = ROOT / "designs" / "wildlife_cam" / "fit_coupon.py"


@pytest.fixture(scope="module")
def study_render(tmp_path_factory):
    out = tmp_path_factory.mktemp("study")
    return load_design(STUDY), render.render_design(load_design(STUDY), out), out


def test_assembly_views_are_produced_when_components_exist(study_render):
    _ctx, result, out = study_render
    names = {p.name for p in result.assembly_files}
    assert names, "COMPONENTS があるのに内蔵部品つきの図が出ていない"
    assert "assy_iso.png" in names
    for p in result.assembly_files:
        assert p.exists() and p.stat().st_size > 1000


def test_components_are_actually_drawn_in_colour(study_render):
    """外殻だけのグレーではなく、部品の色が画素として出ていること."""
    _ctx, result, _out = study_render
    iso = [p for p in result.assembly_files if p.name == "assy_iso.png"][0]
    arr = np.array(Image.open(iso).convert("RGB")).reshape(-1, 3).astype(float)
    # 彩度の高い画素 = 色分けされた部品
    mx, mn = arr.max(axis=1), arr.min(axis=1)
    saturated = ((mx - mn) > 40).mean()
    assert saturated > 0.01, f"色の付いた画素が {saturated:.4f} しかない"


def test_sections_show_component_cross_sections(study_render):
    """断面は防水筐体で中を見る唯一の手段。部品の断面が必ず写ること."""
    _ctx, result, _out = study_render
    assert result.section_files
    for p in result.section_files:
        arr = np.array(Image.open(p).convert("RGB")).reshape(-1, 3).astype(float)
        mx, mn = arr.max(axis=1), arr.min(axis=1)
        assert ((mx - mn) > 40).mean() > 0.005, f"{p.name} に部品の断面が写っていない"


def test_legend_maps_names_to_colours(study_render):
    _ctx, result, _out = study_render
    names = [n for n, _c in result.legend]
    assert {"pi", "cam", "pir", "otg_flex"} <= set(names)
    colours = {c for _n, c in result.legend}
    assert len(colours) == len(result.legend), "同じ色が 2 つの部品に割り当たっている"


def test_designs_without_components_still_render(tmp_path):
    """COMPONENTS が無い設計では内蔵部品つきの図は作らない（作れないので）."""
    ctx = load_design(COUPON)
    result = render.render_design(ctx, tmp_path)
    assert not result.assembly_files
    assert result.files and result.section_files
