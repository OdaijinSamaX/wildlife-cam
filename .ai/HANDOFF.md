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
- `parts/` — 内蔵部品ダミー 9 種
- `designs/wildlife_cam/` — `fit_coupon.py` + 測定手順書、`pir_bezel.py`
- `tests/test_checks_negative.py` — ネガティブテスト 23 件 + `tests/fixtures/`
- `README.md` / `docs/AGENTS.md` / `docs/HARNESS.md`
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
- `pir_bezel`: 総合 WARN（ラジアル O リング溝の片側ひさし 70.6 mm2 / 渡り幅 1 mm 未満）
- `out/<design>/` に STEP / STL / 3MF と PNG 9 枚と `report.md`
- `pytest`: 23 passed（約 2 分 20 秒）

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
- HC-SR501 / EG25-G / IR 投光器の **実測が未実施**。`parts/` の該当モジュールは
  `DIM_SOURCE = "estimated"`。特に `pir_bezel` は HC-SR501 の実測が入るまで
  印刷しないこと。
- スライサ連携（印刷時間・材料量の見積り）は次フェーズ。

## Smallest acceptable fix policy

- チェックの閾値を緩めて PASS にするのは禁止。形を直すか、設計の docstring に
  理由を書いて `CHECK_CONFIG` で明示的に上書きする。
- 新しい失敗を潰したら `tests/test_checks_negative.py` にその失敗を再現する
  ケースを足す。ネガティブテストの無いチェックは未完成とみなす。
- `parts/` の推定寸法を触るときは `DIM_SOURCE` を必ず更新し、その部品を使う
  全設計で `harness check` を回し直す。
