"""カメラ窓に使う既製品 — ドリンク用の透明ドーム蓋.

DIM_SOURCE = "measured:2026-08-22"（ノギス実測）。試作機で実用的な映像が
撮れている実績のある部品で、これを前提に設計する。

| 項目 | 実測 | 備考 |
|---|---|---|
| 口径（縁の径） | 76.0 mm | カップの縁に嵌まる側 |
| 深さ | 32.2 mm | 縁の平面から頂点まで |
| **頂点の平らな窓の直径** | **25.0 mm** | **穴ではなく塞がった平面**。像が歪まない |
| 肉厚 | 0.4 mm | **変更できない**。消耗品として扱う |

## 頂点は「平らな窓」であって穴ではない

光は平面を通るので像が歪まない。**曲面越しに撮るのではない。**
試作機ではドームが外に出る向きで取り付け、カメラはドームの中に入っていた。

## 設計を支配する条件: レンズは頂点の窓から 16.0 mm 以内

対角半角 37.98 度（`parts/cam_module3.half_angle_deg()`）を φ25 の平窓で
確保できる距離は

```
L_max = (25.0 / 2) / tan(37.98 度) = 12.5 / 0.7806 = 16.01 mm
```

**フランジ位置（32.2 mm 奥）ではまったく足りない。** そこでの半角は

```
atan(12.5 / 32.2) = 21.2 度   ->  対角 42.4 度。四隅が大きく欠ける
```

したがって **筐体の前壁から支持構造を前方に伸ばし、カメラを 16 mm 圏内まで
送り出して、その上からドームを被せる**構成になる。防犯カメラと同じ作り。

## 嵌合部（**未実測。実測が来たら差し替える**）

このドーム蓋にはカップの縁に嵌まる溝が元から成形されている。筐体側に
カップの縁と同形状の突起を印刷すれば、ドームが設計どおり嵌合する。
工具なしで着脱でき、傷んだら買って交換できる。

**保持は既製品の嵌合に任せ、防水はその下に敷く O リングが受け持つ**、
という役割分担にする。嵌合部の寸法は下記が未実測（`UNMEASURED` に列挙）。

## 材料と交換周期

肉厚 0.4 mm の PET（と思われる）。**850 nm の近赤外は問題なく透過する**が、
紫外線で白濁して脆化する。交換周期の目安は `docs/window-options.md`。
"""

import math

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "measured:2026-08-22"

RIM_DIA = 76.0        # 実測（口径）
DEPTH = 32.2          # 実測（縁の平面から頂点まで）
WINDOW_DIA = 25.0     # 実測（頂点の平らな窓）
WALL_T = 0.4          # 実測。変更できない

#: 嵌合部の溝形状。**すべて未実測。** 実測が来たらここを埋める。
UNMEASURED = (
    "嵌合溝の内径（カップ縁の外径に相当）",
    "嵌合溝の深さ（半径方向の食い込み量）",
    "嵌合溝の高さ（軸方向の幅）",
    "溝の入口から蓋の縁までの距離",
    "縁の肉厚（溝の外側の壁）",
    "抜け止めビードの有無と、あればその断面寸法",
    "嵌合の締め代（カップ縁との干渉量）",
)

# --- 嵌合部の暫定値（すべて推定。UNMEASURED が埋まったら差し替える） -------
GROOVE_ID = 75.4      # 推定: 印刷側リブの外径
GROOVE_DEPTH = 1.2    # 推定: 半径方向の食い込み
GROOVE_H = 3.0        # 推定: 軸方向の幅
LIP_H = 6.0           # 推定: 縁の立ち上がり高さ


def max_lens_distance(window_dia: float | None = None,
                      half_angle_deg: float | None = None) -> float:
    """平窓 φd で半角 θ を確保できる、レンズから窓までの最大距離."""
    from parts import cam_module3

    d = WINDOW_DIA if window_dia is None else window_dia
    a = cam_module3.half_angle_deg() if half_angle_deg is None else half_angle_deg
    return (d / 2) / math.tan(math.radians(a))


def half_angle_at(distance: float) -> float:
    """レンズが窓から distance のときに得られる対角半角（度）."""
    return math.degrees(math.atan((WINDOW_DIA / 2) / distance))


def model() -> cq.Workplane:
    """縁の平面を z=0、ドームは +z に張り出す（肉厚 0.4 の殻）.

    形は「縁から頂点へ向かう回転体」で近似している。実物の断面は測っていない。
    """
    r_rim = RIM_DIA / 2
    r_win = WINDOW_DIA / 2
    # 縁 -> 頂点を 2 本の直線で近似（下部は立ち上がり、上部は絞り込み）
    pts = [
        (r_rim, 0.0),
        (r_rim, LIP_H),
        (r_win, DEPTH),
        (0.0, DEPTH),
        (0.0, DEPTH - WALL_T),
        (r_win - WALL_T, DEPTH - WALL_T),
        (r_rim - WALL_T, LIP_H),
        (r_rim - WALL_T, 0.0),
    ]
    return (
        cq.Workplane("XZ")
        .polyline(pts)
        .close()
        .revolve(360, (0, 0, 0), (0, 1, 0))
    )


def apex_ring(clearance: float = 0.0) -> cq.Workplane:
    """**頂点の平窓の外側**（= 像として使えない曲面部）を表す円環.

    視野円錐がこの環に当たったら、四隅が曲面越しになる。`fov` チェックに
    COMPONENTS として渡すことで、16 mm 条件を機械が検証できる。
    ドーム本体は透明なので COMPONENTS に入れない（透過は判定できないため）。
    """
    c = clearance
    return (
        cq.Workplane("XY")
        .circle(RIM_DIA / 2)
        .circle(max(WINDOW_DIA / 2 - c, 0.1))
        .extrude(WALL_T + 2 * c)
        .translate((0, 0, DEPTH - WALL_T - c))
    )


def envelope(clearance: float = 0.0) -> cq.Workplane:
    c = clearance
    return (
        cq.Workplane("XY")
        .circle(RIM_DIA / 2 + c)
        .extrude(DEPTH + c)
    )


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Dome lid (drink lid)", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=(
            "口径 76.0 / 深さ 32.2 / 頂点の平窓 φ25.0 / 肉厚 0.4（実測）。"
            "レンズは平窓から 16.0 mm 以内。嵌合溝の寸法は未実測。"
            "PET は紫外線で白濁するので消耗品として扱う。"
        ),
    )


def place_apex_ring(at=(0, 0, 0), rotate=(0, 0, 0)):
    """視野判定用。平窓の外側だけを部品として置く."""
    return make_component(
        "dome apex ring (non-imaging)", apex_ring, apex_ring, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="頂点の平窓 φ25.0 の外側。ここに視野が掛かると四隅が曲面越しになる",
    )
