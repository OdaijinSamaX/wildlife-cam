# enclosure-lab で AI が設計するときの規約

このファイルが設計スクリプトの正本。`designs/` に置くファイルは必ずこの形にする。
上位のプロトコルは `/srv/homelab/repos/home-lab-setup/AGENTS.md` にある。矛盾したら
安全側（厳しい方）を採る。

## 0. 大原則

- **AI には目が無い。** 書いた形が正しいかは、レンダと数値チェックを通してしか
  分からない。設計を書いたら必ず `uv run python -m harness check` を通し、
  `out/<design>/report.md` の画像と数値を見てから次に進む。
- **推測を数字として書かない。** 分からない寸法は決め打ちせず「推定」と明記する。
- **チェックが PASS したことは、設計が正しいことを意味しない。**
  各チェックの「限界」（`docs/HARNESS.md`）に書いてあるものは見逃す。

## 1. ファイルの形

```python
"""何のための部品か / 想定する取り付け方 / 未確定事項"""

import cadquery as cq
from parts import hcsr501

DESIGN_NAME = "pir_bezel"          # 省略するとファイル名が使われる

PARAMS = {                          # 全ての寸法はここに集約する
    "wall": 3.0,
    ...
}

PRINT_ORIENTATION = {"rotate": (180, 0, 0)}   # 造形姿勢。overhang はこれを適用してから見る

COMPONENTS = [hcsr501.place(at=(0, 0, -6.2))] # 内蔵部品。clearance / interference に使う

CHECK_CONFIG = {
    "min_wall_mm": 1.6,
    "max_bbox_mm": (256, 256, 256),
    "max_overhang_deg": 50,
    "component_clearance_mm": 0.4,
}

SECTIONS = [                        # 任意。省略すると XZ 中央 / YZ 中央
    {"name": "xz_mid", "origin": (0, 0, 0), "normal": (0, -1, 0)},
]

def build(p=PARAMS):
    """cq.Workplane か cq.Assembly を返す"""
```

## 2. 座標と単位

- 単位は **mm**、**Z が上**。
- 原点は **「取り付け基準面」** に置く。壁を貫通する部品なら「筐体壁の外面」、
  基板を載せる部品なら「基板の座面」。docstring に必ず書く。
- 造形姿勢は `PRINT_ORIENTATION` で表す。設計座標を造形の都合で歪めない。

## 3. 寸法の書き方

**式の中に生の数値を置かない。** すべて `PARAMS` に出し、各行に出所を書く。
出所は次の 3 種類だけを使う。

| 書き方 | 意味 |
|---|---|
| `# HC-SR501 データシート` | 一次資料に載っている値 |
| `# 実測 2026-08-22` | ノギスで測った値。日付を必ず書く |
| `# 推定（未実測）` | 根拠のない概算。**必ず「推定」と書く** |

計算で出した値は `# 計算値: 23.0 + 2 * (1.5 * 0.75)` のように式ごと残す。
設計方針で決めた値は `# 設計値` と書く。

推定値は後で実測に差し替える。差し替えたら:

1. `PARAMS` の値とコメントを更新する
2. 部品側なら `parts/*.py` の `DIM_SOURCE` を `"measured:YYYY-MM-DD"` に変える
3. **その部品を使っている全ての設計で `harness check` を回し直す**

## 4. parts/ の使い方

内蔵部品（プリントしない実物）は `parts/` のモジュールを使う。各モジュールは:

```python
DIM_SOURCE = "datasheet" | "measured:YYYY-MM-DD" | "estimated"
def model(**kw) -> cq.Workplane            # 実体
def envelope(clearance=0.0, **kw) -> cq.Workplane   # 外形 + クリアランス
ENVELOPE = envelope(0.5)
def place(at=(0,0,0), rotate=(0,0,0), **kw) -> Component  # 配置済み
```

`COMPONENTS` には `place()` の戻り値を入れる。生の `Workplane` を入れても動くが、
その場合 envelope がバウンディングボックス近似になり、レポートに警告が出る。

**envelope は「意図した接触面」にはクリアランスを足さない。**
たとえば基板を端面で押さえる構成なら、その面は接触が正しいのでクリアランス 0 にする。
足してしまうと、正しい設計が clearance FAIL になる。

## 5. 造形の前提（P1S / ASA / 0.4 mm ノズル）

| 項目 | 既定値 | 根拠 |
|---|---|---|
| 最小肉厚 | 1.6 mm | 0.4 mm 押出幅 x 4（外壁 2 + 内壁 2）。屋外品で割れない下限 |
| 造形枠 | 256 x 256 x 256 mm | P1S のビルドボリューム |
| オーバーハング閾値 | 50 度 | ASA でサポート無しに刷れる限界のあたり |
| 層厚 | 0.2 mm | 第 1 層の判定に使う |
| ブリッジ可の渡り幅 | 10 mm | これを超える下向き面はサポートが要るとみなす |

意図的にこれを外す設計（例: 公差クーポンの 0.8 mm 薄板）は、`CHECK_CONFIG` で
閾値を上書きし、**なぜ外すのかを docstring に書く**。黙って外さない。

## 6. 防水設計のルール

- **開口は必ず `CHECK_CONFIG["expected_openings"]` に宣言する。**
  宣言が無いと openings チェックは WARN のまま素通りする。宣言してあれば、
  意図しない貫通穴が増えた瞬間に FAIL になる。
- ねじ穴を O リング溝の内側に置かない。置いたらそこが漏れ経路になる。
  外側に置いた場合は「相手側のボスを止まり穴にする」ことを docstring に書く。
- 密閉筐体には通気ベント（`parts/gore_vent.py`）を入れる。内圧の振れを逃がさないと
  O リングを押し広げて水を吸う。
- O リング溝の寸法は `parts/oring.py` の根拠（圧縮率 25% / 充填率 78%）に従う。
  外すなら計算し直して docstring に残す。
- PIR は遠赤外を見るので、アクリルや PC の窓を透過しない。窓を張る構成は成立しない。

## 7. 書いたあとにやること

```bash
uv run python -m harness check designs/<...>.py
```

1. `report.md` の **断面図を必ず見る**。防水筐体は溝と肉厚が中に隠れるので、
   外観だけでは判断できない。
2. FAIL/WARN の実測値を読む。閾値を緩める前に、まず形を直せないかを考える。
3. 新しい種類の失敗を潰したら、`tests/test_checks_negative.py` にその失敗を
   再現するケースを足す。**ネガティブテストが無いチェックは未完成。**
4. 推定値のまま残っているものを docstring の「未確定事項」に列挙する。

## 8. やってはいけないこと

- チェックを通すためだけに閾値を緩める（理由を書かずに）
- 推定寸法を「実測」と書く
- `out/` をコミットする
- 実測が入っていない部品の設計を印刷に回す
