"""レイアウト検討 3 案の共通部品.

**これは最終設計ではなく比較検討用の器である。** 目的は「部品が本当に収まるか」と
「外形が何 mm になるか」を数字で出して案を比べること。したがって:

  - 部品は `parts/` の envelope ではなく **単純な箱のキープアウト**で置く。
    envelope には抜き差し代やアンテナ逃げが入っていて、相手のコネクタを別途
    置くと二重計上になるため。ここでは実寸 + 一律クリアランスで素直に積む。
  - 外殻は単純な直方体シェル。分割線・蓋・ボス・リブは一切入れていない。
    実際にはここから 1 割前後は太る。
  - 柔軟部のケーブルは折れ線で経路を置き、曲げ半径ぶんの円筒で領域を取る。

各案はこのモジュールの `Layout` を組み立てるだけで、チェックとレンダは
ハーネスの通常経路に乗る。部品同士の食い合いは `layout` チェックが見る。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import cadquery as cq

from harness import feature, geom
from harness.component import Component
from parts import cam_module3, hcsr501, otg_cable, pi_zero_2w, soracom_onyx

# --- 部品のキープアウト寸法（実寸。クリアランスは Layout 側で一律に足す） ----
#: (名前, X, Y, Z, 出所)
BOXES = {
    "pi": (pi_zero_2w.PCB_L, pi_zero_2w.PCB_W,
           pi_zero_2w.BOT_COMP_H + pi_zero_2w.PCB_T + pi_zero_2w.TOP_COMP_H),
    "otg_micro": (otg_cable.MICRO_L, otg_cable.MICRO_W, otg_cable.MICRO_H),
    # PIR は筐体壁を貫くので、キャリア（φ52 x 13.3）+ モジュール背面 9.4 を包む箱
    "pir": (52.0, 52.0, hcsr501.PCB_T + hcsr501.BACK_COMP_H + 13.3),
    # レンズ前方に足すのは WINDOW_GAP（窓と前玉が触れないための逃げ）。
    # このカメラに鏡筒は無く焦点は LensPosition で固定するので、調整代は要らない。
    "cam": (cam_module3.PCB_L, cam_module3.PCB_W,
            cam_module3.PCB_T + cam_module3.BACK_COMP_H + cam_module3.LENS_H
            + cam_module3.WINDOW_GAP),
}

#: microSD カードの抜き差しに要る直線の逃げ（カード飛び出し 4.1 + 指の代 推定）
SD_SERVICE_MM = 4.1 + 20.0

# --- 設置対象（現地写真から確定・2026-08-22） -------------------------------
#: 幹の円周 15〜20 cm -> 直径。**桁が違うので平面の背板では線接触にしかならない。**
TRUNK_DIA_MIN = 48.0
TRUNK_DIA_MAX = 64.0
#: ASA の密度。概算質量に使う。
ASA_DENSITY_G_CM3 = 1.07
#: 部品の実測質量（分かっているものだけ）。
PART_MASS_G = {"assy_onyx": 36.0, "assy_onyx_thin": 0.0, "assy_usba": 0.0,
               "pi": 10.0, "otg_micro": 0.0, "otg_flex": 20.0,
               "pir": 8.0, "cam": 4.0}

#: Onyx は内蔵アンテナ 1 本で使うと決まった（外部 CRC9 は使わない）。
#: そのぶん **壁際に置き、金属と他の基板を近づけない**配置ルールが要る。
ANTENNA_MIN_CLEAR_MM = 10.0   # 他の基板との最小離隔（推定。根拠は経験則のみ）
ANTENNA_MAX_WALL_MM = 6.0     # 壁までの距離がこれ以下なら「壁際」とみなす
#: 内蔵アンテナが載っているのは後端側（薄くなっている区間）と仮定する（推定）。
ANTENNA_AT_THIN_END = True


@dataclass
class Box:
    """置いた部品のキープアウト。(名前, 中心, サイズ) で持つ."""

    name: str
    center: tuple[float, float, float]
    size: tuple[float, float, float]
    note: str = ""

    def solid(self, clearance: float = 0.0) -> cq.Shape:
        sx, sy, sz = (s + 2 * clearance for s in self.size)
        cx, cy, cz = self.center
        return cq.Solid.makeBox(sx, sy, sz, cq.Vector(cx - sx / 2, cy - sy / 2, cz - sz / 2))

    @property
    def lo(self):
        return tuple(c - s / 2 for c, s in zip(self.center, self.size))

    @property
    def hi(self):
        return tuple(c + s / 2 for c, s in zip(self.center, self.size))


def cam_window_center(cam_box: "Box", fpc_dir: str) -> tuple[float, float, float]:
    """カメラ窓の中心。**基板中心ではなくレンズ中心に合わせる。**

    実測でレンズは基板中心から FPC が出ている辺の側へ 2.45 mm 寄っている
    （`parts/cam_module3.LENS_OFFSET`）。基板中心に窓を開けると、その 2.45 mm
    ぶん画角が偏る。fpc_dir は FPC が出ていく向き（"+Z" など）。
    """
    i, sign = FACES[fpc_dir]
    c = list(cam_box.center)
    c[i] += sign * cam_module3.LENS_OFFSET
    return tuple(c)


def onyx_assembly(origin: tuple[float, float, float], long_axis: str,
                  width_axis: str) -> list["Box"]:
    """Onyx + OTG の USB-A メスを挿した **剛体ブロック** を箱 3 個で表す.

    実測の組立全長 **115.0 mm** がこの箱の中を貫く曲がらない実長で、
    レイアウトを支配する。内訳（USB-A の自由端を 0 として）:

        0    .. 35.0   OTG の USB-A ハウジング   16.8 x 10.3
        37.5 .. 94.2   Onyx 本体（厚い側）       35.8 x 13.2
        94.2 .. 115.0  Onyx 後端の面取り区間     35.8 x  9.3  <- 脇に物を寄せられる

    origin は USB-A の自由端の中心。long_axis はブロックが伸びる向き
    ("+X" / "-X" / "+Z" など)、width_axis は 35.8 mm を割り当てる軸 ("Y" / "Z")。
    """
    ox = soracom_onyx
    total = ox.ASSEMBLED_WITH_OTG_L
    body_start = total - ox.BODY_L
    thin_start = total - ox.THIN_L
    segs = [
        ("assy_usba", 0.0, otg_cable.USB_A_L, otg_cable.USB_A_W, otg_cable.USB_A_H,
         "OTG の USB-A ハウジング"),
        ("assy_onyx", body_start, thin_start, ox.BODY_W, ox.BODY_H,
         "Onyx 本体（厚い側）"),
        ("assy_onyx_thin", thin_start, total, ox.BODY_W, ox.THIN_H,
         "Onyx 後端の面取り区間。脇に他の部品を寄せられる"),
    ]
    sign = -1.0 if long_axis.startswith("-") else 1.0
    la = {"X": 0, "Y": 1, "Z": 2}[long_axis[-1]]
    wa = {"X": 0, "Y": 1, "Z": 2}[width_axis]
    ta = [a for a in range(3) if a not in (la, wa)][0]

    out = []
    for name, a0, a1, w, h, note in segs:
        center = list(origin)
        center[la] = origin[la] + sign * (a0 + a1) / 2
        size = [0.0, 0.0, 0.0]
        size[la] = a1 - a0
        size[wa] = w
        size[ta] = h
        out.append(Box(name=name, center=tuple(center), size=tuple(size), note=note))
    return out


def box(name: str, at: tuple[float, float, float], axes: str = "xyz",
        note: str = "") -> Box:
    """BOXES の実寸を `axes` の並べ替えで置く。at はキープアウトの中心.

    axes は元の (X, Y, Z) をどの軸に割り当てるかの並び。例: "zyx" なら
    元の X 寸法が Z 方向に来る。
    """
    src = BOXES[name]
    idx = {"x": 0, "y": 1, "z": 2}
    size = [0.0, 0.0, 0.0]
    for src_i, ch in enumerate(axes):
        size[idx[ch]] = src[src_i]
    return Box(name=name, center=at, size=tuple(size), note=note)


# --- 柔軟部の経路 -----------------------------------------------------------


def route_length(points: list[tuple[float, float, float]]) -> float:
    """折れ線の長さ。曲げ半径ぶんの短縮は見ない（保守側 = 長めに出る）."""
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += math.dist(a, b)
    return total


def route_solid(points, radius: float) -> cq.Shape:
    """折れ線に沿った円筒 + 継ぎ目の球。ケーブルが占める領域."""
    solids = []
    for a, b in zip(points, points[1:]):
        v = cq.Vector(*(bi - ai for ai, bi in zip(a, b)))
        if v.Length < 1e-9:
            continue
        solids.append(cq.Solid.makeCylinder(radius, v.Length, cq.Vector(*a), v))
    for p in points[1:-1]:
        solids.append(cq.Solid.makeSphere(radius, cq.Vector(*p), angleDegrees1=-90))
    out = solids[0]
    for s in solids[1:]:
        out = out.fuse(s)
    return out.clean()


def max_bend_deviation(points) -> float:
    """折れ線の最大の折れ角（度）。**0 が真っ直ぐ**で、大きいほど急.

    90 度を超えると折り返しに近く、R15 では渡り切れない。
    """
    worst = 0.0
    for a, b, c in zip(points, points[1:], points[2:]):
        u = [bi - ai for ai, bi in zip(a, b)]
        w = [ci - bi for bi, ci in zip(b, c)]
        nu = math.dist((0, 0, 0), u)
        nw = math.dist((0, 0, 0), w)
        if nu < 1e-9 or nw < 1e-9:
            continue
        cos = sum(x * y for x, y in zip(u, w)) / (nu * nw)
        worst = max(worst, math.degrees(math.acos(max(-1.0, min(1.0, cos)))))
    return worst


def fillet_tangent(dev_deg: float, radius: float) -> float:
    """折れ角 dev を半径 radius で丸めるのに要る接線長 R*tan(dev/2)."""
    return radius * math.tan(math.radians(dev_deg) / 2)


# --- 貫通 -------------------------------------------------------------------


#: 面の名前 -> (軸番号, 符号)
FACES = {"-X": (0, -1), "+X": (0, 1), "-Y": (1, -1), "+Y": (1, 1),
         "-Z": (2, -1), "+Z": (2, 1)}
AXIS_NAME = {0: "X", 1: "Y", 2: "Z"}


@dataclass
class Hole:
    """外殻の 1 面だけを貫く穴.

    面を指定するのが要点。軸だけ指定すると反対側の壁まで抜けて、
    貫通が 2 つに増えてしまう（漏水経路が倍になる）。
    """

    name: str
    face: str                 # "-Y" など
    u: float                  # 面内の第 1 座標
    v: float                  # 面内の第 2 座標
    dia: float
    note: str = ""

    def plane_axes(self) -> tuple[int, int, int]:
        i = FACES[self.face][0]
        others = [a for a in range(3) if a != i]
        return i, others[0], others[1]

    def center(self, lo, hi) -> tuple[float, float, float]:
        i, a, b = self.plane_axes()
        sign = FACES[self.face][1]
        c = [0.0, 0.0, 0.0]
        c[i] = hi[i] if sign > 0 else lo[i]
        c[a] = self.u
        c[b] = self.v
        return tuple(c)


# --- レイアウト -------------------------------------------------------------


@dataclass
class Layout:
    boxes: list[Box]
    holes: list[Hole]
    routes: list[dict] = field(default_factory=list)
    #: 蓋になる面。ここは壁を作らない（本体だけを build する）。
    #: 閉じた箱のまま刷ることはできないので、必ずどこかを開ける。
    open_face: str = "+Y"
    #: 背面に彫る鞍（幹に座る V 溝）。幅 / 深さ / ベルト溝の幅・深さ・位置。
    saddle: bool = True
    saddle_w: float = 44.0
    saddle_d: float = 16.0
    belt_w: float = 30.0      # 何重にも巻ける幅
    belt_extra_d: float = 3.0  # 鞍の面よりさらに深く彫る量
    wall: float = 3.0
    clearance: float = 1.0        # 部品まわりの一律すきま
    inner_margin: float = 2.0     # キープアウトの外側に取る空き

    # --- 内寸・外形 ---
    def cavity(self) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
        c = self.clearance + self.inner_margin
        los = [[b.lo[i] - c for b in self.boxes] for i in range(3)]
        his = [[b.hi[i] + c for b in self.boxes] for i in range(3)]
        for r in self.routes:
            for p in r["points"]:
                for i in range(3):
                    los[i].append(p[i] - r["radius"] - self.inner_margin)
                    his[i].append(p[i] + r["radius"] + self.inner_margin)
        return tuple(min(v) for v in los), tuple(max(v) for v in his)

    def outer(self):
        """外形。鞍を彫るぶんの肉を背面に足す（鞍は奥行きのコスト）."""
        lo, hi = self.cavity()
        olo = [v - self.wall for v in lo]
        ohi = [v + self.wall for v in hi]
        if self.saddle:
            i = FACES[self.open_face][0]
            sign = FACES[self.open_face][1]
            if sign > 0:
                ohi[i] += self.saddle_d
            else:
                olo[i] -= self.saddle_d
        return (tuple(olo), tuple(ohi))

    def outer_size(self) -> tuple[float, float, float]:
        lo, hi = self.outer()
        return tuple(round(h - l, 1) for l, h in zip(lo, hi))

    def outer_volume_cm3(self) -> float:
        sx, sy, sz = self.outer_size()
        return round(sx * sy * sz / 1000.0, 1)

    def interior_point(self) -> tuple[float, float, float]:
        """材料にも部品にも当たらない、空洞の代表点を返す."""
        lo, hi = self.cavity()
        best, best_gap = None, -1.0
        for i in range(9):
            for j in range(9):
                for k in range(9):
                    p = tuple(l + (h - l) * (n + 1) / 10
                              for l, h, n in zip(lo, hi, (i, j, k)))
                    gap = min(
                        max(abs(p[a] - b.center[a]) - b.size[a] / 2 for a in range(3))
                        for b in self.boxes
                    )
                    if gap > best_gap:
                        best, best_gap = p, gap
        return tuple(round(v, 2) for v in best)

    # --- 形状 ---
    def shell(self, table) -> cq.Workplane:
        lo, hi = self.cavity()
        olo, ohi = self.outer()
        outer = cq.Solid.makeBox(*(b - a for a, b in zip(olo, ohi)), cq.Vector(*olo))
        inner = cq.Solid.makeBox(*(b - a for a, b in zip(lo, hi)), cq.Vector(*lo))
        shape = outer.cut(inner)

        # 蓋になる面の壁を落として本体だけにする。閉じた箱は造形できない
        # （必ず天井ができる）ので、比較検討でも本体だけを見る。
        i, sign = FACES[self.open_face]
        cut_lo, cut_hi = list(olo), list(ohi)
        if sign > 0:
            cut_lo[i] = hi[i]
        else:
            cut_hi[i] = lo[i]
        shape = shape.cut(cq.Solid.makeBox(
            *(b - a for a, b in zip(cut_lo, cut_hi)), cq.Vector(*cut_lo)))

        if self.saddle:
            shape = shape.cut(self._saddle_cutter())

        for h in self.holes:
            d = table.hole(h.dia)
            i, _a, _b = h.plane_axes()
            sign = FACES[h.face][1]
            c = list(h.center(lo, hi))
            # その面の壁だけを貫く。外面の 1 mm 外から内面の 1 mm 内まで。
            c[i] = (ohi[i] if sign > 0 else olo[i]) + sign * 1.0
            direction = [0.0, 0.0, 0.0]
            direction[i] = -sign
            shape = shape.cut(
                cq.Solid.makeCylinder(
                    d / 2, self.wall + 2.0, cq.Vector(*c), cq.Vector(*direction)
                )
            )
        return cq.Workplane("XY").newObject([shape])

    def _saddle_cutter(self) -> cq.Shape:
        """背面の V 溝 + ベルト溝。幹の軸は Z 方向（縦）に立つものとする."""
        olo, ohi = self.outer()
        i = FACES[self.open_face][0]
        back = ohi[i] if FACES[self.open_face][1] > 0 else olo[i]
        cx = (olo[0] + ohi[0]) / 2
        zlo, zhi = olo[2], ohi[2]
        depth = self.saddle_d
        half = self.saddle_w / 2

        # V 溝（背面から depth だけ食い込む三角柱。幹の軸 = Z に沿って通す）
        pts = [(cx - half, back), (cx + half, back),
               (cx, back - depth if i == 1 else back)]
        if i != 1:
            raise ValueError("鞍は背面 (+Y/-Y) にしか彫れない")
        v = (
            cq.Workplane("XY")
            .polyline([(x, y) for x, y in pts]).close()
            .extrude(zhi - zlo + 2).translate((0, 0, zlo - 1))
        )
        cutter = geom.as_shape(v)

        # ベルト溝: 上下 2 本。鞍の面よりさらに深く、幅は何重にも巻ける寸法
        span = zhi - zlo
        for frac in (0.25, 0.75):
            zc = zlo + span * frac
            pts2 = [(cx - half, back), (cx + half, back),
                    (cx, back - depth - self.belt_extra_d)]
            belt = (
                cq.Workplane("XY")
                .polyline([(x, y) for x, y in pts2]).close()
                .extrude(self.belt_w).translate((0, 0, zc - self.belt_w / 2))
            )
            cutter = cutter.fuse(geom.as_shape(belt))
        return cutter.clean()

    # --- 取り付けの評価 ---
    def mount_metrics(self, shell_volume_mm3: float | None = None) -> dict:
        """細い幹に付けたときの効きを数字で出す."""
        sx, sy, sz = self.outer_size()
        olo, ohi = self.outer()
        wind = sx * sz                      # 前面投影面積（受風面積）
        overhang = (sx - TRUNK_DIA_MIN) / 2  # 幹の左右への張り出し
        # 重心の代表点: 部品の質量で重み付けした重心
        num = [0.0, 0.0, 0.0]
        den = 0.0
        for b in self.boxes:
            mass = PART_MASS_G.get(b.name, 5.0)
            den += mass
            for k in range(3):
                num[k] += mass * b.center[k]
        cog = [n / den for n in num] if den else [0, 0, 0]
        i = FACES[self.open_face][0]
        back = ohi[i] if FACES[self.open_face][1] > 0 else olo[i]
        # 幹の中心は鞍の底からさらに外側
        trunk_axis = back + TRUNK_DIA_MIN / 2 if FACES[self.open_face][1] > 0 \
            else back - TRUNK_DIA_MIN / 2
        out = {
            "前面投影面積 (cm2)": round(wind / 100.0, 1),
            "幹からの横張り出し 片側 (mm)": round(overhang, 1),
            "鞍の接触長 = 縦の寸法 (mm)": round(sz, 1),
            "受風面積 / 接触長 (mm)": round(wind / sz, 1),
            "重心-幹軸 距離 (mm)": round(abs(cog[i] - trunk_axis), 1),
            "部品質量 合計 (g)": round(den, 1),
        }
        if shell_volume_mm3:
            shell_g = shell_volume_mm3 / 1000.0 * ASA_DENSITY_G_CM3
            out["外殻の概算質量 (g)"] = round(shell_g, 1)
            out["総質量の目安 (g)"] = round(shell_g + den, 1)
            out["転倒モーメントの目安 (g x mm)"] = round(
                (shell_g + den) * out["重心-幹軸 距離 (mm)"], 0)
        return out

    # --- 宣言 ---
    def components(self) -> list[Component]:
        out = []
        for b in self.boxes:
            out.append(Component(
                name=b.name, shape=b.solid(0.0),
                envelope_fn=lambda c, _b=b: _b.solid(c),
                notes=b.note, dimension_source="layout-study",
            ))
        for r in self.routes:
            # 柔軟部のケーブルも実在する部品。レンダに出したいので Component にする。
            solid = route_solid(r["points"], r["radius"])
            out.append(Component(
                name=r["name"], shape=solid,
                envelope_fn=lambda c, _s=solid: _s,
                notes="OTG ケーブル柔軟部（曲げ半径ぶんの太さで置いてある）",
                dimension_source="layout-study",
            ))
        return out

    def features(self, table) -> list[feature.Feature]:
        m = self.clearance
        out = []
        # Onyx + OTG の剛体ブロックは「接するのが正しい」ひと続きなので、
        # 3 個の箱をまとめて 1 つの claim にする（別々だと自分同士で食い合う）。
        assy = [b for b in self.boxes if b.name.startswith("assy_")]
        if assy:
            region = assy[0].solid(m)
            for b in assy[1:]:
                region = region.fuse(b.solid(m))
            out.append(feature.Feature(
                name="part_onyx_assembly", region=region.clean(), margin=m,
                note="Onyx + OTG USB-A の剛体ブロック 115.0 mm",
            ))
        out += [
            feature.Feature(name=f"part_{b.name}", region=b.solid(m), margin=m,
                            note=b.note)
            for b in self.boxes if not b.name.startswith("assy_")
        ]
        for r in self.routes:
            out.append(feature.Feature(
                name=r["name"], region=route_solid(r["points"], r["radius"]),
                margin=0.0, note="OTG ケーブル柔軟部の経路",
            ))
        clo, chi = self.cavity()
        olo, ohi = self.outer()
        for h in self.holes:
            i, a, b = h.plane_axes()
            sign = FACES[h.face][1]
            z0 = (chi[i] if sign > 0 else olo[i]) - 0.5
            z1 = (ohi[i] if sign > 0 else clo[i]) + 0.5
            center2d = (h.u, h.v) if a < b else (h.v, h.u)
            out.append(feature.cylinder(
                f"hole_{h.name}", center2d, table.hole(h.dia),
                min(z0, z1), max(z0, z1), margin=m,
                axis=AXIS_NAME[i], note=h.note,
            ))
        return out

    def expected_openings(self, table) -> list[dict]:
        agg: dict[float, dict] = {}
        for h in self.holes:
            d = h.dia
            row = agg.setdefault(d, {"diameter_mm": d, "count": 0, "note": ""})
            row["count"] += 1
            row["note"] = (row["note"] + " / " + h.note).strip(" /") if row["note"] else h.note
        return list(agg.values())

    def seam_perimeter(self) -> float:
        """蓋の合わせ面の周長。パッキンの長さ = 漏水経路の長さ."""
        i = FACES[self.open_face][0]
        sz = self.outer_size()
        others = [a for a in range(3) if a != i]
        return round(2 * (sz[others[0]] + sz[others[1]]), 1)

    # --- 内蔵アンテナの配置ルール ---
    def antenna_metrics(self) -> dict:
        """Onyx が壁際にあるか、他の基板から離れているか."""
        onyx = [b for b in self.boxes if b.name.startswith("assy_onyx")]
        if not onyx:
            return {}
        target = ([b for b in onyx if b.name.endswith("thin")] or onyx)[0] \
            if ANTENNA_AT_THIN_END else onyx[0]
        olo, ohi = self.outer()
        wall_gap = min(
            min(abs(target.lo[i] - (olo[i] + self.wall)),
                abs((ohi[i] - self.wall) - target.hi[i]))
            for i in range(3)
        )
        boards = [b for b in self.boxes if b.name in ("pi", "cam", "pir")]
        gaps = []
        for b in boards:
            g = max(
                max(target.lo[i] - b.hi[i], b.lo[i] - target.hi[i])
                for i in range(3)
            )
            gaps.append(max(g, 0.0))
        return {
            "アンテナ端-壁 (mm)": round(wall_gap, 1),
            "アンテナ端-他基板 最小 (mm)": round(min(gaps), 1) if gaps else None,
            "アンテナ配置ルール": (
                "OK" if wall_gap <= ANTENNA_MAX_WALL_MM
                and (not gaps or min(gaps) >= ANTENNA_MIN_CLEAR_MM) else "要見直し"
            ),
        }

    # --- 比較用の指標 ---
    def metrics(self) -> dict:
        sx, sy, sz = self.outer_size()
        faces: dict[str, int] = {}
        for h in self.holes:
            faces[h.face] = faces.get(h.face, 0) + 1
        out = {
            "外形 X/Y/Z (mm)": f"{sx} x {sy} x {sz}",
            "外形体積 (cm3)": self.outer_volume_cm3(),
            "貫通の数": len(self.holes),
            "貫通の面": " / ".join(f"{k}:{v}" for k, v in sorted(faces.items())),
            "蓋になる面": self.open_face,
            "合わせ面の周長 (mm)": self.seam_perimeter(),
        }
        out.update(self.antenna_metrics())
        out.update(self.mount_metrics())
        for r in self.routes:
            dev = max_bend_deviation(r["points"])
            out[f"{r['name']} 経路長 (mm)"] = round(route_length(r["points"]), 1)
            out[f"{r['name']} 最大折れ角 (deg, 0=直線)"] = round(dev, 1)
            out[f"{r['name']} R15 に要る接線長 (mm)"] = round(
                fillet_tangent(dev, otg_cable.MIN_BEND_RADIUS), 1)
        return out
