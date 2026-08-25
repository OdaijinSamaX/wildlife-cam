// ============================================================================
// wildlife-cam γ版 箱B  受信ファーム  (ESP32-WROOM-32E / Freenove ボード)
//
// 今回の版: PUMP を「実駆動」にした(デッドマン回路の本体)。
//   - PUMP を CPU が自分の足で叩く 20kHz 矩形波に(LEDC/RMT/タイマ ISR は使わない)
//   - SENSE(GPIO34)で C2 電圧を読み、実 V_pump を定期表示
//   - ベンチ試験コマンド(p/o/h/s)で Pi なしでも Phase 2 を実施可能
//   - 減衰時間を ESP32 自身が計測(通常OFFは core1、ハング時は core0 sampler)
//
//   デュアルコア配置(設計判断。詳細は FIX-NOTES.md):
//     Core1(APP_CPU): guardian = 受理判定(§4.3) + 状態機械(§5.1) + PUMP 駆動 を
//                     「同一ループ」で回す(§5.4 単一ループ不変条件)。ここが固まれば
//                     PUMP のトグルも止まる → デッドマン成立。
//     Core0(PRO_CPU): BLE(既定) + sampler = ADC を占有して V_pump を公開し、
//                     guardian ハング時も生き残って減衰カーブを捕捉する。
//
//   実装済みの設計書項目: §4.1 解釈 / §4.3 受理規約 / §5.1 状態機械 /
//     §5.2 デッドマン(実駆動) / §5.5 減衰計測 / scan の3点指定(passive/白/重複無効)
//
//   開発環境: Arduino-ESP32(生の esp_bt_* / esp_ble_gap_* を直叩き)。README 参照。
// ============================================================================

#include <string.h>
#include "config.h"

#include "nvs_flash.h"
#include "esp_timer.h"
#include "esp_task_wdt.h"
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_ble_api.h"
#include "mbedtls/md.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"

// ---------------------------------------------------------------------------
// 状態機械 (設計書 §5.1)
// ---------------------------------------------------------------------------
enum State {
  S0_RESET_LOCKOUT, S1_BOOTSTRAP, S2_IDLE_LOW, S3_IDLE_HIGH, S4_BOOST,
  S5_LIT, S6_COOLDOWN, S7_ORPHAN, S8_SELFTEST, S9_RESET_STORM
};
static const char* STATE_NAME[] = {
  "S0_RESET_LOCKOUT","S1_BOOTSTRAP","S2_IDLE_LOW","S3_IDLE_HIGH","S4_BOOST",
  "S5_LIT","S6_COOLDOWN","S7_ORPHAN","S8_SELFTEST","S9_RESET_STORM"
};

// ---------------------------------------------------------------------------
// 受信フレームを GAP コールバック → guardian へ渡すキュー。
//   ★安全ロジック(受理規約・状態機械・PUMP 判定)は §5.4 の教義に従い
//     「すべて guardian の同一ループ内」で行う。コールバックは生データを積むだけ。
// ---------------------------------------------------------------------------
typedef struct {
  uint8_t data[PAYLOAD_LEN];
  int     rssi;
  uint8_t evt_type;
} raw_frame_t;
static QueueHandle_t g_frame_q = nullptr;

// ---------------------------------------------------------------------------
// guardian(core1)だけが触る状態変数(→ ロック不要)
// ---------------------------------------------------------------------------
static State    state = S0_RESET_LOCKOUT;
static bool     have_epoch = false;
static uint16_t cur_epoch = 0;
static uint32_t last_seq = 0;
static uint32_t last_accepted_cmd_seq = 0;  // §4.3-6 受理したものだけ
static int      bootstrap_count = 0;

static bool     ir_should_be_on = false;
static int64_t  boot_lockout_until_us = 0;
static int64_t  last_valid_on_us = 0;       // ★デッドマンの鮮度基準 §4.3-5
static int64_t  lit_start_us   = 0;
static int64_t  boost_start_us = 0;
static int64_t  cooldown_start_us = 0;
static int64_t  last_cmd_us    = 0;
static int64_t  last_beaconA_us = 0, last_beaconB_us = 0;
static int64_t  prev_loop_us = 0;

// ---- ランプの実態 (2026-08-25 / 監査 順位2) --------------------------------
//   T_cap 45秒とデューティ計上の起点を「状態機械の考え」から「PUMP 出力の実態」へ移す。
//   旧: 状態機械が一度でも OFF を通ると lit_start_us が書き直されたので、
//       OFF → 100ms 後に ON を繰り返すと、ランプは一度も消えないのに 45秒の時計だけが
//       ゼロに戻り続けた(BLE 広告間隔 100ms 固定 < 実測の消灯 151ms)。
//   新: PUMP 出力が「連続 LAMP_COOL_US(500ms)低かったとき」だけ起点をクリアする。
static int64_t  lamp_hot_since_us = 0;   // 0 = ランプは冷えている。非0 = その時刻から熱い
static int64_t  lamp_low_since_us = 0;   // 0 = 現在 PUMP は High。非0 = Low になった時刻
static bool     g_within_cap = true;     // T_cap 45秒の内側か(guardian がベンチ強制ONにも効かせる)

// ---- デューティ: 10秒 x 60個のスライド窓 (2026-08-25 / 監査 順位2) ----------
//   旧: 10分ごとに accum を丸ごとゼロクリア → 窓の後半5分＋次の窓の前半5分＝
//       連続10分が正規に通っていた。計上も「ON 指令が出ている時間」だけだったので
//       交互点滅では実点灯の半分しか数えていなかった。
static uint16_t duty_ring_ms[DUTY_RING_N];   // 各バケツの「ランプが熱かった」ms (120 バイト)
static int      duty_ring_idx = 0;
static int64_t  duty_bucket_start_us = 0;
static int64_t  duty_frac_us = 0;            // 1ms に満たない端数の持ち越し
static bool     duty_limited = false;

// PUMP / bench / 減衰
static bool     g_sm_pump_ok = false;       // 状態機械が「点けてよい」と判断したか
static bool     bench_force_on = false;     // 'p' による強制ON
static int64_t  bench_force_until = 0;
static volatile bool g_hang_request = false;// 'h' によるハング模擬要求
static bool     prev_pump = false;
static bool     decay_active = false;
static int64_t  decay_start_us = 0;
// t_half 計測用 (2026-08-25 / 監査 順位1)
static int64_t  decay_hi_us = 0;        // DECAY_TAU_HI_MV を切った時刻
static int64_t  decay_lo_us = 0;        // DECAY_TAU_LO_MV(= hi の半分)を切った時刻
static bool     decay_thresh_done = false;
static int      decay_peak_mv = 0;

// SENSE 断線検出(§7 追加 / 2026-08-23)。真の間、SENSE 由来の診断は「不明」に倒す。
static bool     g_sense_open = false;        // 直近の探査で「浮き」と出たか
static bool     sense_ever_probed = false;   // 未探査を健康と誤読させないための旗
static int64_t  sense_next_probe_us = 0;
static int      sense_last_rise_mv = 0;

