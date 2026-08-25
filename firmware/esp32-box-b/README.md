# 箱B 受信ファーム — インストールから書き込みまで

読者: 非プログラマ（菊川）。**上から順にそのままなぞれば書き込めます。**
このファームは **Freenove ESP32-WROOM 開発ボード**（CH340C 搭載）用です。

---

## 0. これは何をするファームか（今回の範囲）

秋月の部品がまだ届いていないので、**デッドマン回路（ポンプ）は組めません**。
なので今回のファームは **「BLE で Pi の電波を受信して、正しく判定するところまで」** に限定しています。

- Pi が 100ms ごとに出す BLE 広告（`ADV_NONCONN_IND`）を **passive scan で受信**
- 設計書 §4.1 の 24 バイトのデータを **中身に分解**
- 設計書 §4.3 の **受理規約**（特に「seq が厳密に増えたときだけ点灯を延長する」= 本設計の命）を実装
- 設計書 §5.1 の **状態機械 S0〜S9**
- **ポンプ（PUMP）は実際には動かさず、シリアルに「今なら点ける／消す」とログを出すだけ**（回路が無いので）

結果は **シリアルモニタ（パソコン画面）に日本語で流れます**。IR は点きません。

---

## 1. なぜ Arduino を選んだか（Arduino か ESP-IDF か）

**Arduino-ESP32 を選びました。** 理由:

- **書き込みが一番やさしい**。Arduino IDE を入れてボードを選び、→（Upload）ボタンを押すだけ。
  Python や `idf.py`、コマンドライン環境の構築が要りません（ESP-IDF はこれが必要で、非プログラマには重い）。
- **それでいて中身は同じ**。Arduino-ESP32 は土台が ESP-IDF なので、設計書が指定する
  低レベル API（`esp_ble_gap_set_scan_params` に `BLE_SCAN_TYPE_PASSIVE` /
  `BLE_SCAN_FILTER_ALLOW_ONLY_WLST` / `BLE_SCAN_DUPLICATE_DISABLE`）を **そのまま直接呼べます**。
  実際このファームは Arduino の簡易 BLE ラッパを使わず、その3つの設定を厳密に指定しています。

→ **「書き込みの易しさ（Arduino）」と「設計書どおりの厳密な制御（ESP-IDF の API）」を両取り**しています。

---

## 2. 準備するもの

- Freenove ESP32-WROOM ボード（手元の2枚のうち1枚）
- USB ケーブル（データ通信できるもの。充電専用ケーブルは不可）
- Windows か Mac のパソコン

---

## 3. インストール手順

### 3-1. CH340 ドライバを入れる（USB でボードを認識させる）

Freenove ボードの USB チップは **CH340C**。これのドライバが要ります。

- メーカー（WCH）配布ページ「CH341SER」を入れる（"CH340 driver windows/mac" で検索）。
- 入れたらパソコンを再起動。

> 確認: ボードを USB でつなぎ、Windows なら「デバイスマネージャー」の「ポート(COM と LPT)」に
> `USB-SERIAL CH340 (COMx)` が出れば成功。Mac は `/dev/tty.wchusbserial*` が出ます。

### 3-2. Arduino IDE を入れる

- 公式サイトから **Arduino IDE 2.x** をダウンロードして普通にインストール。

### 3-3. ESP32 ボード定義を追加する

1. Arduino IDE を開く →「ファイル」→「基本設定」（Mac は「Arduino IDE」→「設定」）。
2. **「追加のボードマネージャの URL」** に次を貼って OK:
   ```
   https://espressif.github.io/arduino-esp32/package_esp32_index.json
   ```
3. 左の「ボードマネージャ」アイコン → **「esp32」で検索 → "esp32 by Espressif Systems" を Install**。
   （数百 MB あるので少し待ちます）

---

## 4. ファームを開いて設定する

1. このフォルダの中の **`wildlife_box_b`** フォルダごと使います。
   `wildlife_box_b/wildlife_box_b.ino` を Arduino IDE で開く（`config.h` も一緒に開かれます）。
2. **`config.h` の★印だけ**を必要に応じて編集します（本体 `.ino` は触らない）:
   - **★1 `LINK_ID`**: Pi 側 irlink と同じペア番号にする。
   - **★2 `HMAC_KEY`**: Pi 側と1バイトも違わないようにする。**ダミーのままだと Pi の本物フレームを弾きます。**
   - **★3 `USE_WHITELIST`**: 最初は `0`（Pi のアドレスを知らなくても動く）。現地では `1` にして `PEER_ADDR` に Pi のアドレスを入れる。
   - まず動作を見たいだけなら、`REQUIRE_HMAC` を一時的に `0` にすると HMAC 無しで試せます（**本番は必ず 1 に戻す**）。

---

## 5. 書き込む

