// ============================================================================
// wildlife-cam γ版 箱B  受信ファーム  設定ファイル
//   ここに書いてある値だけを編集すればよい。プログラム本体(.ino)は触らない。
//   （非プログラマ向け: ★印の3か所だけは必ず Pi 側と一致させること）
// ============================================================================
#pragma once
#include <stdint.h>

// ---------------------------------------------------------------------------
// ★1. ペア識別子 link_id  (Pi 側 irlink と同じ値にする。0〜255)
// ---------------------------------------------------------------------------
static const uint8_t LINK_ID = 0x42;   // Pi 側 ble_advertiser.py の --link-id 既定値に一致

// ---------------------------------------------------------------------------
// ★2. HMAC 共有鍵  (Pi 側と1バイトも違ってはいけない)
//     設計書 §4.1: HMAC-SHA256(key, ver..reserved) の先頭8バイトで認証する。
//
// ★★★ 2026-08-25 / 監査 順位2(b): 無人13日運用に入れる前に本番鍵へ貼り替えること ★★★
//
//   貼り方（Pi 側と必ず「同時に」替える。片方だけ替えると全フレームが bad_mac で捨てられ、
//   ESP32 は鮮度切れで消灯したまま13日が過ぎる）:
//
//     1. 鍵を1本つくる。例: openssl rand -hex 32
//        ★この値はシリアルにもログにも文書にも残さないこと。
//     2. 下の【本番鍵の空欄】に 0x.. のカンマ区切りで貼る（32バイト推奨）。
//     3. すぐ下の HMAC_KEY_IS_PLACEHOLDER を 1 → 0 にする。
//     4. 同じ鍵を Pi 側 ble_advertiser.py の --key に渡す。
//        ※ --key は文字列を受けるので、hex を渡すなら Pi 側も ESP32 側も
//          「同じバイト列」になる表現に揃えること（下の空欄に貼るのは "バイト列"）。
//     5. 焼く順番: ESP32 を焼く → Pi を再起動 → シリアルで [CMD] ... 受理 を確認。
//        bad_mac が増え続けるなら鍵が食い違っている（片方だけ元に戻さないこと）。
//
//   1 のまま焼いた場合: コンパイル時に #warning が出て、起動時と beaconB に
//   「公開テスト鍵のまま」の警告行が出続ける。無人運用に投入してはいけない。
// ---------------------------------------------------------------------------
#define HMAC_KEY_IS_PLACEHOLDER 1   // ★本番鍵を貼ったら 0 にする

#if HMAC_KEY_IS_PLACEHOLDER
#warning "HMAC_KEY が公開テスト鍵のままです。無人運用の前に config.h で本番鍵へ貼り替えてください"
// 机上試験用。Pi 側 ble_advertiser.py の --key 既定値 "phase1-public-test-key" の
// ASCII バイト列(22バイト)。★公開値であり秘密鍵ではない。
static const uint8_t HMAC_KEY[] = {
  0x70,0x68,0x61,0x73,0x65,0x31,0x2D,0x70,
  0x75,0x62,0x6C,0x69,0x63,0x2D,0x74,0x65,
  0x73,0x74,0x2D,0x6B,0x65,0x79
};
#else
// ==================== 【本番鍵の空欄】ここに貼る。他は触らない ====================
static const uint8_t HMAC_KEY[] = {

};
// ================================================================================
static_assert(sizeof(HMAC_KEY) >= 16,
              "HMAC_KEY が空か短すぎます: config.h の【本番鍵の空欄】に 16 バイト以上を貼ってください");
#endif

static const size_t HMAC_KEY_LEN = sizeof(HMAC_KEY);

