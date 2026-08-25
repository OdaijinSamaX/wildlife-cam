# FIX-NOTES — BLE 初期化が 0x103 (ESP_ERR_INVALID_STATE) で失敗する件

対象: `/tmp/esp32-fw/wildlife_box_b/`（Arduino-ESP32 core 3.3.11 / ESP32-WROOM-32E / CH340C）
結論: **1行の追加で直る。** 生の `esp_bt_*` / `esp_ble_gap_*` API はそのまま維持。設計書の必須3点も維持。

---

## 1. 原因（一次情報で裏取り済み）

症状の連鎖はこうなっていた:

1. **Arduino-ESP32 のコアが、`setup()` より前に BLE 用メモリを解放していた。**
   `initArduino()`（`cores/esp32/esp32-hal-misc.c`）に次のコードがある（実物を確認）:

   ```c
   bool userOverriddenBtInUse = ((void *)btInUse != (void *)_btInUse_default);
   if (!btClassicInUse() && !(userOverriddenBtInUse && btInUse())) {
     btMemRelease(BT_MODE_CLASSIC_BT);
   }
   if (!bleInUse() && !(userOverriddenBtInUse && btInUse())) {
     btMemRelease(BT_MODE_BLE);   // ← ここで BLE メモリが解放される
   }
   ```

   `btClassicInUse()` / `bleInUse()` / `btInUse()` は `esp32-hal-bt.h` で宣言され、
   実装は**弱いデフォルト（false を返す）**。強い定義を与えるのは通常「Arduino の BLE
   ライブラリを include したとき」。**我々は BLE ライブラリを使わず生 API を直叩き**して
   いるので、これらは全部 false のまま。結果、上の 2 つの `btMemRelease` が両方走り、
   **classic も BLE もコントローラ用 DRAM が起動時に全解放**される。

2. **全解放された状態だと IDF の `esp_bt_controller_init()` は 0x103 を返す。**
   `esp-idf/components/bt/controller/esp32/bt.c` の `esp_bt_controller_init()` に、
   実物で確認した次の判定がある（`ESP_ERR_INVALID_STATE` を返す箇所は2つ）:

   ```c
   //if all the bt available memory was already released, cannot initialize bluetooth controller
   if (btdm_dram_available_region[0].mode == ESP_BT_MODE_IDLE) {
       return ESP_ERR_INVALID_STATE;               // ← 今回はこれ
   }
   ...
   if (btdm_controller_status != ESP_BT_CONTROLLER_STATUS_IDLE) {
       return ESP_ERR_INVALID_STATE;               // ← こちらは status=IDLE なので通過
   }
   ```

   実機ログの `esp_bt_controller_get_status() = 0 (IDLE)` は**2つ目の判定を通過**する
   ことを意味する。つまり失敗しているのは**1つ目（メモリ全解放済み）**。我々が
   `mem_release` を一切呼んでいないのに 0x103 になる、という切り分け結果と完全に一致する。

**→ dispatch の疑い「Arduino コア側が起動時に解放している」は、一次情報どおり正しい。**

### 一次情報 URL

- Arduino-ESP32 起動時のメモリ解放ロジック（`initArduino()`）
  https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/esp32-hal-misc.c
- `btInUse()` / `bleInUse()` / `btClassicInUse()` の宣言（`extern "C"`）
  https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/esp32-hal-bt.h
- `btStart()` / `btMemRelease()` の実装
  https://github.com/espressif/arduino-esp32/blob/master/cores/esp32/esp32-hal-bt.c
- IDF の `esp_bt_controller_init()` が 0x103 を返す条件（メモリ全解放判定）
  https://github.com/espressif/esp-idf/blob/master/components/bt/controller/esp32/bt.c
- 同症状の既知 issue（裏付け）
  https://github.com/espressif/arduino-esp32/issues/2253

---

## 2. 採った対策（最小・生API維持）

**`wildlife_box_b.ino` に強い `bleInUse()` を定義して true を返させた。** これは
コア側が想定している上書きフックそのもの（BLE ライブラリが true を返すのと同じ役割）。

