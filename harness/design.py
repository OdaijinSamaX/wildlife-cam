"""設計スクリプトの読み込みと、チェックが共有する計算結果のキャッシュ."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import cadquery as cq

from . import fit as fit_mod
from . import geom
from .component import Component, coerce
from .feature import Feature

REPO_ROOT = Path(__file__).resolve().parent.parent

DEFAULT_CHECK_CONFIG: dict[str, Any] = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256.0, 256.0, 256.0),
    "max_overhang_deg": 50.0,
    "component_clearance_mm": 0.4,
    "voxel_pitch_mm": 0.6,
}


@dataclass
class DesignContext:
    name: str
    path: Path
    module: Any
    params: dict
    print_orientation: dict
    check_config: dict
    components: list[Component]
    features: list[Feature]
    #: 狙い形状（印刷後にこうなってほしい形）。全てのチェックとレンダはこれを見る。
    shape: cq.Shape
    raw: Any
    #: 補正済み形状（スライサに渡す形）。STL / 3MF の書き出しだけに使う。
    print_raw: Any = None
    fit: Any = None
    fit_log: list = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    _print_shape: Any = None
    _oriented_print_shape: Any = None
    _mesh: Any = None
    _oriented_shape: Any = None
    _oriented_mesh: Any = None
    _voxels: Any = None
    _named_solids: Any = None

    # --- 設定 ---
    def config(self, key: str, default=None):
        if key in self.check_config:
            return self.check_config[key]
        if key in DEFAULT_CHECK_CONFIG:
            return DEFAULT_CHECK_CONFIG[key]
        return default

    # --- 派生データ（重いので遅延 + キャッシュ） ---
    @property
    def mesh(self):
        if self._mesh is None:
            self._mesh = geom.to_mesh(self.shape)
        return self._mesh

    @property
    def oriented_shape(self) -> cq.Shape:
        if self._oriented_shape is None:
            rot = self.print_orientation.get("rotate", (0, 0, 0))
            self._oriented_shape = geom.drop_to_plate(geom.rotate_shape(self.shape, rot))
        return self._oriented_shape

    @property
    def oriented_mesh(self):
        if self._oriented_mesh is None:
            self._oriented_mesh = geom.to_mesh(self.oriented_shape)
        return self._oriented_mesh

    @property
    def voxels(self):
        if self._voxels is None:
            pitch = float(self.config("voxel_pitch_mm", 0.6))
            self._voxels = geom.voxelize(self.mesh, pitch)
        return self._voxels

    @property
    def print_shape(self) -> cq.Shape:
        """補正済み形状。宣言が無ければ狙い形状をそのまま返す."""
        if self._print_shape is None:
            self._print_shape = (
                self.shape if self.print_raw is None else geom.as_shape(self.print_raw)
            )
        return self._print_shape

    @property
    def oriented_print_shape(self) -> cq.Shape:
        if self._oriented_print_shape is None:
            rot = self.print_orientation.get("rotate", (0, 0, 0))
            self._oriented_print_shape = geom.drop_to_plate(
                geom.rotate_shape(self.print_shape, rot)
            )
        return self._oriented_print_shape

    @property
    def named_solids(self):
        if self._named_solids is None:
            self._named_solids = geom.named_solids(self.raw)
        return self._named_solids

    @property
    def sections(self) -> list[dict]:
        """断面指定。設計側が SECTIONS を持たなければ XZ 中央 / YZ 中央."""
        secs = getattr(self.module, "SECTIONS", None)
        if secs:
            return list(secs)
        c = self.shape.BoundingBox().center
        return [
            {"name": "xz_mid", "origin": (c.x, c.y, c.z), "normal": (0, -1, 0)},
            {"name": "yz_mid", "origin": (c.x, c.y, c.z), "normal": (-1, 0, 0)},
        ]


def load_design(path: str | Path, params_override: dict | None = None) -> DesignContext:
    """設計スクリプトを読み込んで build() を実行する.

    params_override を渡すと PARAMS を上書きして build する（ネガティブテスト用）。
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    mod_name = f"_design_{path.stem}"
    spec = importlib.util.spec_from_file_location(mod_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)

    warnings: list[str] = []
    params = dict(getattr(module, "PARAMS", {}))
    if params_override:
        unknown = set(params_override) - set(params)
        if unknown:
            warnings.append(f"PARAMS に無いキーを上書きしています: {sorted(unknown)}")
        params.update(params_override)

    table = getattr(module, "FIT_TABLE", None)
    if table is not None:
        table.reset_log()

    def _build():
        return module.build(params) if params else module.build()

    if table is None:
        warnings.append(
            "FIT_TABLE が宣言されていません。寸法補正が効いていない設計です "
            "（harness/fit.py と docs/AGENTS.md を参照）"
        )
        raw = _build()
        print_raw = None
        fit_log: list = []
    else:
        # 狙い形状（チェック用）と補正済み形状（造形用）を別々に組む。
        with table.using(fit_mod.MODE_TARGET):
            raw = _build()
        fit_log = list(table.log)
        table.reset_log()
        with table.using(fit_mod.MODE_PRINT):
            print_raw = _build()
        table.reset_log()

    print_orientation = dict(getattr(module, "PRINT_ORIENTATION", {"rotate": (0, 0, 0)}))
    check_config = dict(getattr(module, "CHECK_CONFIG", {}))

    raw_components = getattr(module, "COMPONENTS", [])
    if callable(raw_components):
        raw_components = raw_components(params)
    components = [coerce(c, i) for i, c in enumerate(raw_components)]
    for c in components:
        warnings.extend(f"{c.name}: {w}" for w in c.warnings)

    raw_features = getattr(module, "FEATURES", None)
    if raw_features is None and hasattr(module, "features"):
        if table is None:
            raw_features = module.features(params)
        else:
            with table.using(fit_mod.MODE_TARGET):
                raw_features = module.features(params)
            table.reset_log()
    features = list(raw_features or [])
    bad = [f for f in features if not isinstance(f, Feature)]
    if bad:
        raise TypeError(
            "FEATURES / features() は harness.feature.Feature を返すこと"
            f"（{type(bad[0]).__name__} が混ざっています）"
        )

    shape = geom.as_shape(raw)
    return DesignContext(
        name=getattr(module, "DESIGN_NAME", path.stem),
        path=path,
        module=module,
        params=params,
        print_orientation=print_orientation,
        check_config=check_config,
        components=components,
        features=features,
        shape=shape,
        raw=raw,
        print_raw=print_raw,
        fit=table,
        fit_log=fit_log,
        warnings=warnings,
    )
