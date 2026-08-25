// pump_diag4 — GPIO34 は「本当に何かに繋がっている」のか、それとも「浮いている」のか
//   diag3 で判明した気になる点:
//     ・全駆動ピン Hi-Z のとき GPIO34 = 1117 mV。分圧(下側100kΩ)が効いていれば 0V のはず
//     ・GPIO26/27 を HIGH にしただけで GPIO34 が 750〜811 mV 動く。50kΩ 源ならあり得ない
//   → GPIO34 が浮いている疑い。浮いたピンは電荷を溜めて保持するので DC に見える。
//   対照として GPIO32 の内部プルアップ/プルダウン(約45kΩ)を「既知インピーダンス源」に使う。
#include <Arduino.h>
#include "driver/gpio.h"

static const int PUMP = 25;
static const int SENSE = 34;
static const int FLOATREF = 35;   // 何も繋がっていない基準
static const int ZREF = 32;       // 内部プルで既知インピーダンスを作れる ADC1 ピン

static void mode_out(int pin){ gpio_config_t c={}; c.pin_bit_mask=1ULL<<pin; c.mode=GPIO_MODE_INPUT_OUTPUT;
  c.pull_up_en=GPIO_PULLUP_DISABLE; c.pull_down_en=GPIO_PULLDOWN_DISABLE; c.intr_type=GPIO_INTR_DISABLE; gpio_config(&c); }
static void mode_hiz(int pin){ gpio_config_t c={}; c.pin_bit_mask=1ULL<<pin; c.mode=GPIO_MODE_INPUT;
  c.pull_up_en=GPIO_PULLUP_DISABLE; c.pull_down_en=GPIO_PULLDOWN_DISABLE; c.intr_type=GPIO_INTR_DISABLE; gpio_config(&c); }
static void mode_pu(int pin){ gpio_config_t c={}; c.pin_bit_mask=1ULL<<pin; c.mode=GPIO_MODE_INPUT;
  c.pull_up_en=GPIO_PULLUP_ENABLE; c.pull_down_en=GPIO_PULLDOWN_DISABLE; c.intr_type=GPIO_INTR_DISABLE; gpio_config(&c); }
static void mode_pd(int pin){ gpio_config_t c={}; c.pin_bit_mask=1ULL<<pin; c.mode=GPIO_MODE_INPUT;
  c.pull_up_en=GPIO_PULLUP_DISABLE; c.pull_down_en=GPIO_PULLDOWN_ENABLE; c.intr_type=GPIO_INTR_DISABLE; gpio_config(&c); }

static void track(const char* label, int seconds) {
  Serial.printf("  %s\n    ", label);
  for (int i = 0; i < seconds * 5; i++) {
    Serial.printf("%d ", analogReadMilliVolts(SENSE));
    if ((i+1) % 15 == 0) Serial.print("\n    ");
    delay(200);
  }
  Serial.println();
}

void setup() {
  Serial.begin(115200);
  delay(700);
  Serial.println("\n================ pump_diag4 ================");
  analogReadResolution(12);
  analogSetPinAttenuation(SENSE, ADC_11db);
  analogSetPinAttenuation(FLOATREF, ADC_11db);
  analogSetPinAttenuation(ZREF, ADC_11db);

  Serial.println("--- 対照: 内部プル(約45kΩ)を掛けた GPIO32 は「既知インピーダンス源」 ---");
  mode_pd(ZREF); delay(300);
  Serial.printf("  GPIO32 内部プルダウン(45k->GND) = %d mV  (期待: ほぼ 0 = 142)\n", analogReadMilliVolts(ZREF));
  mode_pu(ZREF); delay(300);
  Serial.printf("  GPIO32 内部プルアップ(45k->3.3V) = %d mV  (期待: 飽和 3134)\n", analogReadMilliVolts(ZREF));
  mode_hiz(ZREF); delay(300);
  Serial.printf("  GPIO32 プル無し(完全に浮く)      = %d mV\n", analogReadMilliVolts(ZREF));

  Serial.println("\n--- T1. 全部 Hi-Z のまま 8 秒。分圧が効いていれば動かない。浮いていれば漂う ---");
  mode_hiz(PUMP); delay(300);
  track("GPIO34 (200ms ごと):", 8);
  Serial.printf("    参考: 未接続の GPIO35 = %d mV\n", analogReadMilliVolts(FLOATREF));

  Serial.println("\n--- T2. GPIO25 を HIGH 500ms → Hi-Z。放電先があるかを見る ---");
  Serial.println("     100kΩ で PUMP 網に繋がっているなら R_pd 10kΩ 経由で即 0V に落ちる");
  Serial.println("     どこにも繋がっていない(浮き)なら電荷が逃げず 3V 近くを保持する");
  mode_out(PUMP); gpio_set_level((gpio_num_t)PUMP, 1); delay(500);
  Serial.printf("    Hi-Z 直前 = %d mV\n", analogReadMilliVolts(SENSE));
  mode_hiz(PUMP);
  track("Hi-Z にした後 (200ms ごと):", 6);

  Serial.println("\n--- T3. GPIO25 を LOW に駆動してから Hi-Z ---");
  mode_out(PUMP); gpio_set_level((gpio_num_t)PUMP, 0); delay(500);
  Serial.printf("    Hi-Z 直前 = %d mV\n", analogReadMilliVolts(SENSE));
  mode_hiz(PUMP);
  track("Hi-Z にした後 (200ms ごと):", 4);

  Serial.println("\n--- T4. 源インピーダンスの推定: チャンネル切替直後の連続読み ---");
  Serial.println("     低インピーダンス源なら 1 発目から安定。高インピーダンス/浮きなら数発かけて動く");
  mode_out(PUMP); gpio_set_level((gpio_num_t)PUMP, 1); delay(500);
  mode_pd(ZREF); delay(200);
  Serial.print("    GPIO32(45k プルダウン既知源):");
  for (int i=0;i<12;i++){ analogReadMilliVolts(FLOATREF); Serial.printf(" %d", analogReadMilliVolts(ZREF)); }
  Serial.println();
  Serial.print("    GPIO34(SENSE, GPIO25=HIGH)  :");
  for (int i=0;i<12;i++){ analogReadMilliVolts(FLOATREF); Serial.printf(" %d", analogReadMilliVolts(SENSE)); }
  Serial.println();
  gpio_set_level((gpio_num_t)PUMP, 0); delay(300);
  Serial.print("    GPIO34(SENSE, GPIO25=LOW)   :");
  for (int i=0;i<12;i++){ analogReadMilliVolts(FLOATREF); Serial.printf(" %d", analogReadMilliVolts(SENSE)); }
  Serial.println();

  Serial.println("\n--- 判定 ---");
  Serial.println("  T1 が漂う / T2 で Hi-Z 後も 3V 近くを保持 → GPIO34 は浮いている(SENSE 配線が繋がっていない)");
  Serial.println("  T1 が動かない / T2 で即 0V         → GPIO34 は本当に PUMP 網に抵抗で繋がっている");
}
void loop(){ delay(2000); }