1. ボードを USB でつなぐ。**（このテストでは電池は使いません。電池 JST は挿さない）**
2. Arduino IDE 上部で **ボードを選ぶ**:「ツール」→「ボード」→「esp32」→ **`ESP32 Dev Module`**。
3. **ポートを選ぶ**:「ツール」→「ポート」→ CH340 の `COMx`（Mac は `wchusbserial`）。
4. 左上の **→（Upload / マイコンに書き込む）** ボタンを押す。
5. 画面下に `Connecting....` が出たまま進まないときは、ボードの **BOOT ボタンを押しっぱなし**にして、
   `Connecting` の間だけ押す（書き込みが始まったら離してよい）。
   - うまくいかないときは「ツール」→「Upload Speed」を **115200** に下げると通ることがあります。
6. `Done uploading` が出れば成功。

---

## 6. 動作を見る（シリアルモニタ）

1. 右上の **虫めがね（シリアルモニタ）** を開く。
2. 右下の速度を **115200 baud** にする。
3. 次のようなログが日本語で流れます:

```
=== wildlife-cam 箱B 受信ファーム (受信+判定のみ / PUMP はスタブ) ===
S0: 起動ロックアウト 5 秒間 PUMP 強制Low
設定: LINK_ID=0x2A  USE_WHITELIST=0  REQUIRE_HMAC=1
[BLE] scan パラメータ設定完了 → scan 開始
[BLE] scan 開始成功。Pi の広告受信待ち…
    [PUMP-stub] IDLE (デッドマン: ポンプ停止→約1.5秒でIR消灯)  (ON 指令なし)
[beaconA] state=S0_RESET_LOCKOUT ir_gate=0 last_cmd_seq=0 fault{bad_mac=0,seq_regress=0,orphan=0}
```

Pi（または下記のスマホ手打ち）から正しいフレームが来ると:

```
[epoch] 初回: epoch=7 → BOOTSTRAP やり直し
[bootstrap] 連続増加 2/2  seq=51903
>>> 状態遷移 S1_BOOTSTRAP → S3_IDLE_HIGH  (bootstrap 完了)
[CMD] PREARM 受理 seq=51904
>>> 状態遷移 S3_IDLE_HIGH → S4_BOOST  (PREARM 受理)
[CMD] ON 受理 seq=51905 → 鮮度更新
>>> 状態遷移 S4_BOOST → S5_LIT  (ON 受理(正規))
    [PUMP-stub] BURST(本番ならGPIO25を20kHzトグル)  (点灯継続の条件成立)
```

そして Pi が黙る／死ぬと、**同じ seq を受信し続けても点灯は延長されず**、2 秒（LIT の HOLD）で:

```
[破棄] seq 後退/据置き seq=51905 <= last=51905 (seq_regress=1)
>>> 状態遷移 S5_LIT → S3_IDLE_HIGH  (HOLD 満了(鮮度切れ))
    [PUMP-stub] IDLE (デッドマン: ポンプ停止→約1.5秒でIR消灯)  (鮮度切れ(リンク断/Pi死))
```

**この「同じ seq では延長しない」動作が、本設計の唯一の安全論拠（設計書 §1）です。**

---

## 7. Pi がまだ無いときの動作確認（任意）

スマホアプリ **nRF Connect** で、自作の広告（Manufacturer Specific Data）を投げて試せます。
ただし HMAC を手で作るのは大変なので、`config.h` の **`REQUIRE_HMAC` を `0`** にしてから試します
（パースと状態遷移だけ確認できる）。**確認が済んだら必ず `1` に戻すこと。**

Manufacturer Specific Data（先頭 Company ID = `FF FF`）の中身（設計書 §4.1、リトルエンディアン）:

| バイト位置 | 中身 | 例 |
|---|---|---|
| 0-1 | Company ID | `FF FF` |
| 2 | ver | `01` |
| 3 | type(CMD) | `01` |
| 4 | link_id | `2A`（config の LINK_ID と一致） |
| 5-6 | epoch (LE) | `07 00` |
| 7-10 | seq (LE) | 送るたびに +1 増やす |
| 11 | want | `00`=OFF `01`=ON `02`=PREARM |
| 12 | ttl_ds | `5E` (=94→9.4秒) 等 |
| 13 | flags | `03` |
| 14 | duty_hint | `02`=BOOST |
| 15 | reserved | `00` |
| 16-23 | hmac8 | REQUIRE_HMAC=0 なら何でも可（例 `00×8`） |

**seq を毎回 +1 して送ると点灯継続、同じ seq のまま送ると点灯が延長されない**ことが確認できます。

---

## 8. 今回やっていないこと（次の段）

- **PUMP の実駆動**（回路未着のためスタブ。部品到着後に GPIO25 の 20kHz トグルへ）
- **状態ごとの scan duty 切替**（省電力。今回は受信優先で連続 scan 相当。Phase 4 で追加）
- **復路ビーコンの実送信**（今回はログのみ。TX は次段）
- **ADC 読み取り**（SENSE/SHUNT/VBAT は回路未着のため未使用。ピン定義だけ正しく置いてある）

いずれも安全ロジック（受理規約・状態機械）が正しく動くことを先に固めるための切り分けです。

---

## ファイル構成

```
esp32-fw/
├── README.md                      ← この手順書
└── wildlife_box_b/
    ├── wildlife_box_b.ino         ← 本体（受信・受理規約・状態機械・PUMPスタブ）
    └── config.h                   ← ★ここだけ編集（LINK_ID / HMAC鍵 / 白リスト等）
```