```cpp
// ヘッダが extern "C" なので C リンケージで定義する
extern "C" bool bleInUse(void) { return true; }
```

効果（上の misc.c のロジックに代入して確認）:

- `!bleInUse()` = `!true` = **false** → **BLE メモリは解放されない**（init 可能に）。
- `btInUse` は上書きしていないので `btClassicInUse()` 経路はそのまま → **classic は解放**
  される（**BLE 専用なので classic RAM が空くのはむしろ好都合**）。

あわせて `ble_init()` を次のように調整した:

- **`ESP_ERROR_CHECK`（失敗で abort＝再起動ループ）を廃止**し、各 API の戻り値を
  シリアルにログする形へ。失敗しても状態機械など他機能は動き続け、非プログラマが
  画面で原因を確認できる（元の abort→再起動ループを避ける）。
- 初期化順は IDF の BLE 専用定石どおり:
  `mem_release(CLASSIC)`（既解放でも無害）→ `esp_bt_controller_init(&cfg)` →
  `esp_bt_controller_enable(ESP_BT_MODE_BLE)` → `esp_bluedroid_init/enable` →
  `esp_ble_gap_register_callback` → `esp_ble_gap_set_scan_params`。

`config.h` は変更不要（★の設定項目もそのまま）。

### 期待される起動ログ（修正後）

```
=== wildlife-cam 箱B 受信ファーム ... ===
S0: 起動ロックアウト 5 秒間 PUMP 強制Low
[BLE] コントローラ/host 初期化 OK。scan パラメータ設定待ち…
設定: LINK_ID=0x42  USE_WHITELIST=0  REQUIRE_HMAC=1
[BLE] scan パラメータ設定完了 → scan 開始
[BLE] scan 開始成功。Pi の広告受信待ち…
```

---

## 3. 他の選択肢を採らなかった理由

| 選択肢 | 判定 | 理由 |
|---|---|---|
| **`btStart()` を呼ぶ** | ✗ 単独では効かない | `btStart()`→`btStartMode()` は内部で `esp_bt_controller_init()` を呼ぶだけ（一次情報で確認）。**起動時に解放されたメモリを復活はさせない**ので、同じ 0x103 になる。メモリ解放を止めない限り無意味 |
| **`#include <BLEDevice.h>`** | △ 効くが過剰 | BLE ライブラリが強い `bleInUse()=true` を提供するので解放は止まる（＝今回の対策と同じ原理）。ただし Bluedroid の C++ ラッパ一式をリンクしフラッシュが増える上、`BLEDevice::init()` と生 init の二重管理になりやすい。**1行で同じ効果が得られるので不要** |
| **ビルドフラグ / sdkconfig / build_opt.h で解放を抑止** | ✗ 不可・脆い | 解放は sdkconfig ではなく `initArduino()` の C コードが `btClassicInUse()/bleInUse()` の**戻り値**で分岐している。フラグで消せる箇所ではなく、コア改変は core 更新で消える。コアが用意した上書き口（InUse 関数）を使うのが正道 |
| **NimBLE 系へ切替** | △ 可能だが過大 | NimBLE-Arduino も同じ起動時解放の影響を受け、結局 `bleInUse()` を true にする必要がある（大きな載せ替えの割に本質は同じ）。Bluedroid が1行で直る以上、切替は不要。※ NimBLE でも重複フィルタ無効化は可能（`ble_gap_disc_params.filter_duplicates = 0` / `NimBLEScan::setDuplicateFilter(false)`）なので、将来切替が必要になっても必須要件は満たせる |

**優先順位: ①強い `bleInUse()`（採用） > ②`#include <BLEDevice.h>` > ③NimBLE 切替。**
`btStart()` 単独・ビルドフラグは**動かない/脆い**ため不採用。

---

## 4. 必須要件の確認（設計書 §14 U2）

「passive scan / 白リストフィルタ / 重複フィルタ無効」の3点は、今回の修正で**一切変えて
いない**。`esp_ble_gap_set_scan_params()` に渡す `scan_params`（`.ino` 内）で明示指定済み:

```cpp
static esp_ble_scan_params_t scan_params = {
  .scan_type          = BLE_SCAN_TYPE_PASSIVE,            // ① passive scan
  .own_addr_type      = BLE_ADDR_TYPE_PUBLIC,
#if USE_WHITELIST
  .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ONLY_WLST,  // ② 白リストのみ受理
#else
  .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,        //    (動作確認時は link_id+HMAC で絞る)
#endif
  .scan_interval      = SCAN_ITVL,
  .scan_window        = SCAN_WIN,
  .scan_duplicate     = BLE_SCAN_DUPLICATE_DISABLE,       // ③ 重複フィルタ無効（U2 必須）
};
```

`BLE_SCAN_DUPLICATE_DISABLE` は HCI の `Filter_Duplicates=0x00` に直結する。
本設計の「同じ広告を出し続けても点灯を延長しない」安全論拠が成立するために必須で、
Bluedroid でそのまま指定できることを確認済み（初期化方式の変更はこの指定に影響しない）。

---

## 5. まだ確認できていないこと（正直に）

- 本修正の**実ビルド/実機での成否はこちら（dispatch 側）で確認**とのことなので、当方では
  コンパイル・書き込みは行っていない（実機・Windows 環境が手元に無いため）。原因と対策は
  上記の一次情報で裏が取れているが、**最終確認は実機ログ**（§2 の期待ログが出るか）で。
- `own_addr_type` は動作確認用に `BLE_ADDR_TYPE_PUBLIC` のまま。現地で LE privacy を使う
  場合は Pi 側のアドレス種別に合わせて見直す（今回の 0x103 とは無関係）。

---

# 追記 — PUMP 実駆動（デッドマン回路の本体）

## A. 20kHz を CPU で叩く（LEDC/RMT/ISR を使わない理由）

`pump_burst()` は `digitalWrite` + `delayMicroseconds(25)` の**ソフトループ**で 20kHz を作る。
設計書 §5.2 の禁止事項どおり、**LEDC/RMT/タイマ ISR は一切使っていない**。理由はそれらが
「CPU がハングしてもクロックを出し続ける」ため。CPU が自分の足で叩く形にすると、**CPU（=この
ループ）が止まった瞬間にトグルも止まり、電圧ダブラはエッジしか通さないので出力がゼロに落ち、
C2 が R_pd を通して放電して IR が消える**。これがデッドマンの物理的な核心。

## B. デュアルコア配置（設計判断）と、なぜハングがポンプ停止に伝わるのか

| コア | 走らせるもの | 役割 |
|---|---|---|
| **Core1 (APP_CPU)** | `guardian_task` | **受理判定(§4.3)＋状態機械(§5.1)＋PUMP 20kHz 駆動を「同一ループ」で**回す |
| **Core0 (PRO_CPU)** | BLE(既定) ＋ `sampler_task` | gap_cb は生フレームをキューに積むだけ。sampler は ADC を占有し V_pump を公開＋ハング時の減衰を捕捉 |

**「なぜ状態機械のハングがポンプ停止に伝わるのか」＝ §5.4 単一ループ不変条件を守っているから。**
PUMP のエッジを出すのは `guardian_task` の中の `pump_burst()` **だけ**で、それは**同じイテレーション
で seq 鮮度を再判定した直後**に呼ばれる。したがって:

- guardian のどこか（状態機械・受理判定・`h` 模擬・スタックオーバーフロー等）が固まる
  → ループが回らない → `pump_burst()` が呼ばれない → **C2 放電 → IR 消灯**。
- 加えて guardian は毎イテレーションで `esp_task_wdt_reset()` を実行（§5.4）。固まれば feed が
  止まり、TWDT が PANIC 設定ならリセット（層4）。IDLE1 飢餓も backstop になる。
- BLE(core0) が固まった場合 → フレームが来ない → seq が進まない → 鮮度切れ → guardian が
  `g_sm_pump_ok=false` にする → ポンプ停止。**どちらのコアが死んでも消灯側に倒れる。**

