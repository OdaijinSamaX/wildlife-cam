# enclosure-lab

屋外 IoT の防水筐体を **AI が設計して 3D プリントする** ための作業台。

AI が CAD を扱うときの本質的な弱点は「目が無い」ことにある。だからこのリポジトリの
本体は CadQuery のラッパではなく、**書いた形を自動で見て・測って・数字で突き返す
ループ**である。

```
設計スクリプト (CadQuery)
   -> build   : STEP / STL / 3MF
   -> render  : 6 面 + iso + 断面 PNG（人と AI が目で見る用）
   -> checks  : 肉厚・密閉・干渉・サイズ枠・オーバーハング・開口を数値で判定
   -> report  : out/<design>/report.md に画像と数値と PASS/FAIL
```

最初の利用先は wildlife-cam（Pi Zero 2 W のトレイルカメラ）。プリンタは
**Bambu Lab P1S**（密閉筐体・ASA 可）、造形枠 256 x 256 x 256 mm。

## 1 行で試す

```bash
uv run python -m harness check designs/wildlife_cam/fit_coupon.py
```

`out/fit_coupon/` に STEP / STL / 3MF と PNG 9 枚と `report.md` が出る。

```bash
uv run python -m harness check designs/wildlife_cam/pir_bezel.py
uv run python -m harness list                 # 設計とチェックの一覧
uv run pytest                                 # ネガティブテスト（下記）
```

主なオプション:

| オプション | 意味 |
|---|---|
| `--only wall,openings` | 一部のチェックだけ走らせる |
| `--no-render` | PNG を作らない（速い） |
| `--no-export` | STEP/STL/3MF を作らない |
| `--pitch 0.4` | openings のボクセルピッチを上書き |
| `--out DIR` | 出力先を変える |

終了コードは総合判定が FAIL のとき 1、それ以外 0。CI に直接掛けられる。

## 環境構築

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh   # uv が無ければ
uv sync                                            # .venv を作って依存を入れる
```

`sudo` も apt も要らない。すべて PyPI の wheel で完結する。

### なぜ Python 3.12 なのか

母艦のシステム Python は 3.14 だが、**CadQuery / OCP には 3.14 用の wheel が無い**。
`.python-version` で 3.12 に固定し、`uv` がプロジェクト専用の Python を持ってくる。
システム Python には一切触らない。実績のある組み合わせは:

| | バージョン | 備考 |
|---|---|---|
| Python | 3.12.13 | uv が管理。3.14 では OCP が入らない |
| cadquery | 2.8.0 | |
| cadquery-ocp | 7.9.3.1.1 | OCCT 7.9 |
| vtk | 9.6.2 | レンダに使う |
| trimesh | 5.0.0 | メッシュ側のチェックに使う |
| shapely | 2.1.2 | 断面ラスタライズと張り出し幅の計算 |

### ヘッドレスレンダについて

GUI が無いのでオフスクリーン描画が要る。実際に試した結果:

- **採用: VTK のオフスクリーン (EGL)** — `vtkRenderWindow.SetOffScreenRendering(1)`
  だけで PNG が出た。VTK は X への接続に失敗したあと EGL に落ちる
  （`bad X server connection. DISPLAY=` という警告が出るが無害）。
  apt パッケージも仮想ディスプレイも要らない。
- **予備: numpy の Z バッファによるソフトウェアラスタライザ** —
  `harness/render.py` に同梱。EGL が使えない環境や GPU の無いコンテナ用。
  `ENCL_RENDERER=soft` で強制でき、VTK が例外を投げたときも自動で切り替わる。
- **却下: `xvfb-run`** — apt が必要（この母艦では sudo パスワードが要る）。
- **却下: pyrender / OSMesa ホイール** — 依存が重く、VTK で足りたので採用しなかった。

レンダが真っ白/真っ黒になった場合は VTK 側の失敗とみなして自動でソフトウェアに
落ちる。どちらを使ったかは `report.md` の先頭に出る。

## リポジトリの中身

```
harness/           ハーネス本体
  cli.py           `python -m harness check <design.py>`
  design.py        設計スクリプトの読み込みと派生データのキャッシュ
  geom.py          B-rep <-> メッシュ <-> ボクセルの変換（OCC / trimesh / shapely はここだけ）
  build.py         STEP / STL / 3MF 出力
  render.py        多視点 + 断面 PNG（VTK / ソフトウェア）
  report.py        Markdown レポート
  component.py     内蔵部品を表す型
  feature.py       フィーチャの占有領域 (claim) を表す型と、その作り方
  checks/          7 つのチェック（下記）
parts/             内蔵部品のダミー形状（BOM プリミティブ）
designs/           設計スクリプト
tests/             ネガティブテスト
out/               生成物（.gitignore 済み）
docs/AGENTS.md     AI が設計を書くときの規約
docs/HARNESS.md    各チェックの意味・閾値の根拠・限界
```

## チェック

| # | 名前 | 見るもの |
|---|---|---|
| 1 | manifold | 水密・多様体か（B-rep とメッシュの両方） |
| 2 | wall | 最小肉厚（レイキャスト法）。薄い箇所は座標も出す |
| 3 | bbox | 造形姿勢を適用したあと P1S の枠に収まるか |
| 4 | interference | ソリッド同士のブーリアン積の体積が 0 か |
| 5 | layout | **同じソリッドの中で**フィーチャ同士が場所を奪い合っていないか |
| 6 | clearance | 内蔵部品の外形 + クリアランスが筐体と干渉しないか |
| 7 | overhang | 造形姿勢を適用したあとの下向き面の面積と渡り幅 |
| 8 | openings | 内外を貫通する開口の一覧と面積（防水の要） |

**すべてのチェックは PASS/FAIL だけでなく実測値を返す。**
閾値の根拠と「何を見逃すか」は `docs/HARNESS.md` にある。

## ネガティブテストという約束

このリポジトリの最大の失敗モードは **「チェックが常に PASS を返すだけの飾りに
なること」**。それを防ぐため、各チェックには「意図的に壊した設計を食わせると
FAIL する」テストが付いている。

```bash
uv run pytest -q
```

- 肉厚を 0.8 mm に落とした変種 → `wall` が FAIL
- 部品を壁にめり込ませた変種 → `clearance` が FAIL
- 300 mm に伸ばした変種 → `bbox` が FAIL
- 止まり穴を貫通させた変種 → `openings` がその穴を検出して FAIL
- 造形姿勢を 90 度倒した変種 → `overhang` が FAIL
- O リング溝を基準ピンの根元に重ねた変種 → `layout` が FAIL（実際に出た不具合の再現）
- 取付ねじをシール溝に寄せた変種 → `layout` が FAIL
- 穴の宣言を 1 つ落とした変種 → `layout` が「宣言し忘れ」として FAIL

**ネガティブテストが無いチェックは未完成とみなす。**

## いまある設計

| 設計 | 何のためか |
|---|---|
| `designs/wildlife_cam/fit_coupon.py` | 嵌合公差テーブルを 1 回の印刷で確定させる校正クーポン（120 x 90 x 20 mm）。手順は [fit_coupon.md](designs/wildlife_cam/fit_coupon.md) |
| `designs/wildlife_cam/pir_bezel.py` | HC-SR501 を筐体壁に防水で貫通させるベゼル |

どちらも **まだ印刷していない**。`parts/hcsr501.py` の寸法が全て推定なので、
pir_bezel は実測が入るまで印刷しないこと。