// ---------------------------------------------------------------------------
// ★3. 白リスト(ホワイトリスト)を使うか
//     0 = 使わない(初期の動作確認向け)。link_id + HMAC だけでフィルタする。
//         → Pi のアドレスが分からなくても、机上でとりあえず動かせる。
//     1 = 使う(現地向け)。下の PEER_ADDR に Pi の static random address を入れる。
//     ※設計書の本当の安全フィルタは link_id + HMAC。白リストは CPU 負荷を
//        減らすための最適化(§6.8)なので、0 でも安全性は落ちない。
// ---------------------------------------------------------------------------
#define USE_WHITELIST 0
// Pi の BLE アドレス (USE_WHITELIST=1 のときだけ使う。左から順に6バイト)
static const uint8_t PEER_ADDR[6] = { 0xC0,0xDE,0xCA,0xFE,0x00,0x01 };

// ---------------------------------------------------------------------------
// 動作確認モード: HMAC 検証を一時的に無効化して、パースと状態機械だけ試す
//   1 = HMAC を必ず検証する(本番)。
//   0 = HMAC を検証しない(スマホの nRF Connect 等で手打ちの広告を投げて
//        パース/状態遷移だけ確認したいとき。★本番では必ず 1 に戻すこと)
// ---------------------------------------------------------------------------
#define REQUIRE_HMAC 1

// ---------------------------------------------------------------------------
// GPIO 割り当て  (/tmp/gpio-remap-result.md の読み替え結果に従う)
//   今回はスタブなので PUMP は駆動しない(定義だけ正しく置く)。
// ---------------------------------------------------------------------------
static const int PIN_PUMP     = 25;  // ポンプ駆動(本番は出力+外付け10kΩプルダウン)。今回は非駆動
static const int PIN_SENSE    = 34;  // ADC1_CH6 入力専用: ポンプ電圧分圧
static const int PIN_SHUNT    = 35;  // ADC1_CH7 入力専用: IR 電流シャント
// ★★ 2026-08-25 / 監査 順位3【SHUNT を判定に使ってはいけない】
//    IR 0.4〜0.6A × シャント 0.1Ω = 全部で 40〜60mV。増幅器は無い(§5.2)。
//    ところがこの基板の ADC 読み値の下限は 142mV(8/23 対照試験: 内部45kΩで完全に 0V に
//    落としたピンが 8秒間 142mV から動かなかった)。全点灯も完全消灯も同じ数字になり、
//    しかも非ゼロなので、どんな判定も「電流は流れている」と読む = 恒真式。
//    → `shunt_mv_off > 5mV` のような AND 項は独立確認ではない。足さないこと。
//    現状ファームは SHUNT を一度も読んでいない(ピン定義のみ)。読み始める前にここを読むこと。
//    代替(帰国後): VBAT_IR(GPIO36)の OFF 前後 200ms 平均差 ≈ 270mV で見る(監査 順位3)。
static const int PIN_VBAT_IR  = 36;  // ADC1_CH0(VP) 入力専用: 12V パック電圧
static const int PIN_VBAT_ESP = 39;  // ADC1_CH3(VN) 入力専用: ESP32 パック電圧
static const int PIN_JP1      = 27;  // デジタル入力+内部プルアップ: 有線切り戻しジャンパ

// ---------------------------------------------------------------------------
// プロトコル定数 (設計書 §4.1)
// ---------------------------------------------------------------------------
static const uint16_t COMPANY_ID = 0xFFFF;  // SIG 予約(内部/テスト用)
static const uint8_t  PROTO_VER  = 0x01;
static const uint8_t  TYPE_CMD   = 0x01;     // Pi → ESP32
static const uint8_t  PAYLOAD_LEN = 24;      // company_id(2)..hmac8(8)
static const uint8_t  HMAC_MSG_OFF = 2;      // HMAC 対象は ver から
static const uint8_t  HMAC_MSG_LEN = 14;     // ver..reserved (offset 2..15)
static const uint8_t  HMAC_OFF     = 16;     // hmac8 の位置

// want の値
enum { WANT_OFF = 0x00, WANT_ON = 0x01, WANT_PREARM = 0x02 };
// duty_hint の値
enum { DUTY_LOW = 0, DUTY_HIGH = 1, DUTY_BOOST = 2 };

