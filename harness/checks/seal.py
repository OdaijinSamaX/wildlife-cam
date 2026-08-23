"""10. seal — 締結点の間でパッキンの潰し量が保つか.

**なぜ要るのか。** `wall` は「薄いこと」しか見ず、**長い蓋が締結点の間でたわんで
辺の中央でパッキンが浮く**という失敗にはどのチェックも掛からなかった
（`docs/HARNESS.md` の wall の限界に明記してある通り）。この失敗は水が入るまで
外から見えない。屋外筐体では致命的なので、専用のチェックを立てた。

設計が `SEAL_SPANS`（`harness.seal.SealSpan` のリスト、または params を取る関数）を
宣言すると、

  1. **実際に build() した形状**を薄くスライスして断面二次モーメント I(z) を測り、
  2. パッキンを非線形の弾性床とした梁として解き、
  3. 合わせ面に沿った**潰し量の最小値**を出す。

判定は静的フェイスシールの圧縮率で行う。

| 圧縮率 | 判定 |
|---|---|
| 15% 未満 | **FAIL**（静的シールとして成立しない） |
| 15 〜 20% | WARN（成立はするが余裕が無い） |
| 20 〜 35% | PASS |
| 35% 超 | WARN（圧縮永久ひずみが出る）|

式・仮定・出所は `harness/seal.py` の docstring と `docs/lid-fastening.md`。
"""

from __future__ import annotations

from .. import seal as seal_mod
from . import FAIL, PASS, SKIP, WARN, CheckResult, register