**やってはいけない構成（dispatch の警告）:** 「状態機械を core0、ポンプを core1 の別ループ」に
分けること。それだと状態機械がハングしてもポンプ側ループは古い `ir_should_be_on` のまま回り
続け、デッドマンが無効になる。**本実装は判定とポンプを同一タスク・同一ループに閉じ込めてある**
ので、その罠を踏んでいない。ADC だけを core0 に分離したのは、①判定/ポンプの邪魔をしない、
②guardian ハング時に生き残って減衰を測れる、の2点のためで、**判定ロジックは一切 core0 に出して
いない**（安全上の分割はしていない）。

## C. 減衰時間の計測方法（§5.5 / 要件5）

- **通常 OFF（`o` または状態機械の OFF）**: guardian が V_pump（sampler が 1kHz 更新する共有値）を
  監視し、PUMP 停止（ON→OFF 立下り）から `V_pump < 1.3V` までの時間を **ms 精度で自動ログ**する。
- **ハング（`h`）の場合**: guardian(core1) は自分では測れない。**core0 の `sampler_task` が生き残る**
  ので、① 常時サンプルしているリングバッファ（256点≒256ms）を freeze 時刻から走査し、②未クロス
  ならライブで待って、`V_pump < 1.3V` までの時間を出す。これが dispatch の「リングバッファに貯めて
  復帰後に吐く」案の実装。testでは freeze 検知(100ms) → 追従計測で捕捉できる。

## D. ★重要な発見 — 減衰時間が仕様(1.0〜2.5s)より1桁速い可能性（推測でなく RC 計算）

設計書内に**数値の不整合**がある。設計書 §5.3 は R_pd を **10kΩ** に確定（塩霧対策で 100kΩ を撤回）。
一方 §4.5/§5.2 と Phase 2-2 の合格条件は減衰 **約1.5s（1.0〜2.5s）**。だが R_pd=10kΩ・C2=10µF の
RC からは:

```
τ = R_pd × C2 = 10kΩ × 10µF = 100 ms
V_pump 5.9V → 1.3V:  t = τ × ln(5.9/1.3) = 0.10 × 1.51 ≈ 0.15 s  (150ms)
```

**つまり期待減衰は約 0.15s で、仕様の 1.5s の約 1/10。** 「1.5s」は 100kΩ 版の名残か、小数点位置の
誤記の可能性が高い。**どちらが正か（typo なのか、C2 を 100µF にすべきなのか）は人間が設計を
突き合わせて決める話**なので、ファーム側で数値を捏造して「合格」にはしない。ファームは実測を
そのまま出す。実機で `o` を押したときのログ（例 `[減衰] V_pump<1300mV まで 150 ms`）が Phase 2-2 の
1.0〜2.5s に**入らなくても、それはファームのバグではなく設計値の要再確認**、という位置づけ。

- 安全性の向きは問題なし（**速く消える＝より安全**。デッドマンとしては 0.15s でも成立）。
- もし本当に 1.0〜2.5s の粘りが要るなら、C2 を約 68〜100µF に上げる（τ を 10 倍）か、R_pd を
  見直す（ただし §5.3 の塩霧リスクと相反）。**これは設計判断**。
- ユーザの C2 は暫定の 10µF 電解。§11 では電解は不可（高温多湿で容量低下）なので、いずれ積セラ
  X7S 10µF（発注リスト #6）へ。容量が同じなら減衰時間もほぼ同じ（≈0.15s）。

## E. SENSE(ADC) の精度について（正直な注記）

- 100k/100k 分圧なので V_pump=6.2V のとき **ピン電圧 3.1V** で、ESP32 の ADC はこの辺（>2.5V）で
  非線形＝飽和ぎみ。**満充電の絶対値（5.5〜6.2V 判定）はテスタ併用を推奨**。`analogReadMilliVolts`
  （eFuse 校正）で読んでいるが上端の誤差は残る。
- 一方 **減衰の閾値 1.3V → ピン 0.65V は ADC の正確な領域**なので、**減衰時間（相対計測）は ESP32
  だけで信頼できる**。dispatch の「ESP32 は減衰計測が得意」という見立てどおり。
- ポンプ動作中の V_pump 表示にはポンプ・リップルが乗る。表示は瞬時値なので数十 mV 揺れる。
