# HANDOFF — enclosure-lab Phase A (Claude Code -> Codex)

## Current task

Phase A: 筐体設計ハーネス MVP。CadQuery の設計スクリプトを
`build -> render -> checks -> report` のループに掛ける道具立てと、
最初の設計 2 つ（公差クーポン / PIR ベゼル）。

## Repository and branch

- repo: `/srv/homelab/repos/enclosure-lab` (GitHub `OdaijinSamaX/enclosure-lab`, private)
- branch: `task/harness-mvp` -> PR を立てて停止。main へのマージは人間が行う。

## Files changed

- `harness/` — CLI / 設計ローダ / 形状変換 / エクスポート / レンダ / レポート / チェック 8 種
  （`feature.py` + `checks/layout.py` は「単一ソリッド内のフィーチャの食い合い」用）
- `parts/` — 内蔵部品ダミー 10 種
- `designs/wildlife_cam/` — `fit_coupon.py` + 測定手順書、`pir_bezel.py`
- `tests/test_checks_negative.py` + `tests/test_parts.py` — 66 件 + `tests/fixtures/`
- `README.md` / `docs/AGENTS.md` / `docs/HARNESS.md` / `docs/DECISIONS.md`
- `pyproject.toml` / `.python-version` / `uv.lock`

## Setup commands (clean checkout から)

```bash
cd /srv/homelab/repos/enclosure-lab
uv sync
```

`sudo` も apt も不要。uv が Python 3.12 を取ってくる（システムの 3.14 は触らない）。

## Smoke tests to run first

```bash
uv run python -m harness list
uv run python -m harness check designs/wildlife_cam/fit_coupon.py
uv run python -m harness check designs/wildlife_cam/pir_bezel.py
uv run pytest -q
```

## Expected behavior

- `fit_coupon`: 総合 PASS（120 x 90 x 20 mm）
- `pir_bezel`: 総合 WARN（O リング溝とシーラント溜まりの底が下向き面。どちらもブリッジ可）
- `out/<design>/` に STEP / STL / 3MF と PNG 9 枚と `report.md`
- `pytest`: 66 passed（約 2 分 20 秒）

## Known risks / likely failures

1. **レンダ**: VTK の EGL オフスクリーンに依存している。GPU が見えない環境では
   例外になり、ソフトウェアラスタライザに自動で落ちる（`ENCL_RENDERER=soft` で強制可）。
   落ちたことは `report.md` の「注意」に出る。落ちても数値チェックには影響しない。
2. **起動時の警告**: `bad X server connection. DISPLAY=` が毎回出る。VTK が X を
   試して失敗し EGL に切り替える際のもので、無害。
3. **実行時間**: `check` 1 本が 20〜35 秒（テッセレーション + レイキャスト +
   ボクセル化）。`pytest` は約 2 分。
4. **openings のボクセルピッチ**: 既定 0.5〜0.8 mm。細かくすると重くなる。
   `--pitch` で上書きできる。
5. **`cq.Face.positionAt(0.5, 0.5)` はトリムされた面の外に出ることがある**
   （実測で板の外の z が返った）。円筒面上の代表点が要るときは
   `geom.CylFace.probe_point()` を使う。
6. **`cq.Workplane.revolve` の軸はローカル座標系**。`"XZ"` ワークプレーンで
   グローバル Z 軸まわりに回すには `(0,1,0)` を渡す。ここを間違えると体積 0 の
   板ができる（manifold チェックが検出する）。

## Hardware or credential gaps

- 3D プリンタ（P1S）での **実印刷は未実施**。
- **HC-SR501 は実測済み** (`measured:2026-08-22`)。ただし HOLE_DIA 2.2 と
  HOLE_PITCH 28.5 は誤差の可能性ありと申告されている（この設計は取付穴を
  使っていないので影響しない）。
- **OTG ケーブルは実測済み** (`measured:2026-08-22`)。
- IR 投光器は **実測が未実施** (`DIM_SOURCE = "estimated"`)。
- `parts/soracom_onyx.py` は外形 95x36x13 / 36g がメーカー公称 (`DIM_SOURCE = "datasheet"`)
  だが、**USB プラグ突出量・SIM スロット位置・CRC9 端子位置は推定**で、実測待ち。
  CRC9 がどちらの長辺かも不明なため、envelope は両側に逃げを取る保守的な形にしてある。
- **筐体内で最長の部品は SORACOM Onyx の 95 mm**（Pi Zero 2 W の 65 mm より長い）。
  抜き差し代を含めると 110 mm 前後の直線的な空きが要る。詳細は docs/AGENTS.md。
- スライサ連携（印刷時間・材料量の見積り）は次フェーズ。

## PIR の封止方式（読まずに触らないこと）

`designs/wildlife_cam/pir_bezel.py` は名前こそベゼルだが、中身は
**接着封止キャリア**である。HC-SR501 の実測でドームに **O リングを座らせる
ツバが無い**ことが判明し（FLANGE_DIA == DOME_DIA == 23.0）、旧構成が
不成立になったため作り直した。

- 採用: 案B 接着封止（ボンドライン片側 0.30 mm / 接着代 3.3 mm / 口元に溜まり）
  + フェイス O リング（φ2.0 / 中心径 34.0）
- 不採用: 案A ラジアルシール（軸方向予算がちょうど 0、圧縮率が造形誤差で
  10〜40% に振れる、はみ出し隙間が過大）
- 不成立: 基板を使った面シール（片側 0.70 mm しか残らない）

根拠と数字は `docs/DECISIONS.md` の D-001。**造形姿勢は宣言であり、
内径の軸を造形方向に平行に保つこと**（`tests/test_checks_negative.py` が検証する）。

残リスク: フレネルドームが HDPE 系だとシリコーンは化学的に接着しない。
機械的な保持（溜まり + 狭隙間へのくさび効果）で成立させる設計にしてあるが、
実物で剥離試験をすること。

## 配線レイアウトの制約

Pi Zero 2 W 65 + OTG ケーブル 150 + Onyx 95 = **310 mm** で P1S の枠 256 mm を
超える。**折り返し配置が必須。** 折り返せるのはケーブルの可動部 84.2 mm だけで、
両端のコネクタ 65.8 mm は剛体。詳細は `docs/AGENTS.md` と D-003。

## Smallest acceptable fix policy

- チェックの閾値を緩めて PASS にするのは禁止。形を直すか、設計の docstring に
  理由を書いて `CHECK_CONFIG` で明示的に上書きする。
- 新しい失敗を潰したら `tests/test_checks_negative.py` にその失敗を再現する
  ケースを足す。ネガティブテストの無いチェックは未完成とみなす。
- `parts/` の推定寸法を触るときは `DIM_SOURCE` を必ず更新し、その部品を使う
  全設計で `harness check` を回し直す。