// ---------------------------------------------------------------------------
// タイムアウト階層 (設計書 §4.5 / §5.1)  単位: マイクロ秒
// ---------------------------------------------------------------------------
static const int64_t BOOT_LOCKOUT_US = 5LL   * 1000000; // S0: 起床後5秒 PUMP 強制Low
static const int64_t IDLE_HOLD_US    = 600LL * 1000;    // IDLE 時の鮮度 600ms
static const int64_t LIT_HOLD_US     = 2000LL* 1000;    // LIT 時の鮮度 2.0s(遮蔽対策)
static const int64_t TCAP_US         = 45LL  * 1000000; // 絶対上限 45秒
// ★2026-08-25 / 監査 順位2: TCAP_US の起点は「状態機械が点灯を決めた時刻」ではなく
//   「ランプが実際に熱い時間」= lamp_hot_since。PUMP 出力が連続でこの時間 Low に
//   なったときだけ起点をクリアする。根拠: 実測の消灯 151ms の 3.3倍、かつ BLE 広告
//   間隔 100ms(U4 で確定)の 5倍。OFF→100ms 後 ON を繰り返してもクリアできない。
static const int64_t LAMP_COOL_US    = 500LL * 1000;    // PUMP が連続 500ms Low → 冷えた
static const int64_t BOOST_MAX_US    = 8LL   * 1000000; // BOOST は最大8秒
static const int64_t COOLDOWN_US     = 60LL  * 1000000; // COOLDOWN 60秒 ON 拒否
static const int64_t ORPHAN_US       = 600LL * 1000000; // 600秒 CMD 無しで ORPHAN
// ★2026-08-25 / 監査 順位2: デューティ計測窓を「10分ごとに丸ごとゼロクリア」から
//   「10秒 x 60個のリングでずらして数える」へ。旧方式では窓の後半5分＋次の窓の前半5分
//   ＝連続10分が正規に通っていた。計上の基準も ON 指令ではなく lamp_hot(ランプの実態)。
static const int64_t  DUTY_BUCKET_US  = 10LL * 1000000;  // バケツ1個 = 10秒
static const int      DUTY_RING_N     = 60;              // 60個 = 600秒(10分)のスライド窓
static const uint32_t DUTY_BUDGET_MS  = 300000;          // その窓の中の点灯上限 5分
static const uint32_t DUTY_RELEASE_MS = 270000;          // ここまで落ちたら解除(ヒステリシス)

static const int64_t BEACON_A_US = 2LL  * 1000000;      // 復路 subtype A 周期(ログのみ)
static const int64_t BEACON_B_US = 10LL * 1000000;      // 復路 subtype B 周期(ログのみ)

// ---------------------------------------------------------------------------
// scan パラメータ (0.625ms 単位)。今回は連続 scan 相当で受信を優先する。
//   状態ごとの duty 切替(§5.1)は電力最適化なので Phase4 で追加(README 参照)。
// ---------------------------------------------------------------------------
static const uint16_t SCAN_ITVL = 0x00A0;  // 100ms
static const uint16_t SCAN_WIN  = 0x00A0;  // 100ms (itvl==win → ほぼ連続)

// ループの刻み(ms)。TWDT を蹴りつつ CPU を空けすぎない程度。
static const uint32_t LOOP_TICK_MS = 5;

// ---------------------------------------------------------------------------
// PUMP 実駆動 / ベンチ試験 / SENSE (今回追加)
// ---------------------------------------------------------------------------
// ★ベンチ試験コマンド。1=有効(p/o/h/s)。本番は 0 にして 'h'(ハング模擬)を無効化。
#define BENCH_MODE 1

