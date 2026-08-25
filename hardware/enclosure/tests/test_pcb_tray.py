"""基板トレーのテスト.

**このトレーの成否は「本体に入るか」の一点に尽きる。** CSI レスキューを付けた Pi は
microSD 込みで 76.9 mm あり、**x の隙間は全部 0.4 mm しかない**（D-022 / D-023）。
蓋の柱 6 点（D-019）も内部を細かく仕切っている。
だから **実際にブーリアンで本体と突き合わせる**テストを主軸に置く。

図面上の寸法を突き合わせるだけのテストは、ここでは意味が薄い
（当たるのは柱の丸みと棚の角なので、bbox の比較では出ない）。
**ただし x の収支だけは数字でも押さえる**（`test_tray_and_the_rescue_pi_both_pass_...`）。
"""

from __future__ import annotations

import importlib
from pathlib import Path

import cadquery as cq
import pytest

from harness import geom
from harness.checks import BAD, run_all
from harness.design import load_design

ROOT = Path(__file__).resolve().parent.parent
BODY = ROOT / "designs" / "wildlife_cam" / "camera_unit.py"
TRAY = ROOT / "designs" / "wildlife_cam" / "pcb_tray.py"

#: 接触は許す（棚に載るのが正しい）。当たり判定はこの体積で見る。
TOUCH_EPS = 1e-3


def unit():
    return importlib.import_module("designs.wildlife_cam.camera_unit")


def tray():
    return importlib.import_module("designs.wildlife_cam.pcb_tray")


@pytest.fixture(scope="module")
def body_shape():
    return load_design(BODY).shape


@pytest.fixture(scope="module")
def tray_shape():
    return load_design(TRAY).shape


def clash(body, shape) -> float:
    return body.intersect(shape).Volume()


def test_all_checks_pass():
    bad = [r for r in run_all(load_design(TRAY)) if r.status in BAD]
    assert not bad, [(r.name, r.summary) for r in bad]


def test_tray_seats_in_the_body_without_biting_anything(body_shape, tray_shape):
    """**home の位置で本体と食い合わないこと。** 棚に載る接触は体積 0 なので許される."""
    assert tray_shape.Volume() > 1000.0, "トレーが空"
    assert clash(body_shape, tray_shape) < TOUCH_EPS


def test_tray_can_be_pushed_in_from_the_back(body_shape, tray_shape):
    """**差し込みの経路が通っていること。**

    クリック止めの歯のぶん持ち上げた姿勢で、背面 (+Y) から home まで滑らせる。
    途中のどこかで当たるなら、現地では入らない。
    """
    lift = unit().PARAMS["detent_h"]
    for dy in [i * 0.5 for i in range(0, 37)]:      # +18 mm から home まで
        moved = tray_shape.translate(cq.Vector(0, dy, lift))
        assert clash(body_shape, moved) < TOUCH_EPS, f"y +{dy} mm で当たる"


def test_the_detent_actually_blocks_the_tray_from_backing_out(body_shape, tray_shape):
    """**クリック止めが本当に効いていること。**

    home のまま（持ち上げずに）背面へ引くと、歯が切り欠きの壁に当たって出られない。
    持ち上げれば出られることは `test_tray_can_be_pushed_in_from_the_back` が見ている。

    **この 2 つが揃って初めて「クリック止め」である。** 片方だけなら、
    ただの隙間か、ただの嵌め殺しでしかない。
    """
    for dy in (0.5, 1.0, 2.0):
        moved = tray_shape.translate(cq.Vector(0, dy, 0))
        v = clash(body_shape, moved)
        assert v > TOUCH_EPS, f"持ち上げずに +Y へ {dy} mm 動いてしまう（抜け止めが効いていない）"


def test_tray_has_room_to_be_lifted_off_the_detent(body_shape, tray_shape):
    """**歯を乗り越えるだけの遊びがあること。** 無ければ現地で引き出せない."""
    u = unit().PARAMS
    assert u["tray_lift"] > u["detent_h"], "遊びが歯より小さい"
    moved = tray_shape.translate(cq.Vector(0, 0, u["detent_h"]))
    assert clash(body_shape, moved) < TOUCH_EPS, "歯のぶん持ち上げると本体に当たる"