@register("seal")
def check(ctx) -> CheckResult:
    spans = getattr(ctx.module, "SEAL_SPANS", None)
    if callable(spans):
        spans = spans(ctx.params)
    spans = list(spans or [])
    if not spans:
        return CheckResult(
            "seal", SKIP,
            "SEAL_SPANS が未宣言。**合わせ面が無いのか、効かないと判断したのかは "
            "この結果からは分からない**（docs/AGENTS.md §6: 締結点の間隔が 60 mm 以下の"
            "小さいフランジは対象外だが、その判断を docstring に書くこと）",
            {"spans": 0}, limits=LIMITS,
        )

    floor = float(ctx.config("seal_min_squeeze_frac", seal_mod.MIN_SQUEEZE_FRAC))
    target = float(ctx.config("seal_target_squeeze_frac", seal_mod.TARGET_SQUEEZE_FRAC))
    ceiling = float(ctx.config("seal_max_squeeze_frac", seal_mod.MAX_SQUEEZE_FRAC))

    rows = []
    details = []
    worst = 1.0
    worst_name = ""
    over = False
    m: dict = {}
    for sp in spans:
        r = sp.solve(ctx.shape)
        gap = max((b - a) for a, b in zip(sp.supports, sp.supports[1:])) \
            if len(sp.supports) > 1 else float(sp.z1 - sp.z0)
        per_screw = max(r.support_force_n.values()) / max(sp.gasket.lines, 1)
        status = ("FAIL" if r.min_squeeze_frac < floor
                  else "WARN" if r.min_squeeze_frac < target else "PASS")
        if r.max_squeeze_frac > ceiling:
            over = True
        if r.min_squeeze_frac < worst:
            worst, worst_name = r.min_squeeze_frac, sp.name
        rows.append({
            "span": sp.name,
            "supports": len(sp.supports),
            "max_gap_mm": round(gap, 1),
            "seated_%": round(sp.gasket.seated_squeeze_frac * 100, 1),
            "max_lift_mm": round(r.max_lift_mm, 3),
            "min_squeeze_%": round(r.min_squeeze_frac * 100, 1),
            "at_z": round(r.worst_z, 1),
            "seat_force_N": round(r.total_seat_force_n),
            "per_screw_N": round(per_screw),
            "verdict": status,
        })
        m[f"{sp.name}: 最小圧縮率 [%]"] = round(r.min_squeeze_frac * 100, 2)
        m[f"{sp.name}: 最大浮き [mm]"] = round(r.max_lift_mm, 4)
        m[f"{sp.name}: 締結点の最大間隔 [mm]"] = round(gap, 1)
        m[f"{sp.name}: 合計座面力 [N]"] = round(r.total_seat_force_n)
        m[f"{sp.name}: ねじ 1 本あたり [N]"] = round(per_screw)
        m[f"{sp.name}: EI [N mm2]"] = f"{r.ei_min:.3g} 〜 {r.ei_max:.3g}"
        details.append(
            f"{sp.name}: E {sp.modulus_mpa:.0f} MPa x 実効係数 {sp.knockdown:.2f}"
            f" / {sp.gasket.material} {sp.gasket.shore_a:.0f} Shore A"
            f"（ゴムの E = {seal_mod.shore_a_to_young_mpa(sp.gasket.shore_a):.2f} MPa）"
            f" / コード φ{sp.gasket.cord_mm} 溝深さ {sp.gasket.groove_depth_mm}"
            f" -> 密着時の潰し量 {sp.gasket.seated_squeeze_mm:.2f} mm"
        )
        if sp.note:
            details.append(f"{sp.name}: {sp.note}")

    m["閾値: 下限 [%]"] = round(floor * 100, 1)
    m["閾値: 目標 [%]"] = round(target * 100, 1)
    m["閾値: 上限 [%]"] = round(ceiling * 100, 1)
    cols = ["span", "supports", "max_gap_mm", "seated_%", "max_lift_mm",
            "min_squeeze_%", "at_z", "seat_force_N", "per_screw_N", "verdict"]

    if worst < floor:
        return CheckResult(
            "seal", FAIL,
            f"{worst_name} の最小圧縮率 {worst*100:.1f}% が下限 {floor*100:.0f}% を割る"
            "（締結点の間でパッキンが浮く）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    if worst < target:
        return CheckResult(
            "seal", WARN,
            f"{worst_name} の最小圧縮率 {worst*100:.1f}% は下限 {floor*100:.0f}% を"
            f"上回るが目標 {target*100:.0f}% に届かない（クリープの余裕が無い）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    if over:
        return CheckResult(
            "seal", WARN,
            f"最小圧縮率は {worst*100:.1f}% で足りるが、"
            f"上限 {ceiling*100:.0f}% を超える箇所がある（圧縮永久ひずみ）",
            m, details=details, table=rows, table_columns=cols, limits=LIMITS)
    return CheckResult(
        "seal", PASS,
        f"合わせ面 {len(spans)} 本すべてで圧縮率 {worst*100:.1f}% 以上を保つ",
        m, details=details, table=rows, table_columns=cols, limits=LIMITS)


LIMITS = (
    "見逃すもの: **反りと平面度**。198 mm の ASA を刷ったときの合わせ面の反りは "
    "ここで計算する弾性変形（0.1 mm 前後）より大きくなりうる。**実機で定盤に当てて測ること。** "
    "**クリープと圧縮永久ひずみ**も見ていない。ここで出るのは「刷った直後・締めた直後」の値で、"
    "月単位では蓋も O リングも流れて潰し量は減る。"
    "梁は Euler-Bernoulli で、せん断たわみと shear lag（幅 84 に対しスパンが短いので効く）を"
    "無視している。どちらも**実際のたわみを大きくする側**なので、実効弾性率の係数で"
    "まとめて割り引いている（その係数自体が推定）。"
    "本体側のリムは剛体としている（合わせ面の荷重を面内で受ける深い壁なので妥当）。"
    "O リングの反発力は Lindley の一般式で、**その品番の実測ではない**。"
    "締結点では蓋が land に密着している（ねじの力が足りている）と仮定しており、"
    "ねじが緩む・インサートが抜ける側の失敗は見ていない。"
    "梁は 1 方向にしか曲げない。短辺側（幅方向）のたわみは別途考えること。"
)
