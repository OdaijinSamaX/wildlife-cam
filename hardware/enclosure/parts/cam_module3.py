"""Raspberry Pi Camera Module 3 NoIR.

DIM_SOURCE = "measured:2026-08-22"（ノギス実測）。以前の推定値は破棄した。

| 項目 | 値 | 出所 |
|---|---|---|
| PCB_L / PCB_W / PCB_T | 25.0 / 24.0 / 1.0 mm | データシート |
| 取付穴 4 個 | φ2.2 / ピッチ 21.0 x 12.5 mm | データシート |
| LENS_H | **7.6 mm** | 実測。基板の表面からレンズ前面まで |
| LENS_SIZE | **10.7 mm** | 実測。レンズを載せている四角い金属ハウジングの一辺 |
| LENS_OFFSET | **2.45 mm** | 実測からの導出（下記） |
| BACK_COMP_H | **3.0 mm** | 実測。基板裏で最も高いのは CSI コネクタなので CSI_H と同値 |

## LENS_OFFSET 2.45 の導出

レンズ中心から基板の辺までを両側で測った:

```
FPC が出ている辺まで   8.6 mm
反対側の辺まで        13.5 mm
差                     4.9 mm  ->  中心からの寄り = 4.9 / 2 = 2.45 mm
```

8.6 + 13.5 = 22.1 で、基板寸法 24.0 と **1.9 mm 食い違う**。しかし必要なのは
**差**であって和ではない。両端を同じだけ短く測っていても差は変わらないので、
2.45 mm を採用する。（和が合わない原因は未特定。基板の角の面取りか、
ジョウの当て方の系統誤差と思われる。）

**レンズは基板中心ではなく、FPC が出ている辺の側へ 2.45 mm 寄っている。**
窓の位置は基板の中心ではなくレンズの中心に合わせること。

## 訂正 1: ねじ込み式の鏡筒は無い

**このカメラは手で回して焦点を調整できない。** オートフォーカスの駆動部に
レンズが直接載っている構造で、焦点はソフトウェア（`LensPosition`）で固定する運用。

したがって **機械的な調整代を設計に残す必要はない。** 以前 `FOCUS_GAP = 2.0` を
推定で置いていたが、これは誤り。必要なのは「窓とレンズが触れないための光学的な
逃げ」だけなので、`WINDOW_GAP` に名前と根拠を変えた。

窓をレンズのすぐ前まで寄せられるので、**箱が薄くなり内面反射も減る。**
ただし前玉は AF で軸方向にわずかに動くので、接触しない最小限の隙間は残す。

## 訂正 2: 取付穴 4 つは健全

現物で 4 つとも健全であることを確認済み（IR 基板のように欠けてはいない）。
データシート値 21.0 x 12.5 を使ってよく、**ねじで正確に位置決めできるため
画角を設計値で固定できる。**

## 残る推定

  - `WINDOW_GAP = 1.0` — AF の軸方向ストロークを実測していない。前玉が動いても
    窓に触れない最小限として置いた値であって、根拠のある値ではない。
  - FPC が出ている辺を -Y と定義している（`FPC_EDGE`）。実装時の向きは設計側で決める。
  - **CSI コネクタの幅・奥行き・位置（`CSI_W` / `CSI_D` / `CSI_Y`）は推定。**
    高さ 3.0 だけが実測。取付ボスと干渉するかどうかがここで決まるので、
    実測が入ったら `window_snoot` の `boss_dia` を見直すこと。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "measured:2026-08-22"

PCB_L = 25.0        # データシート
PCB_W = 24.0        # データシート
PCB_T = 1.0         # データシート
HOLE_DIA = 2.2      # データシート
HOLE_PITCH_X = 21.0  # データシート（現物で 4 穴とも健全であることを確認済み）
HOLE_PITCH_Y = 12.5  # データシート

LENS_SIZE = 10.7    # 実測 2026-08-22（レンズを載せる四角い金属ハウジングの一辺）
LENS_H = 7.6        # 実測 2026-08-22（基板表面からレンズ前面まで）
LENS_OFFSET = 2.45  # 実測からの導出（(13.5 - 8.6) / 2）。docstring 参照
CSI_H = 3.0         # 実測 2026-08-22（基板裏の CSI コネクタ高さ）
BACK_COMP_H = CSI_H  # 基板裏で最も高いのが CSI コネクタなので同値
CSI_W = 14.0        # 推定（要実測）: CSI コネクタの幅
CSI_D = 5.5         # 推定（要実測）: CSI コネクタの奥行き
CSI_Y = -7.0        # 推定（要実測）: FPC が出る辺 (-Y) 寄りの位置
#: 取付ボスが入る柱の直径。envelope からはこの柱を抜く（意図した接触なので）。
MOUNT_COLUMN_DIA = 6.2
#: envelope が実体を完全には包まないことを宣言する。取付穴の柱を抜いてあるため、
#: 基板の一部（穴の周囲）が envelope の外に出る。**意図した接触**である。
ENVELOPE_INTENTIONAL_CONTACT = True

#: FPC が出ている辺。レンズはこちら側へ LENS_OFFSET だけ寄っている。
FPC_EDGE = "-Y"

#: 窓とレンズ前玉が触れないための逃げ。**機械的な焦点調整代ではない**
#: （このカメラに鏡筒は無く、焦点は LensPosition で固定する）。
#: AF の軸方向ストロークが未実測なので 1.0 mm は推定。
WINDOW_GAP = 1.0

#: 焦点はソフトウェアで固定する。機械的な調整代は不要。
FOCUS_IS_SOFTWARE_FIXED = True

# --- 光学諸元（**要検証**。根拠は docs/window-options.md） -------------------
# 出所はメーカーの公表値とされる数字で、実機で測ってはいない。
# 変えられるようにパラメータ化してある。ここが違えば窓と筒の形も変わる。
FOCAL_LENGTH_MM = 4.74   # 要検証
SENSOR_DIAG_MM = 7.4     # 要検証（約 7.4）
HFOV_DEG = 66.0          # 要検証（約 66 度）
VFOV_DEG = 41.0          # 要検証（約 41 度）
DFOV_DEG = 75.0          # 要検証（約 75 度）


def half_angle_deg(focal: float | None = None, diag: float | None = None) -> float:
    """対角の半画角。焦点距離とセンサ対角から導出する.

    atan((7.4 / 2) / 4.74) = 37.98 度 -> 対角 75.96 度。
    公表値の「約 75 度」（半角 37.5）とほぼ一致するので、両者に矛盾は無い。
    判定には導出値を使う（公表値より 0.5 度広い = 安全側）。
    """
    import math

    f = FOCAL_LENGTH_MM if focal is None else focal
    d = SENSOR_DIAG_MM if diag is None else diag
    return math.degrees(math.atan((d / 2) / f))


def max_straight_tube_length(inner_radius: float) -> float:
    """内半径 r の**真っ直ぐな筒**が視野を遮らない最大長 L = r / tan(半角).

    半角 37.98 度なら L < 1.281 r。**細長い筒は成立しない。**
    """
    import math

    return inner_radius / math.tan(math.radians(half_angle_deg()))


def hole_positions() -> list[tuple[float, float]]:
    return [
        (sx * HOLE_PITCH_X / 2, sy * HOLE_PITCH_Y / 2)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def lens_center() -> tuple[float, float]:
    """基板中心を原点としたときのレンズ中心。FPC 側 (-Y) へ 2.45 寄る."""
    return (0.0, -LENS_OFFSET)


def model() -> cq.Workplane:
    """PCB 前面（レンズ側）を z=0 とし、レンズは +z に出る。FPC は -Y 側."""
    pcb = (
        cq.Workplane("XY")
        .box(PCB_L, PCB_W, PCB_T, centered=(True, True, False))
        .translate((0, 0, -PCB_T))
    )
    for x, y in hole_positions():
        pcb = pcb.cut(
            cq.Workplane("XY").circle(HOLE_DIA / 2).extrude(PCB_T + 1)
            .translate((x, y, -PCB_T - 0.5))
        )
    lx, ly = lens_center()
    lens = (
        cq.Workplane("XY")
        .box(LENS_SIZE, LENS_SIZE, LENS_H, centered=(True, True, False))
        .translate((lx, ly, 0))
    )
    # 裏面で最も高いのは CSI コネクタだけ。板全面を塞いでいるわけではないので、
    # コネクタぶんの箱だけ置く（取付ボスを立てる余地を残すため）。
    back = (
        cq.Workplane("XY")
        .box(CSI_W, CSI_D, BACK_COMP_H, centered=(True, True, False))
        .translate((0, CSI_Y, -PCB_T - BACK_COMP_H))
    )
    return pcb.union(lens).union(back)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """外形 + clearance。レンズ前方は WINDOW_GAP だけ空ける（調整代ではない）."""
    c = clearance
    h = PCB_T + BACK_COMP_H + LENS_H + WINDOW_GAP + 2 * c
    env = cq.Workplane("XY").box(
        PCB_L + 2 * c, PCB_W + 2 * c, h, centered=(True, True, False)
    ).translate((0, 0, -PCB_T - BACK_COMP_H - c))
    # 取付穴の柱は「意図した接触」なので keep-out から抜く。
    # 抜かないと、正しく立てたボスが clearance FAIL になる。
    for x, y in hole_positions():
        env = env.cut(
            cq.Workplane("XY").circle(MOUNT_COLUMN_DIA / 2).extrude(h + 2)
            .translate((x, y, -PCB_T - BACK_COMP_H - c - 1))
        )
    return env


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Camera Module 3 NoIR", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes=(
            "実測 2026-08-22。レンズは基板中心から FPC 側へ 2.45 mm 寄っているので、"
            "窓は基板中心ではなくレンズ中心に合わせること。"
            "鏡筒が無く焦点は LensPosition で固定するため、機械的な調整代は不要。"
            "窓との逃げ 1.0 mm は AF ストローク未実測のための推定。"
        ),
    )
