"""パッキンの面圧が締結点の間で保つかを数値で見るための梁モデル.

**なぜ要るのか。** `wall` チェックは「薄いこと」しか見ない。長い蓋が締結点の間で
たわんで、辺の中央でパッキンが浮くという失敗は、いまあるどのチェックにも掛からない
（`docs/HARNESS.md` の wall の限界に明記してある）。実際 `camera_unit_lid` は
長辺 198 mm を四隅 4 点で押さえており、人間から「中央が浮くのではないか」という
指摘が出た。この module はその指摘に数字で答えるためのもの。

## 何を計算するか

蓋を **z 方向に伸びる 1 本の梁**とみなし、パッキンを **弾性床**（Winkler）として
下から押し上げる。締結点では蓋が本体の land に密着している（変位 0）とする。

```
        締結点                                            締結点
          |                                                 |
  ========o=================================================o========   蓋（梁）
          ^   ^   ^   ^   ^   ^   ^   ^   ^   ^   ^   ^   ^ ^          パッキンの反発
```

  - 断面二次モーメント I(z) は **実際に build() した形状を薄くスライスして測る**。
    設計側に数字を書かせない（AGENTS.md §4.5 と同じ理由。宣言と実物がずれない）。
  - パッキンの反発は線形バネではない。O リングは潰すほど急に硬くなるので、
    Lindley の実験式（下記）をそのまま非線形床として使い、Newton 法で解く。

## 式と出所

**1. ゴムのヤング率（Gent の式。Shore A 硬度から）**

```
E [MPa] = 0.0981 * (56 + 7.62336 S) / (0.137505 * (254 - 2.54 S))
```

  S = 70 -> 5.52 MPa / S = 50 -> 2.46 MPa / S = 40 -> 1.69 MPa

**2. O リングを平板で潰すのに要る線圧（Lindley 1966）**

```
w(eps) = E * d * (1.25 eps^1.5 + 50 eps^6)        [N/mm]
eps = 潰し量 / コード径
```

  φ2.0 コード / 70 Shore A / 圧縮率 25% で **1.86 N/mm**。
  `docs/enclosure-body.md` §4 が当初使っていた「3〜5 N/mm」はこの倍あり、
  出所も書かれていなかった（2026-08-23 に訂正済み）。

**3. 梁**

  2 節点の Hermite 梁要素（せん断変形を無視した Euler-Bernoulli）。
  要素ごとに EI を変える。締結点は変位 0 の拘束、パッキンは節点集中の非線形バネ。

**4. 判定に使う量**

  締結点では蓋が land に当たって止まる（**ハードストップ**）ので、そこでの潰し量は
  「コード径 - 溝深さ」で頭打ちになる。中央が u だけ浮けば、そこの潰し量は
  `s0 - u` に減る。**この s0 - u が静的シールの下限を割ったら漏れる。**

## 仮定（結論はここに強く依存する。docs/lid-fastening.md に一覧がある）

  - 平面保持（Euler-Bernoulli）。幅 84 / スパン 130〜174 なので shear lag が
    あり、**実際の断面はここで測る I よりいくらか効かない**（危険側）。
  - せん断たわみを見ていない。L/h ≈ 6 なので +5〜10% 程度の過小評価（危険側）。
  - 本体側のリムは剛体とみなす。本体の側壁は合わせ面の荷重を**面内**で受ける
    深い板なので、蓋よりはるかに硬い（安全側の仮定として妥当）。
  - **印刷品の実効ヤング率**。中身が疎充填なら実体より柔らかい。`PRINT_KNOCKDOWN`
    を掛けて表す。この係数はスライサ設定に依存し、**実測していない**。
  - クリープを見ていない。ASA は常温でも荷重が続けば流れるので、**時間が経つと
    たわみは増える**。ここで出る数字は「刷った直後」の値。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

#: 実体の ASA の曲げ弾性率（メーカー公称のあたり。実測していない）
ASA_MODULUS_MPA = 2000.0
#: 疎充填で刷ったぶんの割引。4 壁 + 25% 充填の角材を実体と比べたときの目安（推定）。
#: 1.0 は「レール部が実体になる設定で刷る」という意味。
PRINT_KNOCKDOWN = 0.6

#: 静的フェイスシールの圧縮率。下限を割ると漏れる / 上限を超えると永久ひずみ。
MIN_SQUEEZE_FRAC = 0.15
TARGET_SQUEEZE_FRAC = 0.20
MAX_SQUEEZE_FRAC = 0.35


def shore_a_to_young_mpa(shore_a: float) -> float:
    """Gent の式。Shore A 硬度 -> ヤング率 [MPa]."""
    s = float(shore_a)
    return 0.0981 * (56.0 + 7.62336 * s) / (0.137505 * (254.0 - 2.54 * s))


def oring_line_load(squeeze_mm: float, cord_mm: float, shore_a: float) -> float:
    """O リングを平板で squeeze_mm だけ潰すのに要る線圧 [N/mm]（Lindley）."""
    if squeeze_mm <= 0.0:
        return 0.0
    e = shore_a_to_young_mpa(shore_a)
    eps = min(squeeze_mm / cord_mm, 0.6)
    return e * cord_mm * (1.25 * eps ** 1.5 + 50.0 * eps ** 6)


def oring_line_stiffness(squeeze_mm: float, cord_mm: float, shore_a: float) -> float:
    """上の式の接線剛性 dw/ds [N/mm / mm]. Newton 法の Jacobian に使う."""
    if squeeze_mm <= 0.0:
        return 0.0
    e = shore_a_to_young_mpa(shore_a)
    eps = min(squeeze_mm / cord_mm, 0.6)
    return e * (1.875 * math.sqrt(eps) + 300.0 * eps ** 5)


@dataclass(frozen=True)
class Gasket:
    """パッキンの素性。溝は設計側の値をそのまま渡す."""

    cord_mm: float
    groove_depth_mm: float
    shore_a: float
    #: 梁が受け持つパッキンの本数。長辺 2 本を 1 本の梁で受けるなら 2。
    lines: int = 2
    material: str = "silicone"

    @property
    def seated_squeeze_mm(self) -> float:
        """合わせ面が密着したときの潰し量（ハードストップ）."""
        return self.cord_mm - self.groove_depth_mm

    @property
    def seated_squeeze_frac(self) -> float:
        return self.seated_squeeze_mm / self.cord_mm

    def load(self, squeeze_mm: float) -> float:
        """梁が受ける単位長さあたりの反発力 [N/mm]（lines 本ぶん）."""
        return self.lines * oring_line_load(squeeze_mm, self.cord_mm, self.shore_a)

    def stiffness(self, squeeze_mm: float) -> float:
        return self.lines * oring_line_stiffness(squeeze_mm, self.cord_mm, self.shore_a)


# --- 断面二次モーメントを実物から測る -------------------------------------


def section_props(shape, z: float, slab_mm: float = 0.4) -> tuple[float, float]:
    """z における断面の (面積 [mm2], 中立軸まわりの I [mm4]).

    **設計側に数字を書かせない。** 薄い板でブーリアン積を取り、体積特性から出す。
    厚み slab の板の I は `slab * I_area + slab^3/12 * A` なので、
    第 2 項（slab=0.4 なら 0.0053 * A）を引いてから割る。
    曲げ軸は X 軸に平行（= 蓋は z 方向に伸びる梁として y 方向に曲がる）。
    """
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Ax1, gp_Dir, gp_Pnt

    import cadquery as cq

    bb = shape.BoundingBox()
    slab = cq.Solid.makeBox(
        bb.xlen + 2, bb.ylen + 2, slab_mm,
        cq.Vector(bb.xmin - 1, bb.ymin - 1, z - slab_mm / 2))
    cut = shape.intersect(slab)
    props = GProp_GProps()
    BRepGProp.VolumeProperties_s(cut.wrapped, props)
    vol = props.Mass()
    if vol <= 0:
        return 0.0, 0.0
    c = props.CentreOfMass()
    axis = gp_Ax1(gp_Pnt(c.X(), c.Y(), c.Z()), gp_Dir(1, 0, 0))
    i_vol = props.MomentOfInertia(axis)
    area = vol / slab_mm
    i_area = (i_vol - slab_mm ** 3 / 12.0 * area) / slab_mm
    return area, max(i_area, 0.0)


def section_table(shape, z_values) -> list[tuple[float, float, float]]:
    return [(z, *section_props(shape, z)) for z in z_values]


# --- 梁 ---------------------------------------------------------------------


def _element_k(ei: float, le: float) -> np.ndarray:
    l2, l3 = le * le, le ** 3
    return (ei / l3) * np.array([
        [12.0, 6.0 * le, -12.0, 6.0 * le],
        [6.0 * le, 4.0 * l2, -6.0 * le, 2.0 * l2],
        [-12.0, -6.0 * le, 12.0, -6.0 * le],
        [6.0 * le, 2.0 * l2, -6.0 * le, 4.0 * l2],
    ])


@dataclass
class SealResult:
    z: np.ndarray
    lift_mm: np.ndarray
    squeeze_mm: np.ndarray
    squeeze_frac: np.ndarray
    support_force_n: dict[float, float]
    total_seat_force_n: float
    ei_min: float
    ei_max: float
    notes: list[str] = field(default_factory=list)

    @property
    def min_squeeze_frac(self) -> float:
        return float(self.squeeze_frac.min())

    @property
    def worst_z(self) -> float:
        return float(self.z[int(np.argmin(self.squeeze_frac))])

    @property
    def max_lift_mm(self) -> float:
        return float(self.lift_mm.max())

    @property
    def max_squeeze_frac(self) -> float:
        return float(self.squeeze_frac.max())


@dataclass
class SealSpan:
    """1 本の合わせ面（蓋 1 枚）のモデル.

    z0/z1 はパッキンが走る区間、supports は締結点の z、
    end_load_mm は「梁と直交する側（短辺）のパッキンの長さ」で、
    両端に集中荷重として載せる。
    """

    name: str
    z0: float
    z1: float
    supports: tuple[float, ...]
    gasket: Gasket
    #: 短辺のパッキン長さ [mm]。両端の集中荷重に化ける。
    end_run_mm: float = 0.0
    modulus_mpa: float = ASA_MODULUS_MPA
    knockdown: float = PRINT_KNOCKDOWN
    stations: int = 48
    note: str = ""

    @property
    def ei_modulus(self) -> float:
        return self.modulus_mpa * self.knockdown

    def solve(self, shape, sections: list[tuple[float, float, float]] | None = None
              ) -> SealResult:
        z0, z1 = float(self.z0), float(self.z1)
        if len(self.supports) < 2:
            raise ValueError(f"{self.name}: 締結点が 2 点未満では梁を支えられない")
        out = [s for s in self.supports if not (z0 <= s <= z1)]
        if out:
            raise ValueError(
                f"{self.name}: 締結点 {out} がパッキンの区間 {z0}〜{z1} の外にある")
        n_el = int(self.stations)
        nodes = np.linspace(z0, z1, n_el + 1)
        # 締結点を節点に載せる（無いと拘束が掛けられない）
        for s in self.supports:
            nodes[int(np.argmin(np.abs(nodes - s)))] = s
        nodes = np.unique(nodes)
        n = len(nodes)

        if sections is None:
            mids = 0.5 * (nodes[:-1] + nodes[1:])
            sections = section_table(shape, mids)
        i_el = np.array([s[2] for s in sections])
        ei = self.ei_modulus * i_el

        ndof = 2 * n
        k = np.zeros((ndof, ndof))
        for e in range(n - 1):
            le = nodes[e + 1] - nodes[e]
            ke = _element_k(ei[e], le)
            idx = [2 * e, 2 * e + 1, 2 * e + 2, 2 * e + 3]
            k[np.ix_(idx, idx)] += ke

        # 節点の受け持ち長さ（パッキンの分布荷重を集中させる）
        trib = np.zeros(n)
        for e in range(n - 1):
            le = nodes[e + 1] - nodes[e]
            trib[e] += le / 2
            trib[e + 1] += le / 2
        # 短辺のパッキンは両端の集中荷重（潰し量に応じて変わるので長さで持つ）
        # load() は lines 本ぶんを返すので、短辺の実長を lines で割って足す
        end_extra = np.zeros(n)
        end_extra[0] += self.end_run_mm / max(self.gasket.lines, 1)
        end_extra[-1] += self.end_run_mm / max(self.gasket.lines, 1)
        weight = trib + end_extra

        fixed = []
        for s in self.supports:
            fixed.append(2 * int(np.argmin(np.abs(nodes - s))))
        free = np.array([i for i in range(ndof) if i not in set(fixed)])

        s0 = self.gasket.seated_squeeze_mm
        u = np.zeros(ndof)
        for _ in range(60):
            lift = u[0::2]
            sq = np.clip(s0 - lift, 0.0, None)
            fvec = np.zeros(ndof)
            fvec[0::2] = weight * np.array([self.gasket.load(s) for s in sq])
            kt = k.copy()
            tang = weight * np.array([self.gasket.stiffness(s) for s in sq])
            kt[0::2, 0::2] += np.diag(tang)
            r = k @ u - fvec
            du = np.zeros(ndof)
            du[free] = np.linalg.solve(kt[np.ix_(free, free)], -r[free])
            u += du
            if np.max(np.abs(du[0::2])) < 1e-9:
                break
        else:  # pragma: no cover - 収束しないのは入力が壊れているとき
            raise RuntimeError(f"{self.name}: Newton 法が収束しなかった")

        lift = u[0::2]
        sq = np.clip(s0 - lift, 0.0, None)
        fvec = np.zeros(ndof)
        fvec[0::2] = weight * np.array([self.gasket.load(s) for s in sq])
        react = k @ u - fvec
        forces = {float(nodes[i // 2]): float(-react[i]) for i in fixed}
        return SealResult(
            z=nodes, lift_mm=lift, squeeze_mm=sq, squeeze_frac=sq / self.gasket.cord_mm,
            support_force_n=forces,
            total_seat_force_n=float(fvec[0::2].sum()),
            ei_min=float(ei.min()), ei_max=float(ei.max()),
            notes=[self.note] if self.note else [],
        )


def rigid_gasket_bound(w_n_per_mm: float, span_mm: float, ei: float) -> float:
    """比較用の粗い上限: 一定荷重の単純支持梁 5wL^4/384EI [mm].

    パッキンが浮いても線圧が落ちないと仮定するので、必ず実際より大きく出る。
    「桁が合っているか」の確認にだけ使う。
    """
    return 5.0 * w_n_per_mm * span_mm ** 4 / (384.0 * ei)