# --- ポカヨケ（原則 3）: 逆向きでは物理的に座らない ------------------------


def _flip(shape, rotate):
    bb = shape.BoundingBox()
    c = cq.Vector(0.0, (bb.ymin + bb.ymax) / 2, (bb.zmin + bb.zmax) / 2)
    return geom.rotate_shape(shape.translate(c * -1), rotate).translate(c)


@pytest.mark.parametrize("name,rotate", [
    ("左右反転 (Y 軸まわり)", (0, 180, 0)),
    ("前後反転 (Z 軸まわり)", (0, 0, 180)),
    ("上下反転 (X 軸まわり)", (180, 0, 0)),
])
def test_wrong_orientations_cannot_be_seated(body_shape, tray_shape, name, rotate):
    """**向きを間違えたトレーは、どの高さに置いても本体に当たること。**

    縁の上端は +X 側だけ高く（段 0.8 mm）、本体の「天井から吊ったフック」も同じ段。
    逆向きだと高い側の縁が低い側のフックに当たる。トレーは棚に載っていて
    **下へ逃げられない**ので、どの高さでも座らない。取っ手も上下系の反転を止める。

    「z 方向にずらせば入ってしまう」ことがないよう、**±6 mm を 0.25 mm 刻みで
    総当たりして、全部当たること**を確かめる。ここが緩むとポカヨケは飾りになる。
    """
    flipped = _flip(tray_shape, rotate)
    for i in range(-24, 25):
        dz = i * 0.25
        moved = flipped.translate(cq.Vector(0, 0, dz))
        if clash(body_shape, moved) < TOUCH_EPS:
            pytest.fail(f"{name}: z を {dz:+.2f} mm ずらすと座ってしまう")


def test_the_key_step_is_what_blocks_the_front_back_flip():
    """**ポカヨケが効いているのは段違いのおかげ**であることの裏取り（対照実験）.

    受けとトレーの両方から段違い（フックの段）を消すと、**前後反転（Z 軸まわり）が
    座ってしまう。** ここが落ちなくなったら、その反転を止めているのは段違いでは
    ない別の何かで、それを触った瞬間にポカヨケが黙って消える。

    **上下反転と「左右+上下」反転は、段違いが無くても取っ手が止める**
    （取っ手は板の上端にしかないので、z を反転すると下端へ来て棚に当たる）。
    つまりこの 2 つは**二重に**止まっている。段違いが単独で効いているのは
    前後反転だけなので、対照実験はそこに当てる。
    """
    body = load_design(BODY, params_override={"tray_key_step": 0.0}).shape
    flat = load_design(TRAY, params_override={"key_step": 0.0}).shape
    flipped = _flip(flat, (0, 0, 180))
    seated = any(
        clash(body, flipped.translate(cq.Vector(0, 0, i * 0.25))) < TOUCH_EPS
        for i in range(-24, 25))
    assert seated, "段違いを消しても座らない = ポカヨケの根拠が段違いではない"


def test_the_grip_blocks_the_two_flips_that_the_key_step_does_not():
    """**取っ手が「上下」と「左右+上下」の反転を単独で止めている**ことの裏取り.

    上の対照実験と対になる。段違いを消しても、この 2 つは取っ手で止まる。
    """
    body = load_design(BODY, params_override={"tray_key_step": 0.0}).shape
    flat = load_design(TRAY, params_override={"key_step": 0.0}).shape
    for name, rot in (("上下反転", (180, 0, 0)), ("左右+上下反転", (0, 180, 0))):
        flipped = _flip(flat, rot)
        for i in range(-24, 25):
            moved = flipped.translate(cq.Vector(0, 0, i * 0.25))
            if clash(body, moved) < TOUCH_EPS:
                pytest.fail(f"{name}: 段違い抜きでも座ってしまう（z {i * 0.25:+.2f}）")


# --- 蓋の柱を避けていること -------------------------------------------------