// 20kHz 矩形波: 周期 50us、半周期 25us。CPU が自分の足で叩く(LEDC/RMT/ISR 禁止)。
static const uint32_t PUMP_HALF_US   = 25;    // 半周期
static const uint32_t PUMP_BURST_US  = 8000;   // ★実験: デューティを上げて出力インピーダンスを下げる
static const uint32_t BENCH_FORCE_ON_MS = 3000; // 'p' の強制ON 継続時間

// SENSE(GPIO34, ADC1_CH6): C2 電圧を 100k/100k で分圧 → 実 V_pump = ピン電圧 × 2
static const float    SENSE_DIVIDER   = 2.0f;
static const int      DECAY_THRESH_MV = 1300;   // V_pump がこれ未満になったら「消灯」とみなす(Vgs(th)相当)
static const uint32_t DECAY_TIMEOUT_MS = 3000;  // これを超えて落ちなければ no_decay(=デッドマン死の疑い)
// ★2026-08-23 実測: 本回路の V_pump は約 3,130mV(倍圧していない。設計書 §5.2 の 5.9V は誤り)。
//   旧値 3000 は実測値のすぐ下にあり、MOSFET を繋いで少し垂れただけで減衰計測が
//   「黙って走らなくなる」。走らなかったことは従来どこにも出力されなかった。
//   閾値(1300mV)から十分離れていれば計測できるので 2000 に下げる。
static const int      VPUMP_MIN_FOR_DECAY_MV = 2000; // これ以上まで上がっていた場合のみ減衰計測を開始

// ---------------------------------------------------------------------------
// 減衰の「合格」判定 — 時定数 τ で測る (2026-08-25 / 監査 順位1)
//
//   旧: 「1.3V を割るまでの時刻」を 0.8〜3.0秒 の窓で見る（設計書 §5.5）。
//       設計書の「1.5秒」が10倍の書き間違いで、健康な回路の 0.15秒は窓に入らず、
//       R_pd が外れた故障(約3秒)のほうが窓に入っていた。
//   新: 下り坂で V_hi を切った時刻と V_lo(=V_hi の半分)を切った時刻の差 t_half を測る。
//       t_half = τ・ln2 で、ピーク電圧に一切依存しない。
//         健康(R_pd 10k 込み τ≈95ms)      → t_half ≈ 66ms
//         R_pd かゲート脚が外れ(τ≈2s)     → t_half ≈ 1386ms   ← 21倍離れる
//
//   ★閾値が監査本文の 4.0V/2.0V ではなく 2.0V/1.0V な理由（重要）:
//     監査 順位1 は 4.0V→2.0V と書いているが、それは設計書の「V_pump=5.9V」を
//     前提にした数字。HANDOFF 2026-08-23 §2/§3 で V_pump の実測は
//     無負荷 3.13V / 実負荷 2.79V と確定しており、単段整流なのは意図的に正しい
//     （D_clamp のアノードを 3V3 に移してはいけない）。よって 4.0V は永久に来ない。
//     4.0V のまま実装すると「健康な回路が一度も窓に入らない」という直そうとした穴を
//     そのまま作り直すことになる。比 2:1 を保てば t_half = τ・ln2 は同じなので、
//     実測ピーク 2.79V の下に収まる 2.0V/1.0V を採る（分圧後のピンでは 1.0V/0.5V、
//     ADC 下限 142mV から十分離れている）。分離比 66ms 対 1386ms は変わらない。
// ---------------------------------------------------------------------------
static const int DECAY_TAU_HI_MV = 2000;  // 下り坂で最初に切る電圧(V_pump 換算)
static const int DECAY_TAU_LO_MV = 1000;  // その半分。t_half = 両者の時刻差 = τ・ln2
// 合格帯は固定値にしない: 据付時に一度測った t_half をここに書き写す(0 = 未設定)。
//   C2 が暫定の電解 10µF で、秋月の X7S に差し替えると数字が動くため(監査 順位1)。
//   0 のあいだは判定を出さず、測った値を毎回 unknown として印字するだけにする。
// ★2026-08-25 実機で据付基準値を測定して書き写した。判定帯は ±40% で 41〜96 ms。
//   C2 を X7S に差し替えたら、必ずここを測り直して書き換えること。
static const int DECAY_TAU_BASELINE_MS = 69;
static const int DECAY_TAU_TOL_PCT     = 40;  // 基準 ±40%
static const int DECAY_TAU_MIN_MEASURABLE_MS = 5;  // これ未満はサンプリング分解能以下

