// pump_diag — GPIO25 チャージポンプ切り分け用の一時ファーム
//   目的: 「GPIO が駆動しているか」を、テスターを当てずに ESP32 自身に読ませて確かめる。
//   GPIO25 を INPUT_OUTPUT にすると、出力しながらパッドの実電圧をデジタル読み戻しできる。
#include <Arduino.h>
#include "driver/gpio.h"
#include "esp_adc_cal.h"

static const int PIN_PUMP  = 25;   // 被疑ピン
static const int PIN_REF   = 26;   // 何も繋がっていない参照ピン(手法の妥当性確認用)
static const int PIN_SENSE = 34;   // ADC1_CH6: V_pump の 100k/100k 分圧

static void cfg_io(int pin) {
  gpio_config_t c = {};
  c.pin_bit_mask = 1ULL << pin;
  c.mode = GPIO_MODE_INPUT_OUTPUT;      // ★出力しながら読み戻せる
  c.pull_up_en = GPIO_PULLUP_DISABLE;
  c.pull_down_en = GPIO_PULLDOWN_DISABLE;
  c.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&c);
}

// 静的レベルを与えて、パッドを N 回読み戻して 1 の個数を返す
static int static_level_test(int pin, int level) {
  gpio_set_level((gpio_num_t)pin, level);
  delay(50);
  int ones = 0;
  for (int i = 0; i < 200; i++) { ones += gpio_get_level((gpio_num_t)pin); delayMicroseconds(20); }
  return ones;
}

static int sense_mv() {
  long sum = 0;
  for (int i = 0; i < 64; i++) sum += analogReadMilliVolts(PIN_SENSE);
  return (int)(sum / 64);
}

// 20kHz でトグルしながら、HIGH 直後 / LOW 直後にパッドを読む
static void toggle_test(int pin, uint32_t ms) {
  uint32_t hi_ok = 0, lo_ok = 0, n = 0;
  uint32_t t0 = millis();
  while (millis() - t0 < ms) {
    gpio_set_level((gpio_num_t)pin, 1);
    delayMicroseconds(25);
    hi_ok += gpio_get_level((gpio_num_t)pin);      // HIGH のはず
    gpio_set_level((gpio_num_t)pin, 0);
    delayMicroseconds(25);
    lo_ok += (gpio_get_level((gpio_num_t)pin) == 0) ? 1 : 0;   // LOW のはず
    n++;
  }
  gpio_set_level((gpio_num_t)pin, 0);
  Serial.printf("  20kHz %ums: 周期数=%u  HIGH読み戻し成功=%u (%.1f%%)  LOW読み戻し成功=%u (%.1f%%)\n",
                ms, n, hi_ok, n ? 100.0*hi_ok/n : 0.0, lo_ok, n ? 100.0*lo_ok/n : 0.0);
}

void report(const char* name, int pin) {
  int lo = static_level_test(pin, 0);
  int hi = static_level_test(pin, 1);
  Serial.printf("[%s GPIO%d] 静的LOW時に読めた1の数=%d/200(期待0)  静的HIGH時=%d/200(期待200)\n",
                name, pin, lo, hi);
  gpio_set_level((gpio_num_t)pin, 0);
}

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println();
  Serial.println("================ pump_diag ================");
  cfg_io(PIN_PUMP);
  cfg_io(PIN_REF);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);

  Serial.printf("SENSE(GPIO34) 静止時: pin=%d mV -> V_pump=%d mV\n", sense_mv(), sense_mv()*2);
  Serial.println("--- 1. 静的レベルの読み戻し ---");
  report("PUMP", PIN_PUMP);
  report("REF ", PIN_REF);

  Serial.println("--- 2. 静的HIGH のまま SENSE を見る(C1 が短絡していれば V_pump が上がる) ---");
  gpio_set_level((gpio_num_t)PIN_PUMP, 1);
  delay(500);
  Serial.printf("  PUMP=HIGH 500ms 後: pin=%d mV -> V_pump=%d mV\n", sense_mv(), sense_mv()*2);
  gpio_set_level((gpio_num_t)PIN_PUMP, 0);
  delay(500);
  Serial.printf("  PUMP=LOW  500ms 後: pin=%d mV -> V_pump=%d mV\n", sense_mv(), sense_mv()*2);

  Serial.println("--- 3. 20kHz トグルの読み戻し ---");
  toggle_test(PIN_PUMP, 500);
  toggle_test(PIN_REF, 500);
}

void loop() {
  Serial.println("--- 4. 20kHz を 3 秒回して SENSE を追う ---");
  uint32_t t0 = millis();
  int peak = 0;
  while (millis() - t0 < 3000) {
    for (int i = 0; i < 400; i++) {   // 約20ms 分のトグル
      gpio_set_level((gpio_num_t)PIN_PUMP, 1); delayMicroseconds(25);
      gpio_set_level((gpio_num_t)PIN_PUMP, 0); delayMicroseconds(25);
    }
    int mv = analogReadMilliVolts(PIN_SENSE) * 2;
    if (mv > peak) peak = mv;
  }
  gpio_set_level((gpio_num_t)PIN_PUMP, 0);
  Serial.printf("  3秒トグル中の V_pump 最大 = %d mV\n", peak);
  delay(300);
  Serial.printf("  停止 300ms 後の V_pump = %d mV\n", sense_mv()*2);
  Serial.println("(★いま GPIO25 の行をテスター直流電圧で測るなら、この 3 秒の間)");
  delay(2000);
}