def test_tray_stays_clear_of_the_lid_posts(body_shape, tray_shape):
    """**蓋の柱 2 対（z=142 / 186）を避けていること**（指示のハードな条件）.

    柱は y 3〜44 の全域を塞ぐので、逃げる方向は z しかない。
    図面の数字を突き合わせるのではなく、**柱の占める空間（+ クリアランス）を
    実際に箱で作り、トレーと交差する体積を測る。**
    持ち上げた状態（クリック解除）でも当たらないことまで見る。
    """
    u = unit()
    p = u.PARAMS
    c = 0.5
    for i, (x, z) in enumerate(p["lid_bosses"]):
        d = p["lid_big_boss_dia"] if i == p["lid_big_index"] else p["lid_boss_dia"]
        keepout = cq.Solid.makeCylinder(
            d / 2 + c, u.Y_CAVITY_1 - u.Y_CAVITY_0 + 2,
            cq.Vector(x, u.Y_CAVITY_0 - 1, z), cq.Vector(0, 1, 0))
        for lift in (0.0, p["tray_lift"]):
            v = keepout.intersect(tray_shape.translate(cq.Vector(0, 0, lift))).Volume()
            assert v < TOUCH_EPS, f"柱 {i + 1} (x={x}, z={z}) と {lift} mm 持ち上げ時に干渉 {v:.2f}"


def test_tray_and_the_rescue_pi_both_pass_the_back_opening():
    """**x の収支。ここが本設計でいちばん張り詰めている。**

    CSI レスキューを付けた Pi は **microSD 込みで剛体幅 76.9 mm** ある
    （4.1 + 65.0 + 7.8。すべて実測）。これが背面の開口を通らなければ、
    トレーは箱から出せない = 現地で保守できない。

    幅を 84 -> 88 に広げ、rim_step を 2.0 -> 1.75 に薄くして開口を
    74.0 -> 78.5 にしたのが D-022。**余裕は片側 0.4 mm しかない。**
    """
    from parts import pi_zero_2w_rescue as rescue

    u, t = unit(), tray()
    opening = u.back_opening_x(u.PARAMS)
    assert opening == pytest.approx(39.25), "開口が動いた。x の収支をやり直すこと"
    assert rescue.rigid_width() == pytest.approx(76.9)

    # トレーの板が通る
    assert t.x_out() <= opening - 0.4, "トレーが背面の開口を通れない"
    # Pi + microSD が通る（**板より外へ出ていないこと**も併せて見る）
    pi_half = rescue.rigid_width() / 2
    assert pi_half <= opening - 0.4, "レスキューを付けた Pi が背面の開口を通れない"
    assert pi_half <= t.x_out(), "Pi がトレーの板からはみ出している"


def test_the_rescue_pi_is_centred_on_the_opening_not_on_the_board():
    """**microSD が -X に 4.1 mm 出ているので、基板の中心は箱の中心ではない。**

    剛体（カード + 基板 + ブラケット）の中心を開口の中心に合わせる。
    ここを基板中心で合わせると、カード側が 2 mm 外へはみ出して通らなくなる。
    """
    from parts import pi_zero_2w_rescue as rescue

    u = unit()
    lo = u.PI_BOARD_X0 - rescue.SD_CARD_PROTRUSION
    hi = u.PI_BOARD_X0 + rescue.RESCUE_OVERALL_X
    assert lo == pytest.approx(-hi), "剛体の中心が開口の中心からずれている"
    assert u.PI_BOARD_CX == pytest.approx(-1.85, abs=0.01)