// 計測の前提: ピークが DECAY_TAU_HI_MV まで届いていないと下り坂の起点が取れない。
static_assert(VPUMP_MIN_FOR_DECAY_MV >= DECAY_TAU_HI_MV,
              "VPUMP_MIN_FOR_DECAY_MV は DECAY_TAU_HI_MV 以上にすること(t_half の起点が取れない)");
static_assert(DECAY_TAU_HI_MV == DECAY_TAU_LO_MV * 2,
              "DECAY_TAU_HI_MV は DECAY_TAU_LO_MV のちょうど2倍にすること(t_half = tau*ln2 が崩れる)");

// V_pump をシリアルに定期表示する周期
static const int64_t  VPUMP_PRINT_US = 1000000;  // 1秒ごと

// ---------------------------------------------------------------------------
// SENSE 断線検出 (§7 追加 / 2026-08-23 の実機知見)
//   GPIO34 は入力専用で内部プルが無い。分圧が外れると「浮く」が、浮いたピンは
//   電荷の逃げ道が無いので、隣を走る PUMP 線からの容量結合をそのまま保持する。
//   結果、20kHz に 100% 追従する「完璧な直結」に見え、自己診断は健康を報告する。
//   → デッドマンの観測能力を潰す唯一の故障が、健康として報告される。
//
//   検出原理: PUMP を「1回だけ」立ち上げる。正しく繋がっていれば C2 が上がるのは
//     3.3V × C1/(C1+C2) = 3.3 × 100nF/10.1uF = 約33mV (V_pump 換算)
//   だけで、Vgs(th) 1.0V の 1/30 にすぎない。浮いていればレールまで飛ぶ。
// ---------------------------------------------------------------------------
#define SENSE_OPEN_DETECT 1

// 1発の立上りで V_pump がこれ以上動いたら「浮き」と判定 (正常は約33mV, 浮きは約6000mV)
static const int      SENSE_PROBE_RISE_MV = 1000;
// 探査パルスの幅(ms)。sampler は 1kHz なので数点取れれば足りる。
//   ★C1 が短絡している異常時にはこの幅だけゲートが上がる。だから最小限にする。
static const uint32_t SENSE_PROBE_MS = 3;
// 起動後の初回探査までの待ち(S0 ロックアウト内で終わらせる)
static const int64_t  SENSE_FIRST_PROBE_US = 1500LL * 1000;
// 以降の再検査周期。現地で線が緩む/腐食するのを捕まえるため(消灯中の状態でだけ実施)
static const int64_t  SENSE_RECHECK_US = 600LL * 1000000;   // 10分

// ---- デュアルコア配置(設計判断。詳細は FIX-NOTES.md §デュアルコア) ----
//   Core1(APP_CPU): guardian = 受理判定 + PUMP を同一ループで(§5.4 単一ループ不変条件)
//   Core0(PRO_CPU): BLE(既定) + sampler = ADC を占有し V_pump を公開/ハング時の減衰を捕捉
static const int GUARDIAN_CORE = 1;
static const int SAMPLER_CORE  = 0;
static const int GUARDIAN_PRIO = 10;   // loopTask(1)/IDLE(0) より高い
static const int SAMPLER_PRIO  = 2;    // BLE より低く、邪魔しない
static const uint32_t SAMPLER_PERIOD_MS = 1;    // ~1kHz サンプリング
static const uint32_t HANG_DETECT_MS = 100;     // heartbeat がこの時間止まったらハングとみなす