// コア間共有(volatile)
static volatile int      g_vpump_mv  = 0;   // sampler(core0)が更新、guardian が参照
static volatile uint32_t g_heartbeat = 0;   // guardian が毎ループ++、sampler が監視

// fault カウンタ(§4.2)
static uint32_t cnt_bad_mac = 0, cnt_seq_regress = 0, cnt_orphan = 0, boot_count = 0;
static uint32_t cnt_sense_open = 0;
static uint32_t cnt_decay_skipped = 0;  // 減衰計測を走らせられなかった回数(§8.2 unknown)   // SENSE 断線を検出した回数(§7)
// ---- 2026-08-25 追加のカウンタ(監査 順位1 / 順位2) ----
static uint32_t cnt_tcap_hit   = 0;     // ランプ実点灯が 45秒に達した回数
static uint32_t cnt_duty_limit = 0;     // スライド窓のデューティ上限に達した回数
static uint32_t cnt_tau_ok = 0, cnt_tau_ng = 0, cnt_tau_unknown = 0;
static int      last_tau_half_ms = -1;  // 直近の t_half(ms)。-1 = まだ無い

// 鍵が公開テスト鍵のままなら、13日ぶんのログの毎行に痕跡を残す(監査 順位2(b))。
// ★鍵の値そのものは絶対に出力しない。
#if HMAC_KEY_IS_PLACEHOLDER
#define KEY_WARN_SUFFIX "  ★HMAC鍵=公開テスト鍵のまま(無人運用に投入禁止)"
#else
#define KEY_WARN_SUFFIX ""
#endif

// ===========================================================================
// 広告データから Manufacturer Specific Data(AD type 0xFF)を探す(版非依存)
// ===========================================================================
static const uint8_t* find_mfg(const uint8_t* adv, uint8_t adv_len, uint8_t* out_len) {
  uint8_t i = 0;
  while (i < adv_len) {
    uint8_t len = adv[i];
    if (len == 0) break;
    if ((uint16_t)i + 1 + len > adv_len) break;
    uint8_t type = adv[i + 1];
    if (type == 0xFF) { *out_len = len - 1; return &adv[i + 2]; }
    i += len + 1;
  }
  return nullptr;
}