def test_the_tray_only_uses_the_two_holes_the_bracket_left_free():
    """**ブラケットが CSI 側の取付穴 2 個をねじ + ナットで占有している。**

    だからトレーが留められるのは microSD 側の 2 本だけ。ここが 4 本に戻っていたら、
    **共締めできるという誤った前提が復活している**（ねじの裏はナットで塞がっている）。
    """
    from parts import pi_zero_2w_rescue as rescue

    t = tray()
    assert len(rescue.free_hole_positions()) == 2
    assert len(rescue.nut_positions()) == 2
    assert all(x < 0 for x, _y in rescue.free_hole_positions()), "microSD 側であること"

    screws, pads = t.screw_positions(), t.nut_pad_positions()
    assert len(screws) == 2 and len(pads) == 2
    # ねじとナットのピッチは Pi の機構図どおり（58 x 23）
    from parts import pi_zero_2w
    assert abs(screws[0][0] - pads[0][0]) == pytest.approx(
        pi_zero_2w.PCB_L - 2 * pi_zero_2w.HOLE_INSET)
    assert abs(screws[0][1] - screws[1][1]) == pytest.approx(
        pi_zero_2w.PCB_W - 2 * pi_zero_2w.HOLE_INSET)
    # 4 か所とも板の上に載っていること
    for x, z in screws + pads:
        assert t.PARAMS["z0"] < z < t.PARAMS["z1"], f"座面 z={z} が板の外"
        assert abs(x) < t.x_out(), f"座面 x={x} が板の外"


def test_tray_geometry_is_derived_from_the_body_not_duplicated():
    """**受けと相手が別々の数字を持ったら、いつか必ずずれる。**"""
    u, t = unit(), tray()
    for k_tray, k_body in (("z0", "tray_z0"), ("z1", "tray_z1"), ("y0", "tray_y0"),
                           ("key_step", "tray_key_step"), ("gap", "tray_gap"),
                           ("seat_x", "tray_seat_x"),
                           ("detent_h", "detent_h"), ("detent_w", "detent_w")):
        assert t.PARAMS[k_tray] == u.PARAMS[k_body], k_tray
    for sign in (-1, 1):
        assert t.edge_top(sign=sign) == pytest.approx(
            u.tray_hook_bottom(u.PARAMS, sign) - u.PARAMS["tray_lift"]), \
            "トレーの縁の段と本体のフックの段がずれている"
    assert t.x_out() == pytest.approx(u.tray_x_out(u.PARAMS))
    assert t.PARAMS["boss_h"] == pytest.approx(u.PI_BOSS_H)


def test_the_receiver_really_sits_where_it_is_declared():
    """**宣言と実物がずれる失敗**を止める（旧レールは宣言 z 128〜194 に対し実物が
    z 62〜128 だった。押し出し方向の取り違え）.

    受けの形を変えたら数字を直すのではなく**実物を測り直すこと**。
    """
    u = unit()
    p = u.PARAMS
    assert not hasattr(u, "_rail"), "旧レールが残っている"
    assert not hasattr(u, "_tray_seat"), "旧 C チャンネルが残っている"
    seat = u._tray_receiver(p, u.FIT_TABLE)
    bb = seat.val().BoundingBox() if hasattr(seat, "val") else seat.BoundingBox()
    assert bb.zmin == pytest.approx(p["tray_z0"] - p["tray_ledge_t"], abs=0.01)
    assert bb.zmax == pytest.approx(p["height"] - u.WALL, abs=0.01), \
        "フックが天井まで届いていない（吊れていない）"
    assert bb.ymax == pytest.approx(u.Y_CAVITY_1, abs=0.01)
    assert bb.xmax == pytest.approx(p["width"] / 2 - u.WALL, abs=0.01)


def test_the_receiver_clears_the_lid_posts():
    """**受けと蓋の柱 6 本が食い合っていないこと。**

    棚は柱の影のすぐ上（z 147.0）にあり、フックは柱の間（|x| <= 25）にある。
    どちらも 1 mm 動かすと当たるので、図面の数字ではなく**実際に交差を測る**。
    """
    u = unit()
    p = u.PARAMS
    seat = u._tray_receiver(p, u.FIT_TABLE)
    seat = seat.val() if hasattr(seat, "val") else seat
    for i, (x, z) in enumerate(p["lid_bosses"]):
        d = p["lid_big_boss_dia"] if i == p["lid_big_index"] else p["lid_boss_dia"]
        post = cq.Solid.makeCylinder(
            d / 2, u.Y_CAVITY_1 - u.Y_CAVITY_0 + 2,
            cq.Vector(x, u.Y_CAVITY_0 - 1, z), cq.Vector(0, 1, 0))
        v = post.intersect(seat).Volume()
        assert v < TOUCH_EPS, f"柱 {i + 1} (x={x}, z={z}) と受けが干渉 {v:.2f} mm3"
