// pump_live — 配線を押しながら画面を見るための常時モニタ
//   1秒ごとに「SENSE は繋がっているか」を判定して出す。押して直れば表示が変わる。
//
//   判定の原理(ここが肝):
//     GPIO25 を 1 回だけ HIGH にしたとき、正しく組まれていれば C2 が持ち上がる量は
//       3.3V × C1/(C1+C2) = 3.3 × 100nF/10.1uF = 33mV   → 分圧して 16mV → 142mV のまま
//     一方 GPIO34 が浮いていると、隣の配線から容量結合で一気にレールまで飛ぶ(3134mV)。
//   つまり「1発のエッジで飛ぶかどうか」で、繋がっている/浮いている が 0.5 秒で分かる。
#include <Arduino.h>
#include "driver/gpio.h"

static const int PUMP = 25, SENSE = 34;
static const int PUMP_HALF_US = 25;      // 20kHz
static const int DECAY_THRESH_MV = 1300; // V_pump がこれを割ったら消灯相当

static void out(int p){ gpio_config_t c={}; c.pin_bit_mask=1ULL<<p; c.mode=GPIO_MODE_INPUT_OUTPUT;
  c.pull_up_en=GPIO_PULLUP_DISABLE; c.pull_down_en=GPIO_PULLDOWN_DISABLE; c.intr_type=GPIO_INTR_DISABLE; gpio_config(&c); }
static int mv(){ long s=0; for(int i=0;i<16;i++) s+=analogReadMilliVolts(SENSE); return (int)(s/16); }

// 1発のエッジで飛ぶか? 飛べば浮き。
static bool sense_is_floating(int* lo, int* hi) {
  gpio_set_level((gpio_num_t)PUMP, 0); delay(300);
  *lo = mv();
  gpio_set_level((gpio_num_t)PUMP, 1); delay(50);
  *hi = mv();
  gpio_set_level((gpio_num_t)PUMP, 0); delay(80);
  return (*hi > 1000);
}

static void pump_for(uint32_t ms) {
  uint32_t t0 = millis();
  while (millis() - t0 < ms) {
    gpio_set_level((gpio_num_t)PUMP, 1); delayMicroseconds(PUMP_HALF_US);
    gpio_set_level((gpio_num_t)PUMP, 0); delayMicroseconds(PUMP_HALF_US);
  }
  gpio_set_level((gpio_num_t)PUMP, 0);
}

void setup() {
  Serial.begin(115200);
  delay(600);
  out(PUMP);
  gpio_set_level((gpio_num_t)PUMP, 0);
  analogReadResolution(12);
  analogSetPinAttenuation(SENSE, ADC_11db);
  Serial.println("\n============ pump_live: 配線を押しながら見てください ============");
  Serial.println("SENSE=浮き   … GPIO34 がどこにも繋がっていない。teal の線とその両端を押す");
  Serial.println("SENSE=接続OK … 繋がった。そのまま V_pump の値を見る");
  Serial.println("目標 V_pump = 5500〜6200mV。ただし ADC は 5000mV 超で飽和するのでテスタ併用");
  Serial.println();
}

void loop() {
  int lo=0, hi=0;
  bool floating = sense_is_floating(&lo, &hi);

  if (floating) {
    Serial.printf("SENSE=★浮き★   1発エッジで %d mV まで飛んだ(繋がっていれば %d のまま)\n", hi, lo);
    delay(400);
    return;
  }

  // 繋がっている → ポンプを回して本当の V_pump を測る
  pump_for(1500);
  delayMicroseconds(150);           // トグルを止めてから読む(C2 は tau=2s なのでほぼ落ちない)
  int peak_pin = mv();

  // 減衰: 1.3V を割るまでの時間
  uint32_t t0 = millis(); int cross = 0;
  while (millis() - t0 < 5000) {
    int p = analogReadMilliVolts(SENSE);
    if (p * 2 < DECAY_THRESH_MV) { cross = (int)(millis() - t0); break; }
    delay(5);
  }

  Serial.printf("SENSE=接続OK  V_pump=%d mV (pin %d)  減衰 %s  [1発エッジ %d->%d mV]\n",
                peak_pin * 2, peak_pin,
                cross ? (String(cross) + " ms").c_str() : ">5000 ms(落ちない)",
                lo, hi);
  delay(300);
}
