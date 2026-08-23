"""Raspberry Pi Zero 2 W.

外形と取付穴は Raspberry Pi の機構図どおり（65 x 30 mm、取付穴 58 x 23 ピッチ φ2.75、
穴中心は各辺から 3.5 mm）。
実装部品の高さ（上面 3.0 mm / 下面 1.2 mm）は **推定**。ヘッダを立てる場合や
HAT を載せる場合はここでは足りない。
"""

import cadquery as cq

from harness.component import make_component

DIM_SOURCE = "datasheet+measured:2026-08-22"

PCB_L = 65.0          # データシート
PCB_W = 30.0          # データシート
PCB_T = 1.0           # データシート
HOLE_DIA = 2.75       # データシート
HOLE_INSET = 3.5      # データシート（各辺から穴中心まで）
TOP_COMP_H = 8.8      # 実測 2026-08-22（GPIO 40 ピンヘッダのピン先まで）
BOT_COMP_H = 0.4      # 実測 2026-08-22（ほぼ面一。平面にべた置きできる）
CONNECTOR_MARGIN = 6.0  # 推定（USB / HDMI ケーブルの抜き差し代）

#: 裏面がほぼ面一（0.4 mm）なので、スペーサ無しで平面にべた置きできる。
CAN_SIT_FLAT = True

# --- コネクタ（すべて同じ長辺に並ぶ） --------------------------------------
# microSD スロットを上に見て、左の角から mini-HDMI / micro-USB データ /
# micro-USB 電源 の順。外側の縁どうしの実測 2026-08-22:
#     mini-HDMI -> データ  38.8 mm
#     データ    -> 電源    20.5 mm
# コネクタ単体の幅は推定（mini-HDMI 11.0 / micro-USB 8.0）。
# 左角から mini-HDMI までの距離は測っていない（推定 12.0）。
HDMI_W = 11.0             # 推定
USB_W = 8.0               # 推定
HDMI_FROM_LEFT = 12.0     # 推定（要実測）
HDMI_TO_DATA_OUTER = 38.8   # 実測 2026-08-22（外側の縁どうし）
DATA_TO_POWER_OUTER = 20.5  # 実測 2026-08-22（外側の縁どうし）
CONNECTOR_H = 3.0         # 推定（基板面からコネクタ上面まで）

#: microSD カードが基板の縁から飛び出す量
SD_CARD_PROTRUSION = 4.1  # 実測 2026-08-22
SD_CARD_W = 11.0          # 推定（microSD の幅）


def connector_positions() -> dict[str, tuple[float, float]]:
    """コネクタ長辺に沿った (開始, 終了) を、基板の左角からの距離で返す.

    「外側の縁どうし」の実測から逆算している:
        data_end   = hdmi_start + 38.8
        power_end  = data_start + 20.5
    """
    h0 = HDMI_FROM_LEFT
    h1 = h0 + HDMI_W
    d1 = h0 + HDMI_TO_DATA_OUTER
    d0 = d1 - USB_W
    p1 = d0 + DATA_TO_POWER_OUTER
    p0 = p1 - USB_W
    return {"mini_hdmi": (h0, h1), "usb_data": (d0, d1), "usb_power": (p0, p1)}


def connector_center(name: str) -> float:
    a, b = connector_positions()[name]
    return (a + b) / 2

HOLE_PITCH_X = PCB_L - 2 * HOLE_INSET   # 58.0
HOLE_PITCH_Y = PCB_W - 2 * HOLE_INSET   # 23.0


def hole_positions() -> list[tuple[float, float]]:
    """PCB 中心を原点としたときの取付穴中心."""
    return [
        (sx * HOLE_PITCH_X / 2, sy * HOLE_PITCH_Y / 2)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]


def model() -> cq.Workplane:
    """PCB 上面を z=0 とし、部品は +z 側に出る（基板中心が原点）.

    コネクタ長辺は -Y 側（y = -PCB_W/2）とする。`connector_positions()` の
    距離は、その辺に沿って -X 端（左角）から測ったもの。
    """
    pcb = (
        cq.Workplane("XY")
        .box(PCB_L, PCB_W, PCB_T, centered=(True, True, False))
        .translate((0, 0, -PCB_T))
    )
    for x, y in hole_positions():
        pcb = pcb.cut(
            cq.Workplane("XY")
            .circle(HOLE_DIA / 2)
            .extrude(PCB_T + 1)
            .translate((x, y, -PCB_T - 0.5))
        )
    top = cq.Workplane("XY").box(
        PCB_L - 4, PCB_W - 4, TOP_COMP_H, centered=(True, True, False)
    )
    bot = (
        cq.Workplane("XY")
        .box(PCB_L - 4, PCB_W - 4, BOT_COMP_H, centered=(True, True, False))
        .translate((0, 0, -PCB_T - BOT_COMP_H))
    )
    return pcb.union(top).union(bot)


def envelope(clearance: float = 0.0) -> cq.Workplane:
    """外形 + clearance。コネクタ側 (+X) には抜き差し代を足す."""
    c = clearance
    length = PCB_L + 2 * c + CONNECTOR_MARGIN
    return cq.Workplane("XY").box(
        length,
        PCB_W + 2 * c,
        PCB_T + TOP_COMP_H + BOT_COMP_H + 2 * c,
        centered=(True, True, False),
    ).translate((CONNECTOR_MARGIN / 2, 0, -PCB_T - BOT_COMP_H - c))


ENVELOPE = envelope(0.5)


def place(at=(0, 0, 0), rotate=(0, 0, 0)):
    return make_component(
        "Pi Zero 2 W", model, envelope, at=at, rotate=rotate,
        dimension_source=DIM_SOURCE,
        notes="実装部品高さは推定。コネクタ抜き差し代 6 mm を +X に確保",
    )