// ===========================================================================
// HMAC-SHA256 の先頭8バイトを検証(設計書 §4.1)
// ===========================================================================
static bool hmac8_ok(const uint8_t* msg, size_t msg_len, const uint8_t* mac8) {
  uint8_t out[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (!info) return false;
  mbedtls_md_context_t ctx;
  mbedtls_md_init(&ctx);
  bool ok = false;
  if (mbedtls_md_setup(&ctx, info, 1 /*HMAC*/) == 0 &&
      mbedtls_md_hmac_starts(&ctx, HMAC_KEY, HMAC_KEY_LEN) == 0 &&
      mbedtls_md_hmac_update(&ctx, msg, msg_len) == 0 &&
      mbedtls_md_hmac_finish(&ctx, out) == 0) {
    uint8_t diff = 0;
    for (int i = 0; i < 8; i++) diff |= (out[i] ^ mac8[i]);
    ok = (diff == 0);
  }
  mbedtls_md_free(&ctx);
  return ok;
}

static inline uint16_t rd_u16(const uint8_t* p) { return (uint16_t)p[0] | ((uint16_t)p[1] << 8); }
static inline uint32_t rd_u32(const uint8_t* p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void go(State s, const char* why) {
  if (s != state) {
    Serial.printf(">>> 状態遷移 %s → %s  (%s)\n", STATE_NAME[state], STATE_NAME[s], why);
    state = s;
  }
}

// ===========================================================================
// 1フレームを受理規約(§4.3)にかけて状態を更新する。★心臓部(rule 5)。
// ===========================================================================
static void process_frame(const raw_frame_t* f, int64_t now) {
  const uint8_t* d = f->data;

  if (rd_u16(d) != COMPANY_ID) return;
  if (d[2] != PROTO_VER)       return;
  if (d[3] != TYPE_CMD)        return;

  uint8_t link_id = d[4];
  if (link_id != LINK_ID) return;                    // rule 1

  uint16_t epoch    = rd_u16(&d[5]);
  uint32_t seq      = rd_u32(&d[7]);
  uint8_t  want     = d[11];
  uint8_t  ttl_ds   = d[12];
  uint8_t  flags    = d[13];
  uint8_t  duty_hint= d[14];
  (void)ttl_ds; (void)flags;

#if REQUIRE_HMAC
  if (!hmac8_ok(&d[HMAC_MSG_OFF], HMAC_MSG_LEN, &d[HMAC_OFF])) {   // rule 2
    cnt_bad_mac++;
    Serial.printf("[破棄] HMAC 不一致 (bad_mac=%u) seq=%u\n", cnt_bad_mac, seq);
    return;
  }
#endif

  if (!have_epoch || epoch > cur_epoch) {             // rule 3
    Serial.printf("[epoch] %s epoch=%u → BOOTSTRAP やり直し\n",
                  have_epoch ? "epoch 増加:" : "初回:", epoch);
    have_epoch = true; cur_epoch = epoch; last_seq = seq;
    bootstrap_count = 1; last_cmd_us = now;
    go(S1_BOOTSTRAP, "epoch 変化");
    return;
  }
  if (epoch < cur_epoch) { Serial.printf("[破棄] 古い epoch=%u < %u\n", epoch, cur_epoch); return; }

  if (seq <= last_seq) {                              // rule 4 ★同一seq再受信を弾く
    cnt_seq_regress++;
    Serial.printf("[破棄] seq 後退/据置き seq=%u <= last=%u (seq_regress=%u)\n",
                  seq, last_seq, cnt_seq_regress);
    return;
  }

  // ---- ここから下は「seq が厳密に増加した受理フレーム」のみ ----
  last_seq = seq;
  last_accepted_cmd_seq = seq;   // rule 6
  last_cmd_us = now;

  if (state == S7_ORPHAN) { go(S1_BOOTSTRAP, "ORPHAN 中に CMD 受理"); bootstrap_count = 1; return; }

  if (state == S1_BOOTSTRAP) {
    bootstrap_count++;
    Serial.printf("[bootstrap] 連続増加 %d/2  seq=%u\n", bootstrap_count, seq);
    if (bootstrap_count >= 2) go((duty_hint >= DUTY_HIGH) ? S3_IDLE_HIGH : S2_IDLE_LOW, "bootstrap 完了");
    return;
  }

  if (state == S2_IDLE_LOW && duty_hint >= DUTY_HIGH) go(S3_IDLE_HIGH, "duty_hint=HIGH");
  if (state == S3_IDLE_HIGH && duty_hint == DUTY_LOW && !ir_should_be_on) go(S2_IDLE_LOW, "duty_hint=LOW");

  bool locked_out = (now - boot_lockout_until_us) < 0;

  switch (want) {
    case WANT_OFF:
      if (ir_should_be_on) Serial.printf("[CMD] OFF 受理 seq=%u\n", seq);
      ir_should_be_on = false;
      if (state == S5_LIT) go(S3_IDLE_HIGH, "OFF 受理");
      break;
    case WANT_PREARM:
      if (state == S3_IDLE_HIGH) { boost_start_us = now; go(S4_BOOST, "PREARM 受理"); }
      Serial.printf("[CMD] PREARM 受理 seq=%u\n", seq);
      break;
    case WANT_ON:
      if (locked_out)              { Serial.println("[CMD] ON 拒否: 起動ロックアウト中"); break; }
      if (state == S6_COOLDOWN)    { Serial.println("[CMD] ON 拒否: COOLDOWN 中"); break; }
      if (state == S9_RESET_STORM) { Serial.println("[CMD] ON 拒否: RESET_STORM 中"); break; }
      if (duty_limited)            { Serial.println("[CMD] ON 拒否: デューティ上限"); break; }
      if (state == S4_BOOST || state == S3_IDLE_HIGH || state == S2_IDLE_LOW) {
        if (state != S5_LIT) lit_start_us = now;
        go(S5_LIT, (state == S4_BOOST) ? "ON 受理(正規)" : "ON 受理(PREARM取り逃し)");
      }
      if (state == S5_LIT) {
        ir_should_be_on = true;
        last_valid_on_us = now;   // ★ rule 5: 厳密増加のときだけ鮮度更新
        Serial.printf("[CMD] ON 受理 seq=%u → 鮮度更新\n", seq);
      }
      break;
    default:
      Serial.printf("[破棄] 未知の want=0x%02X\n", want);
      break;
  }
}

// ===========================================================================
// ランプの実態を追う (2026-08-25 / 監査 順位2)
//   guardian が実際に PUMP を駆動したか(pump_now)だけを見る。状態機械の意見は見ない。
//   ★guardian の同一ループから毎回呼ぶこと(§5.4)。
// ===========================================================================
static void lamp_track(int64_t now, bool pump_on) {
  if (pump_on) {
    lamp_low_since_us = 0;
    if (lamp_hot_since_us == 0) lamp_hot_since_us = now;   // 冷えていたなら、ここが起点
    return;
  }
  if (lamp_low_since_us == 0) lamp_low_since_us = now;     // Low に落ちた時刻を控える
  if (lamp_hot_since_us != 0 && (now - lamp_low_since_us) >= LAMP_COOL_US) {
    Serial.printf("[lamp] PUMP が連続 %lldms Low → ランプは冷えたと判定(実点灯 %d ms で終了)\n",
                  LAMP_COOL_US / 1000, (int)((lamp_low_since_us - lamp_hot_since_us) / 1000));
    lamp_hot_since_us = 0;
  }
}

// ===========================================================================
// 時間切れ判定 + デッドマン判定。★PUMP を回してよいかを g_sm_pump_ok に入れる。
//   (実際のトグルは guardian が同一ループで行う = §5.4)
// ===========================================================================
static void service_state(int64_t now) {
  int64_t dt = now - prev_loop_us;
  if (dt < 0) dt = 0;
  prev_loop_us = now;

  // ---- デューティ: 10秒バケツ x 60 のスライド窓(監査 順位2) ----
  //   計上の基準は ON 指令ではなく lamp_hot_since_us(ランプの実態)。
  int64_t bucket_gap = now - duty_bucket_start_us;
  if (bucket_gap >= DUTY_BUCKET_US) {
    int64_t steps64 = bucket_gap / DUTY_BUCKET_US;
    int steps = (steps64 > (int64_t)DUTY_RING_N) ? DUTY_RING_N : (int)steps64;
    for (int i = 0; i < steps; i++) {
      duty_ring_idx = (duty_ring_idx + 1) % DUTY_RING_N;
      duty_ring_ms[duty_ring_idx] = 0;          // 一番古いバケツを捨てる = 窓がずれる
    }
    duty_bucket_start_us += steps64 * DUTY_BUCKET_US;
  }
  if (lamp_hot_since_us != 0) {                 // ★指令ではなくランプが熱い時間を数える
    duty_frac_us += dt;
    if (duty_frac_us >= 1000) {
      uint32_t add_ms = (uint32_t)(duty_frac_us / 1000);
      duty_frac_us -= (int64_t)add_ms * 1000;
      uint32_t v = (uint32_t)duty_ring_ms[duty_ring_idx] + add_ms;
      duty_ring_ms[duty_ring_idx] = (uint16_t)(v > 65535u ? 65535u : v);
    }
  }
  uint32_t duty_sum_ms = 0;
  for (int i = 0; i < DUTY_RING_N; i++) duty_sum_ms += duty_ring_ms[i];
  if (!duty_limited && duty_sum_ms >= DUTY_BUDGET_MS) {
    duty_limited = true; cnt_duty_limit++;
    Serial.printf("[duty] 直近600秒の実点灯 %u ms が上限 %u ms に到達 → 制限(通算 %u 回)\n",
                  duty_sum_ms, DUTY_BUDGET_MS, cnt_duty_limit);
  } else if (duty_limited && duty_sum_ms < DUTY_RELEASE_MS) {
    duty_limited = false;
    Serial.printf("[duty] 直近600秒の実点灯が %u ms まで低下 → 制限解除\n", duty_sum_ms);
  }

  // ★T_cap の起点はランプの実態(監査 順位2)。状態機械が OFF を通っても、PUMP が
  //   連続 500ms 低くならない限り lamp_hot_since_us は書き直されない。
  //   (lit_start_us は「状態機械が点灯を決めた時刻」として残してあるが、
  //    T_cap の判定にはもう使わない。旧版との差分を読むときの目印として置いてある)
  //   ★S0 の早期 return より前に確定させる: 45秒は「どの経路が点けたか」に関係なく
  //     ランプの実態に対する絶対上限なので、ベンチ強制ONにも guardian 側で効かせる。
  bool within_cap = (lamp_hot_since_us == 0) || ((now - lamp_hot_since_us) < TCAP_US);
  g_within_cap = within_cap;

  bool locked_out = now < boot_lockout_until_us;
  if (state == S0_RESET_LOCKOUT) {
    g_sm_pump_ok = false;                 // S0: PUMP 強制Low
    if (!locked_out) go(S1_BOOTSTRAP, "ロックアウト満了");
    return;
  }

  int64_t hold_us = (state == S5_LIT) ? LIT_HOLD_US : IDLE_HOLD_US;
  bool cmd_fresh  = (now - last_valid_on_us) < hold_us;

  bool want_pump = (!locked_out && ir_should_be_on && cmd_fresh && within_cap && !duty_limited);

  static bool prev_ok = false;
  if (want_pump != prev_ok) {
    if (want_pump) Serial.println("[deadman] 条件成立 → PUMP ON(20kHz)");
    else {
      const char* why = locked_out ? "ロックアウト" :
                        !ir_should_be_on ? "ON 指令なし" :
                        !cmd_fresh ? "鮮度切れ(リンク断/Pi死)" :
                        !within_cap ? "T_cap 45秒到達(ランプ実点灯基準)" : "デューティ上限";
      Serial.printf("[deadman] PUMP OFF (%s)\n", why);
    }
    prev_ok = want_pump;
  }
  g_sm_pump_ok = want_pump;

  // 計上そのものは上のスライド窓で済んでいる。ここは上限に触れたときの遷移だけ。
  if (duty_limited && ir_should_be_on) {
    ir_should_be_on = false; cooldown_start_us = now;
    go(S6_COOLDOWN, "デューティ上限(600秒スライド窓で5分)超過");
  }

  switch (state) {
    case S4_BOOST:
      if (now - boost_start_us > BOOST_MAX_US) go(S3_IDLE_HIGH, "BOOST 8秒経過");
      break;
    case S5_LIT:
      if (!within_cap) {
        cnt_tcap_hit++;
        Serial.printf("[T_cap] ランプ実点灯が %d ms 連続 → 45秒上限で強制消灯(通算 %u 回)\n",
                      (int)((now - lamp_hot_since_us) / 1000), cnt_tcap_hit);
        ir_should_be_on = false; cooldown_start_us = now;
        go(S6_COOLDOWN, "T_cap 45秒(ランプ実点灯基準)");
      }
      else if (!cmd_fresh) { ir_should_be_on = false; go(S3_IDLE_HIGH, "HOLD 満了(鮮度切れ)"); }
      break;
    case S6_COOLDOWN:
      if (now - cooldown_start_us > COOLDOWN_US) go(S3_IDLE_HIGH, "COOLDOWN 満了");
      break;
    default: break;
  }

  if (state == S2_IDLE_LOW || state == S3_IDLE_HIGH) {
    if (have_epoch && (now - last_cmd_us > ORPHAN_US)) { cnt_orphan++; go(S7_ORPHAN, "600秒 CMD 無し"); }
  }

  if (now - last_beaconA_us >= BEACON_A_US) {
    last_beaconA_us = now;
    Serial.printf("[beaconA] state=%s ir_gate=%d last_cmd_seq=%u fault{bad_mac=%u,seq_regress=%u,orphan=%u,sense_open=%u}%s\n",
                  STATE_NAME[state], ir_should_be_on ? 1 : 0, last_accepted_cmd_seq,
                  cnt_bad_mac, cnt_seq_regress, cnt_orphan, cnt_sense_open,
                  g_sense_open ? "  ★SENSE 断線中: V_pump と減衰は測定不能" : "");
  }
  if (now - last_beaconB_us >= BEACON_B_US) {
    last_beaconB_us = now;
    if (g_sense_open || !sense_ever_probed)
      Serial.printf("[beaconB] uptime=%llds boot_count=%u V_pump=unknown(%s)\n",
                    now / 1000000, boot_count, g_sense_open ? "SENSE 断線" : "未探査");
    else
      Serial.printf("[beaconB] uptime=%llds boot_count=%u V_pump=%dmV (vbat/shunt は未接続)\n",
                    now / 1000000, boot_count, g_vpump_mv);
    // ★2026-08-25 追加: 13日ぶんのログを1行 grep すれば直ったか分かるようにする。
    uint32_t duty_sum_b = 0;
    for (int i = 0; i < DUTY_RING_N; i++) duty_sum_b += duty_ring_ms[i];
    Serial.printf("[beaconB] lamp_hot=%dms duty600=%u/%ums%s tcap_hit=%u duty_limit=%u"
                  " tau{last=%dms,ok=%u,ng=%u,unknown=%u} decay_skip=%u" KEY_WARN_SUFFIX "\n",
                  lamp_hot_since_us ? (int)((now - lamp_hot_since_us) / 1000) : 0,
                  duty_sum_b, DUTY_BUDGET_MS, duty_limited ? "(制限中)" : "",
                  cnt_tcap_hit, cnt_duty_limit,
                  last_tau_half_ms, cnt_tau_ok, cnt_tau_ng, cnt_tau_unknown,
                  cnt_decay_skipped);
  }
}

// ===========================================================================
// PUMP 実駆動: CPU が自分の足で 20kHz を叩く。★LEDC/RMT/タイマ ISR は使わない。
//   これで CPU(=このループ)が止まればトグルも止まり、C2 が放電して IR 消灯。
// ===========================================================================
static inline void pump_line_low() { digitalWrite(PIN_PUMP, LOW); }

static void pump_burst(uint32_t burst_us) {
  int64_t t_end = esp_timer_get_time() + (int64_t)burst_us;
  while (esp_timer_get_time() < t_end) {
    digitalWrite(PIN_PUMP, HIGH);
    delayMicroseconds(PUMP_HALF_US);
    digitalWrite(PIN_PUMP, LOW);
    delayMicroseconds(PUMP_HALF_US);
  }
  digitalWrite(PIN_PUMP, LOW);   // 必ず Low で抜ける
}

// ===========================================================================
// シリアル1文字コマンド(ベンチ試験)
// ===========================================================================
static void print_status() {
  int64_t now = esp_timer_get_time();
  Serial.println("---- STATUS ----");
  if (g_sense_open || !sense_ever_probed)
    Serial.printf(" state=%s  ir_gate=%d  V_pump=unknown (%s)\n", STATE_NAME[state],
                  ir_should_be_on ? 1 : 0, g_sense_open ? "SENSE 断線" : "未探査");
  else
    Serial.printf(" state=%s  ir_gate=%d  V_pump=%d mV\n", STATE_NAME[state], ir_should_be_on ? 1 : 0, g_vpump_mv);
  Serial.printf(" sense_open=%d (検出%u回 / 直近の1発エッジ応答 %d mV / 閾値 %d mV)\n",
                g_sense_open ? 1 : 0, cnt_sense_open, sense_last_rise_mv, SENSE_PROBE_RISE_MV);
  Serial.printf(" last_cmd_seq=%u  bad_mac=%u seq_regress=%u orphan=%u\n",
                last_accepted_cmd_seq, cnt_bad_mac, cnt_seq_regress, cnt_orphan);
  Serial.printf(" heartbeat=%u  uptime=%llds  bench_force_on=%d\n",
                g_heartbeat, now / 1000000, bench_force_on ? 1 : 0);
  // ---- 2026-08-25 追加(監査 順位1/2) ----
  uint32_t duty_sum_s = 0;
  for (int i = 0; i < DUTY_RING_N; i++) duty_sum_s += duty_ring_ms[i];
  if (lamp_hot_since_us)
    Serial.printf(" lamp_hot=%d ms (T_cap 残り %d ms)\n",
                  (int)((now - lamp_hot_since_us) / 1000),
                  (int)((TCAP_US - (now - lamp_hot_since_us)) / 1000));
  else
    Serial.println(" lamp_hot=0 ms (ランプは冷えている)");
  Serial.printf(" duty(直近600秒)=%u/%u ms %s  tcap_hit=%u duty_limit=%u\n",
                duty_sum_s, DUTY_BUDGET_MS, duty_limited ? "★制限中" : "", cnt_tcap_hit, cnt_duty_limit);
  Serial.printf(" tau: last=%d ms  ok=%u ng=%u unknown=%u  基準=%d ms ±%d%% (%d→%dmV)\n",
                last_tau_half_ms, cnt_tau_ok, cnt_tau_ng, cnt_tau_unknown,
                DECAY_TAU_BASELINE_MS, DECAY_TAU_TOL_PCT, DECAY_TAU_HI_MV, DECAY_TAU_LO_MV);
#if HMAC_KEY_IS_PLACEHOLDER
  Serial.println(" ★HMAC 鍵が公開テスト鍵のままです(無人運用に投入禁止)");
#else
  Serial.println(" HMAC 鍵: 本番鍵(値は表示しない)");
#endif
  Serial.println("----------------");
}

static void handle_serial() {
  while (Serial.available() > 0) {
    int c = Serial.read();
    switch (c) {
      case 'p':
        bench_force_on = true;
        bench_force_until = esp_timer_get_time() + (int64_t)BENCH_FORCE_ON_MS * 1000;
        Serial.printf("★[BENCH] PUMP 強制ON %ums(状態機械の許可なしで駆動)。V_pump 測定用\n", BENCH_FORCE_ON_MS);
        break;
      case 'o':
        bench_force_on = false;
        ir_should_be_on = false;
        if (state == S5_LIT) go(S3_IDLE_HIGH, "bench OFF");
        Serial.println("[BENCH] PUMP 強制OFF");
        break;
#if BENCH_MODE
      case 'h':
        g_hang_request = true;
        Serial.println("★[BENCH] 次イテレーションでハングを模擬します(while(1))");
        break;
#endif
      case 's': print_status(); break;
      case '\r': case '\n': case ' ': break;
      default:
        Serial.printf("[BENCH] キー: p=強制ON  o=強制OFF  s=状態"
#if BENCH_MODE
                      "  h=ハング模擬"
#endif
                      "\n");
        break;
    }
  }
}

// ===========================================================================
// GAP コールバック / scan パラメータ / BLE 初期化(前回の 0x103 対策込み)
// ===========================================================================
static esp_ble_scan_params_t scan_params = {
  .scan_type          = BLE_SCAN_TYPE_PASSIVE,             // ★passive scan
  .own_addr_type      = BLE_ADDR_TYPE_PUBLIC,
#if USE_WHITELIST
  .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ONLY_WLST,   // ★白リストのみ受理
#else
  .scan_filter_policy = BLE_SCAN_FILTER_ALLOW_ALL,         // 動作確認: link_id+HMAC で絞る
#endif
  .scan_interval      = SCAN_ITVL,
  .scan_window        = SCAN_WIN,
  .scan_duplicate     = BLE_SCAN_DUPLICATE_DISABLE,        // ★重複排除を必ず無効(§6.8/U2)
};

static void gap_cb(esp_gap_ble_cb_event_t event, esp_ble_gap_cb_param_t* param) {
  switch (event) {
    case ESP_GAP_BLE_SCAN_PARAM_SET_COMPLETE_EVT:
      Serial.println("[BLE] scan パラメータ設定完了 → scan 開始");
      esp_ble_gap_start_scanning(0);
      break;
    case ESP_GAP_BLE_SCAN_START_COMPLETE_EVT:
      if (param->scan_start_cmpl.status != ESP_BT_STATUS_SUCCESS)
        Serial.printf("[BLE] scan 開始失敗 status=%d\n", param->scan_start_cmpl.status);
      else
        Serial.println("[BLE] scan 開始成功。Pi の広告受信待ち…");
      break;
    case ESP_GAP_BLE_SCAN_RESULT_EVT: {
      auto* r = &param->scan_rst;
      if (r->search_evt != ESP_GAP_SEARCH_INQ_RES_EVT) break;
      uint8_t mfg_len = 0;
      const uint8_t* mfg = find_mfg(r->ble_adv, r->adv_data_len, &mfg_len);
      if (!mfg || mfg_len < PAYLOAD_LEN) break;
      raw_frame_t f;
      memcpy(f.data, mfg, PAYLOAD_LEN);
      f.rssi = r->rssi;
      f.evt_type = r->ble_evt_type;
      if (g_frame_q) xQueueSend(g_frame_q, &f, 0);
      break;
    }
    default: break;
  }
}

// ★0x103 対策(FIX-NOTES.md 参照): コアの起動時 BLE メモリ解放を止める上書きフック
extern "C" bool bleInUse(void) { return true; }

static void ble_init() {
  esp_bt_controller_mem_release(ESP_BT_MODE_CLASSIC_BT);   // classic は解放(BLE専用)。戻り値無視
  esp_bt_controller_config_t cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  // ★必須(FIX-NOTES 罠2)。既定は mode=3(BTDM) なので、enable(ESP_BT_MODE_BLE) と
  //   不一致になり esp_bt_controller_enable が 0x102 を返す。消すと BLE が起動しない。
  cfg.mode = ESP_BT_MODE_BLE;
  esp_err_t e;
  if ((e = esp_bt_controller_init(&cfg)) != ESP_OK) {
    Serial.printf("[BLE] controller_init 失敗 0x%X (status=%d)\n", e, esp_bt_controller_get_status());
    return;
  }
  if ((e = esp_bt_controller_enable(ESP_BT_MODE_BLE)) != ESP_OK) { Serial.printf("[BLE] enable 失敗 0x%X\n", e); return; }
  if ((e = esp_bluedroid_init()) != ESP_OK)   { Serial.printf("[BLE] bluedroid_init 失敗 0x%X\n", e); return; }
  if ((e = esp_bluedroid_enable()) != ESP_OK) { Serial.printf("[BLE] bluedroid_enable 失敗 0x%X\n", e); return; }
  if ((e = esp_ble_gap_register_callback(gap_cb)) != ESP_OK) { Serial.printf("[BLE] gap_register 失敗 0x%X\n", e); return; }

#if USE_WHITELIST
  esp_bd_addr_t peer; memcpy(peer, PEER_ADDR, 6);
  esp_ble_gap_update_whitelist(true, peer, BLE_WL_ADDR_TYPE_RANDOM);
  Serial.println("[BLE] 白リストに Pi アドレスを登録");
#endif

  if ((e = esp_ble_gap_set_scan_params(&scan_params)) != ESP_OK) { Serial.printf("[BLE] set_scan_params 失敗 0x%X\n", e); return; }
  Serial.println("[BLE] コントローラ/host 初期化 OK。scan パラメータ設定待ち…");
}

// ===========================================================================
// 減衰の合否を「時定数 τ」で判定する (2026-08-25 / 監査 順位1)
//
//   t_half = V_pump が DECAY_TAU_HI_MV を切った時刻と、その半分の DECAY_TAU_LO_MV を
//   切った時刻の差。t_half = τ・ln2 で、ピーク電圧に一切依存しない。
//     健康(R_pd 10k 込み)        → 約 66 ms
//     R_pd / ゲート脚が外れた    → 約 1386 ms   ← 21倍離れるので閾値に悩まない
//   合格帯は固定値ではなく「据付時に一度測った値 ±DECAY_TAU_TOL_PCT%」。
//   基準が未設定(=0)のあいだは ok とも urgent とも言わず unknown を出す。
// ===========================================================================
static void report_tau(int t_half_ms, int peak_mv, const char* src) {
  last_tau_half_ms = t_half_ms;

  if (t_half_ms < DECAY_TAU_MIN_MEASURABLE_MS) {
    cnt_tau_unknown++;
    Serial.printf("[減衰tau] %s t_half=%d ms → unknown(サンプリング分解能以下) peak=%d mV\n",
                  src, t_half_ms, peak_mv);
    return;
  }
  if (DECAY_TAU_BASELINE_MS <= 0) {
    cnt_tau_unknown++;
    Serial.printf("[減衰tau] %s t_half=%d ms (%d→%d mV) peak=%d mV 判定=unknown(基準未設定)\n",
                  src, t_half_ms, DECAY_TAU_HI_MV, DECAY_TAU_LO_MV, peak_mv);
    Serial.printf("          → 据付時の値です。config.h の DECAY_TAU_BASELINE_MS に %d を書き写して焼き直してください。\n",
                  t_half_ms);
    return;
  }
  int lo = DECAY_TAU_BASELINE_MS * (100 - DECAY_TAU_TOL_PCT) / 100;
  int hi = DECAY_TAU_BASELINE_MS * (100 + DECAY_TAU_TOL_PCT) / 100;
  if (t_half_ms >= lo && t_half_ms <= hi) {
    cnt_tau_ok++;
    Serial.printf("[減衰tau] %s t_half=%d ms 判定=ok (基準 %d ms ±%d%% = %d〜%d ms) peak=%d mV\n",
                  src, t_half_ms, DECAY_TAU_BASELINE_MS, DECAY_TAU_TOL_PCT, lo, hi, peak_mv);
  } else {
    cnt_tau_ng++;
    Serial.printf("[減衰tau] %s t_half=%d ms 判定=NG(%s) (基準 %d ms ±%d%% = %d〜%d ms) peak=%d mV\n",
                  src, t_half_ms,
                  (t_half_ms > hi) ? "遅い: R_pd かゲート脚が外れた疑い"
                                   : "速い: C2 の容量抜け/短絡の疑い",
                  DECAY_TAU_BASELINE_MS, DECAY_TAU_TOL_PCT, lo, hi, peak_mv);
  }
}

// ===========================================================================
// sampler_task (Core0): ADC を占有して V_pump を公開。guardian ハング時は
//   生き残って減衰カーブをリングバッファ+ライブで捕捉する(§5.5 / dispatch 要件5)。
// ===========================================================================
#define RB_N 256
static uint32_t rb_t_ms[RB_N];
static uint16_t rb_v_mv[RB_N];
static int      rb_head = 0;
static bool     rb_full = false;

static void report_hang_decay(uint32_t freeze_ms) {
  Serial.println("\n★[BENCH] ハング検知(guardian の heartbeat 停止)。core0 sampler が減衰を計測:");
  int n = rb_full ? RB_N : rb_head;
  uint32_t cross_ms = 0, tau_hi_ms = 0, tau_lo_ms = 0; int peak = 0;
  for (int i = 0; i < n; i++) {                     // 1) 履歴を時系列に走査
    int idx = (rb_head - n + i + RB_N) % RB_N;
    if (rb_t_ms[idx] >= freeze_ms) {
      if (rb_v_mv[idx] > peak) peak = rb_v_mv[idx];
      if (cross_ms == 0 && rb_v_mv[idx] < DECAY_THRESH_MV) cross_ms = rb_t_ms[idx];
      // ★t_half 用の2点(監査 順位1)。hi を取った次のサンプル以降でしか lo を取らない。
      if (tau_hi_ms == 0) { if (rb_v_mv[idx] < DECAY_TAU_HI_MV) tau_hi_ms = rb_t_ms[idx]; }
      else if (tau_lo_ms == 0 && rb_v_mv[idx] < DECAY_TAU_LO_MV) tau_lo_ms = rb_t_ms[idx];
    }
  }
  int64_t t0 = esp_timer_get_time();               // 2) 履歴で未クロスならライブで待つ
  //   ★lo(1000mV)は消灯閾値(1300mV)より下なので、cross で抜けずに lo まで待つ。
  //     R_pd が外れた最悪ケース(τ≈2s)でもピーク 2.8V から lo まで約 2.05秒で、
  //     DECAY_TIMEOUT_MS(3000ms)に収まる。
  while (tau_lo_ms == 0 && (esp_timer_get_time() - t0) < (int64_t)DECAY_TIMEOUT_MS * 1000) {
    int v = (int)(analogReadMilliVolts(PIN_SENSE) * SENSE_DIVIDER);
    uint32_t t_ms = (uint32_t)(esp_timer_get_time() / 1000);
    if (v > peak) peak = v;
    if (cross_ms == 0 && v < DECAY_THRESH_MV) cross_ms = t_ms;
    if (tau_hi_ms == 0) { if (v < DECAY_TAU_HI_MV) tau_hi_ms = t_ms; }
    else if (tau_lo_ms == 0 && v < DECAY_TAU_LO_MV) tau_lo_ms = t_ms;
    vTaskDelay(pdMS_TO_TICKS(1));
  }
  if (cross_ms)
    Serial.printf("  ハング時 減衰: freeze から %u ms で V_pump<%dmV (peak≈%dmV)\n",
                  cross_ms - freeze_ms, DECAY_THRESH_MV, peak);
  else
    Serial.printf("  %ums 待っても V_pump が %dmV 未満にならず → no_decay(デッドマン死の疑い) peak≈%dmV\n",
                  DECAY_TIMEOUT_MS, DECAY_THRESH_MV, peak);
  if (tau_lo_ms && tau_hi_ms && tau_lo_ms >= tau_hi_ms) {
    report_tau((int)(tau_lo_ms - tau_hi_ms), peak, "ハング時");
  } else {
    cnt_tau_unknown++; last_tau_half_ms = -1;
    Serial.printf("  [減衰tau] ハング時 t_half=unknown (%u ms 以内に %d mV まで落ちず) peak≈%d mV\n",
                  DECAY_TIMEOUT_MS, DECAY_TAU_LO_MV, peak);
  }
  Serial.println("  ※このあと TWDT が PANIC 設定ならリセット(層4)。そうでなければ手動リセットしてください。");
}

static void sampler_task(void*) {
  uint32_t last_hb = g_heartbeat;
  int64_t  last_hb_us = esp_timer_get_time();
  bool     hang_reported = false;
  for (;;) {
    int v = (int)(analogReadMilliVolts(PIN_SENSE) * SENSE_DIVIDER);
    g_vpump_mv = v;
    rb_t_ms[rb_head] = (uint32_t)(esp_timer_get_time() / 1000);
    rb_v_mv[rb_head] = (uint16_t)(v < 0 ? 0 : (v > 65535 ? 65535 : v));
    rb_head = (rb_head + 1) % RB_N; if (rb_head == 0) rb_full = true;

    int64_t now = esp_timer_get_time();
    uint32_t hb = g_heartbeat;
    if (hb != last_hb) { last_hb = hb; last_hb_us = now; hang_reported = false; }
    else if (!hang_reported && (now - last_hb_us) > (int64_t)HANG_DETECT_MS * 1000) {
      report_hang_decay((uint32_t)(last_hb_us / 1000));
      hang_reported = true;
    }
    vTaskDelay(pdMS_TO_TICKS(SAMPLER_PERIOD_MS));
  }
}

// ===========================================================================
// SENSE 断線検出(§7 追加 / 2026-08-23 の実機知見)
//
//   なぜ要るか: GPIO34 は入力専用で内部プルが無い。分圧が外れると浮くが、浮いた
//   ピンは電荷の逃げ道が無いので、隣を走る PUMP 線からの容量結合を保持する。結果
//   20kHz に 100 パーセント追従する「完璧な直結」に見え、V_pump は高いと読める。
//   つまりデッドマンの観測能力を潰す唯一の故障が、健康として報告される。
//
//   検出原理: PUMP を「1回だけ」立ち上げる。エッジ1発では倍圧は働かず、C2 が
//   上がるのは電荷分配ぶんの 3.3V x C1/(C1+C2) = 3.3 x 100nF/10.1uF = 約33mV。
//   Vgs(th) 1.0V の 1/30 なので点灯しない。浮いていればレールまで飛ぶ。
//
//   ★安全上の注記: 探査は「消灯している状態」でしか走らせない。パルス幅は
//   SENSE_PROBE_MS(既定 3ms)。万一 C1 が短絡している異常時にはこの幅だけゲートが
//   上がるので、幅は必要最小限にしてある。
// ===========================================================================
#if SENSE_OPEN_DETECT
static bool sense_probe_allowed(int64_t now) {
  if (now < sense_next_probe_us) return false;
  switch (state) {                 // 点灯側の状態では絶対に撃たない
    case S0_RESET_LOCKOUT: case S1_BOOTSTRAP: case S2_IDLE_LOW:
    case S3_IDLE_HIGH:     case S7_ORPHAN:
      break;
    default: return false;         // S4_BOOST / S5_LIT / S6_COOLDOWN / S8 / S9
  }
  if (ir_should_be_on || decay_active) return false;
  return true;
}

// ★guardian のループ内から呼ぶこと(§5.4: PUMP を触るのは guardian だけ)
static void sense_probe(int64_t now) {
  digitalWrite(PIN_PUMP, LOW);
  vTaskDelay(pdMS_TO_TICKS(SENSE_PROBE_MS));   // sampler(1kHz)が LOW を数点拾う
  int base = g_vpump_mv;
  digitalWrite(PIN_PUMP, HIGH);                // ★立上り 1 発だけ
  vTaskDelay(pdMS_TO_TICKS(SENSE_PROBE_MS));
  int hi = g_vpump_mv;
  digitalWrite(PIN_PUMP, LOW);                 // ★必ず Low で抜ける

  int rise = hi - base;
  sense_last_rise_mv = rise;
  bool open_now = (rise > SENSE_PROBE_RISE_MV);
  bool changed = (open_now != g_sense_open) || !sense_ever_probed;
  if (open_now && !g_sense_open) cnt_sense_open++;
  g_sense_open = open_now;
  sense_ever_probed = true;
  sense_next_probe_us = now + SENSE_RECHECK_US;

  if (!changed) return;
  if (open_now) {
    Serial.printf("[SENSE] ★断線検出: 1発エッジで V_pump が %d->%d mV (+%d / 閾値 %d)\n",
                  base, hi, rise, SENSE_PROBE_RISE_MV);
    Serial.println("        正常なら約33mV しか動かない。GPIO34 が浮いている。");
    Serial.println("        → V_pump・減衰・自己診断は以後 unknown として報告する。");
    Serial.println("        → 点灯は止めない。デッドマンの物理保証は SENSE に依存しないため。");
  } else {
    Serial.printf("[SENSE] 導通OK: 1発エッジ応答 +%d mV (閾値 %d)。V_pump を信用してよい。\n",
                  rise, SENSE_PROBE_RISE_MV);
  }
}
#endif

// ===========================================================================
// guardian_task (Core1): §5.4 単一ループ。受理判定 + PUMP 駆動 を同じループで。
// ===========================================================================
static void guardian_task(void*) {
  esp_task_wdt_add(NULL);   // 自タスクを TWDT 監視下に(§5.4)。未初期化環境では無害に失敗

  for (;;) {
    if (g_hang_request) {   // ハング模擬(状態機械が固まった状況を再現)
      Serial.println("\n★[BENCH] ハング模擬開始: guardian を while(1) で停止します。");
      Serial.println("  → PUMP のトグル停止 → C2 が R_pd(10k) で放電 → IR 消灯(デッドマン層3)");
      Serial.println("  → guardian が TWDT を feed しない → (PANIC設定時)リセット(層4)");
      pump_line_low();
      for (;;) { /* 意図的ハング。feed も pump も heartbeat も止まる */ }
    }

    int64_t now = esp_timer_get_time();
    handle_serial();

    raw_frame_t f;
    while (g_frame_q && xQueueReceive(g_frame_q, &f, 0) == pdTRUE) process_frame(&f, now);

    service_state(now);     // g_sm_pump_ok を設定(§5.4 と同一ループ)

    bool bench_on = bench_force_on && (now < bench_force_until);
    if (bench_force_on && !bench_on) { bench_force_on = false; Serial.println("[BENCH] 強制ON 期限切れ → OFF"); }
    // ★T_cap 45秒はベンチ強制ONにも効かせる(監査 順位2: 45秒はランプの実態に対する
    //   絶対上限で、どの経路が点けたかに依らない)。'p' は既定 3秒なので通常は無関係。
    //   実機が無い状態でこの直しを確かめる唯一の道でもある(CHANGES の検証手順 2-B)。
    if (bench_on && !g_within_cap) {
      bench_on = false; bench_force_on = false;
      Serial.println("[BENCH] 強制ON を T_cap 45秒(ランプ実点灯基準)で打ち切りました");
    }

    bool pump_now = g_sm_pump_ok || bench_on;
    // ★ランプの実態を更新するのはここ(実際に駆動する直前)。状態機械の意見ではなく
    //   「この周回で PUMP を叩いたか」だけを見る(監査 順位2 / §5.4 同一ループ)。
    lamp_track(now, pump_now);
    if (pump_now) pump_burst(PUMP_BURST_US);   // ★CPU が 20kHz を叩く
    else          pump_line_low();

    // 通常(非ハング)の減衰計測: ON→OFF の立下りで開始し、t_half(=τ・ln2)を測る
    // ★SENSE が断線していると浮いたピンの偽値で「減衰した」と誤判定するので測らない
    if (prev_pump && !pump_now && !g_sense_open && sense_ever_probed && g_vpump_mv >= VPUMP_MIN_FOR_DECAY_MV) {
      // (断線中は測らない = 健康と偽らない。§7 の slow_decay/no_decay も同様に unknown)
      decay_active = true; decay_start_us = now;
      decay_hi_us = 0; decay_lo_us = 0; decay_thresh_done = false; decay_peak_mv = g_vpump_mv;
      Serial.printf("[減衰] 計測開始 V_pump=%dmV\n", g_vpump_mv);
    }
    // ★計測をスキップしたことを必ず言う(§8.2 の unknown を出す規則が無かった)
    else if (prev_pump && !pump_now && !g_sense_open && sense_ever_probed) {
      cnt_decay_skipped++;
      Serial.printf("[減衰] 計測せず: ピークが %d mV で下限 %d mV に届かず (通算 %u 回)\n",
                    g_vpump_mv, VPUMP_MIN_FOR_DECAY_MV, cnt_decay_skipped);
    }
    prev_pump = pump_now;
    if (decay_active) {
      if (pump_now) {
        decay_active = false;          // 途中で再点灯 → 混ざった値は出さない(計測を捨てる)
      } else {
        int v = g_vpump_mv;
        if (v > decay_peak_mv) decay_peak_mv = v;
        // ★hi を取った「次の周回以降」でしか lo を取らない(同一周回で両方に一致すると
        //   t_half=0 になるため)。分解能以下なら report_tau が unknown を出す。
        if (decay_hi_us == 0) { if (v < DECAY_TAU_HI_MV) decay_hi_us = now; }
        else if (decay_lo_us == 0) { if (v < DECAY_TAU_LO_MV) decay_lo_us = now; }

        if (!decay_thresh_done && v < DECAY_THRESH_MV) {   // 従来の消灯時刻も残す
          decay_thresh_done = true;
          Serial.printf("[減衰] V_pump<%dmV まで %d ms\n", DECAY_THRESH_MV, (int)((now - decay_start_us) / 1000));
        }
        if (decay_lo_us != 0) {
          report_tau((int)((decay_lo_us - decay_hi_us) / 1000), decay_peak_mv, "通常OFF");
          decay_active = false;
        } else if ((now - decay_start_us) / 1000 > (int64_t)DECAY_TIMEOUT_MS) {
          if (!decay_thresh_done) Serial.println("[減衰] 時間内に落ちない → no_decay 疑い");
          cnt_tau_unknown++; last_tau_half_ms = -1;
          Serial.printf("[減衰tau] 通常OFF t_half=unknown (%u ms 以内に %d mV まで落ちず) peak=%d mV\n",
                        DECAY_TIMEOUT_MS, DECAY_TAU_LO_MV, decay_peak_mv);
          decay_active = false;
        }
      }
    }

    static int64_t last_vp = 0;
    if (now - last_vp >= VPUMP_PRINT_US) {
      last_vp = now;
      if (g_sense_open || !sense_ever_probed) {
        Serial.printf("[V_pump] unknown (%s) state=%s pump=%s\n",
                      g_sense_open ? "SENSE 断線" : "未探査", STATE_NAME[state],
                      pump_now ? "ON" : "off");
      } else {
        Serial.printf("[V_pump] %d mV (pin %d mV x2) state=%s pump=%s\n",
                      g_vpump_mv, (int)(g_vpump_mv / SENSE_DIVIDER), STATE_NAME[state],
                      pump_now ? ((bench_on && !g_sm_pump_ok) ? "ON(★BENCH強制)" : "ON") : "off");
      }
    }

#if SENSE_OPEN_DETECT
    // ★SENSE 断線の探査。消灯中の状態でだけ、1発の立上りを撃って応答を見る。
    if (!pump_now && sense_probe_allowed(now)) sense_probe(now);
#endif

    g_heartbeat++;
    esp_task_wdt_reset();          // §5.4: ポンプループ自身が feed
    vTaskDelay(pdMS_TO_TICKS(1));  // IDLE/serial に譲る。C2 は τ≈100ms なので 1ms は無害
  }
}

// ===========================================================================
void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("\n\n=== wildlife-cam 箱B 受信ファーム (PUMP 実駆動版) ===");

  // PUMP: 起動直後は必ず Low(S0 ロックアウトで 5秒間は駆動しない)。
  pinMode(PIN_PUMP, OUTPUT);
  digitalWrite(PIN_PUMP, LOW);
  pinMode(PIN_JP1, INPUT_PULLUP);
  // SENSE(GPIO34 入力専用, ADC1): 広めのレンジで読む(校正済み mV)
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);

  int64_t now = esp_timer_get_time();
  boot_lockout_until_us = now + BOOT_LOCKOUT_US;
  prev_loop_us = now; duty_bucket_start_us = now;
  last_beaconA_us = last_beaconB_us = now;
  boot_count++;
#if SENSE_OPEN_DETECT
  sense_next_probe_us = now + SENSE_FIRST_PROBE_US;   // S0 ロックアウト内に初回探査
#endif
  Serial.printf("S0: 起動ロックアウト %lld 秒間 PUMP 強制Low\n", BOOT_LOCKOUT_US / 1000000);

  g_frame_q = xQueueCreate(16, sizeof(raw_frame_t));

  esp_err_t nv = nvs_flash_init();
  if (nv == ESP_ERR_NVS_NO_FREE_PAGES || nv == ESP_ERR_NVS_NEW_VERSION_FOUND) { nvs_flash_erase(); nvs_flash_init(); }
  ble_init();
  Serial.printf("設定: LINK_ID=0x%02X  USE_WHITELIST=%d  REQUIRE_HMAC=%d  BENCH_MODE=%d\n",
                LINK_ID, USE_WHITELIST, REQUIRE_HMAC, BENCH_MODE);
#if HMAC_KEY_IS_PLACEHOLDER
  Serial.println("★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★");
  Serial.println("★ 警告: HMAC 鍵が config.h の公開テスト鍵のままです。");
  Serial.println("★ 無人運用(8/26〜9/8)に投入してはいけません。");
  Serial.println("★ config.h の【本番鍵の空欄】に鍵を貼り、HMAC_KEY_IS_PLACEHOLDER を 0 に。");
  Serial.println("★ ※Pi 側 ble_advertiser.py の --key と必ず同時に替えること。");
  Serial.println("★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★★");
#else
  Serial.println("[鍵] HMAC は本番鍵で動作します(値は表示しません)。Pi 側と一致していることを確認してください。");
#endif
  Serial.printf("T_cap の起点=ランプ実態(PUMP が連続 %lldms Low でクリア) / デューティ=10秒x%d のスライド窓\n",
                LAMP_COOL_US / 1000, DUTY_RING_N);
  Serial.printf("減衰の合否= t_half(%d→%dmV) 基準 %d ms ±%d%% %s\n",
                DECAY_TAU_HI_MV, DECAY_TAU_LO_MV, DECAY_TAU_BASELINE_MS, DECAY_TAU_TOL_PCT,
                (DECAY_TAU_BASELINE_MS <= 0) ? "★基準未設定: 据付時の値を config.h に書き写すこと" : "");
  Serial.println("ベンチ: p=強制ON  o=強制OFF  s=状態  "
#if BENCH_MODE
                 "h=ハング模擬"
#endif
                 );

  // タスク生成(デュアルコア配置)
  xTaskCreatePinnedToCore(sampler_task,  "sampler",  4096, nullptr, SAMPLER_PRIO,  nullptr, SAMPLER_CORE);
  xTaskCreatePinnedToCore(guardian_task, "guardian", 8192, nullptr, GUARDIAN_PRIO, nullptr, GUARDIAN_CORE);
}

void loop() {
  // 実処理は guardian(core1) と sampler(core0)。loopTask は寝かせておく。
  vTaskDelay(pdMS_TO_TICKS(1000));
}
