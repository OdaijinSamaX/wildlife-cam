"""基板トレーのテスト.

**このトレーの成否は「本体に入るか」の一点に尽きる。** 蓋の柱 6 点（D-019）が
内部を細かく仕切っているので、寸法を 1 mm 動かすとすぐ当たる。
だから **実際にブーリアンで本体と突き合わせる**テストを主軸に置く。

図面上の寸法を突き合わせるだけのテストは、ここでは意味が薄い
（当たるのは柱の丸みと棚の角なので、bbox の比較では出ない）。
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

    クリック止めの歯のぶん (0.8 mm) 持ち上げた姿勢で、背面 (+Y) から home まで
    滑らせる。途中のどこかで当たるなら、現地では入らない。
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
    assert clash(body_shape, moved) < TOUCH_EPS, "0.8 mm 持ち上げると本体に当たる"


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

    -X 側の縁だけが 2.5 mm 下へ張り出している（本体側も -X の棚だけ低い）。
    逆向きだと張り出しが上の押さえに当たるか、+X の棚に乗り上げて浮く。

    「z 方向にずらせば入ってしまう」ことがないよう、**±6 mm を 0.25 mm 刻みで
    総当たりして、全部当たること**を確かめる。ここが緩むとポカヨケは飾りになる。
    """
    flipped = _flip(tray_shape, rotate)
    for i in range(-24, 25):
        dz = i * 0.25
        moved = flipped.translate(cq.Vector(0, 0, dz))
        if clash(body_shape, moved) < TOUCH_EPS:
            pytest.fail(f"{name}: z を {dz:+.2f} mm ずらすと座ってしまう")


def test_the_key_step_is_what_blocks_the_wrong_orientations():
    """**ポカヨケが効いているのは段違いのおかげ**であることの裏取り（対照実験）.

    受けとトレーの両方から段違いを消して左右対称にすると、**左右反転が座ってしまう。**
    ここが落ちなくなったら、逆向きを止めているのは段違いではない別の何かで、
    その何かを触った瞬間にポカヨケが黙って消える。
    """
    body = load_design(BODY, params_override={"tray_key_step": 0.0}).shape
    flat = load_design(TRAY, params_override={"key_step": 0.0}).shape
    flipped = _flip(flat, (0, 180, 0))
    seated = any(
        clash(body, flipped.translate(cq.Vector(0, 0, i * 0.25))) < TOUCH_EPS
        for i in range(-24, 25))
    assert seated, "段違いを消しても座らない = ポカヨケの根拠が段違いではない"


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


def test_tray_is_narrow_enough_to_pass_the_back_opening():
    """**背面の開口はリムの段のぶん x ±37 しかない。**

    側壁は x ±39 だが、合わせ面の land が 2 mm 内側へ張り出しているので、
    トレーはそこを通れる幅でなければ**そもそも箱に入らない**。
    受けを内側まで伸ばしてあるのはこのため。
    """
    u, t = unit(), tray()
    opening = u.PARAMS["width"] / 2 - u.WALL - u.PARAMS["rim_step"]
    assert opening == pytest.approx(37.0)
    assert t.x_out() <= opening - 0.5, "トレーが背面の開口を通れない"


def test_tray_carries_the_pi_on_its_datasheet_hole_pattern():
    """取付穴は Pi の機構図どおり（58 x 23）で、**Pi の実際の位置から出していること**."""
    u, t = unit(), tray()
    from parts import pi_zero_2w

    assert t.PARAMS["pi_hole_pitch_x"] == pytest.approx(
        pi_zero_2w.PCB_L - 2 * pi_zero_2w.HOLE_INSET)
    assert t.PARAMS["pi_hole_pitch_z"] == pytest.approx(
        pi_zero_2w.PCB_W - 2 * pi_zero_2w.HOLE_INSET)
    xs = {x for x, _z in t.boss_positions()}
    zs = {z for _x, z in t.boss_positions()}
    assert xs == {-29.0, 29.0} and zs == {151.5, 174.5}
    # 4 つとも板の上に載っていること
    for x, z in t.boss_positions():
        assert t.PARAMS["z0"] < z < t.PARAMS["z1"], f"ボス z={z} が板の外"
        assert abs(x) < t.x_out(), f"ボス x={x} が板の外"


def test_tray_geometry_is_derived_from_the_body_not_duplicated():
    """**受けと相手が別々の数字を持ったら、いつか必ずずれる。**"""
    u, t = unit(), tray()
    for k_tray, k_body in (("z0", "tray_z0"), ("z1", "tray_z1"), ("y0", "tray_y0"),
                           ("key_step", "tray_key_step"), ("gap", "tray_gap"),
                           ("detent_h", "detent_h"), ("detent_w", "detent_w")):
        assert t.PARAMS[k_tray] == u.PARAMS[k_body], k_tray
    assert t.key_z0() == pytest.approx(u.tray_shelf_top(u.PARAMS, -1)), \
        "トレーの段違いと本体の棚の段違いがずれている"
    assert t.x_out() == pytest.approx(u.tray_x_out(u.PARAMS))


def test_body_rails_were_replaced_and_the_old_extrude_bug_is_gone():
    """**旧レールは宣言 z 128〜194 に対し実物が z 62〜128 だった**（押し出し方向）.

    作り直した受けは、宣言した z にちゃんといること。
    ここは「宣言と実物がずれない」ことを見るテストなので、
    受けの形を変えたら数字を直すのではなく**実物を測り直すこと**。
    """
    u = unit()
    p = u.PARAMS
    assert not hasattr(u, "_rail"), "旧レールが残っている"
    seat = u._tray_seat(p, u.FIT_TABLE, 1)
    bb = seat.val().BoundingBox() if hasattr(seat, "val") else seat.BoundingBox()
    assert bb.zmin == pytest.approx(p["tray_z0"] - p["tray_seat_t"], abs=0.01)
    assert bb.zmax == pytest.approx(
        p["tray_z1"] + p["tray_lift"] + p["tray_seat_t"], abs=0.01)
    assert bb.ymax == pytest.approx(u.Y_CAVITY_1, abs=0.01)
