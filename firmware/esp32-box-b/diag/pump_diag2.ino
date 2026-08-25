// pump_diag2 — SENSE(GPIO34) が「何に繋がっているか」を波形の形から特定する
//   diag1 の結論: GPIO25 のパッド駆動は完全に正常(静的HIGH/LOW/20kHz とも 100%)。
//   diag1 の欠陥: トグル中の ADC を必ず LOW 直後に取っていたので位相が偏っていた。
//   ここでは HIGH 位相 / LOW 位相を別々に取り、さらに立上り・立下りの時定数を測る。
#include <Arduino.h>
#include "driver/gpio.h"

static const int PIN_PUMP  = 25;
static const int PIN_SENSE = 34;

static void cfg_io(int pin) {
  gpio_config_t c = {};
  c.pin_bit_mask = 1ULL << pin;
  c.mode = GPIO_MODE_INPUT_OUTPUT;
  c.pull_up_en = GPIO_PULLUP_DISABLE;
  c.pull_down_en = GPIO_PULLDOWN_DISABLE;
  c.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&c);
}
static inline int raw_mv() { return analogReadMilliVolts(PIN_SENSE); }
static int avg_mv(int n) { long s=0; for(int i=0;i<n;i++) s+=raw_mv(); return (int)(s/n); }

// 立上り/立下りの形を出す。直結なら 1ms で終わる。10uF に抵抗経由なら数百ms かかる。
static void ramp(const char* label, int level) {
  gpio_set_level((gpio_num_t)PIN_PUMP, level);
  uint32_t t0 = micros();
  const int ms[] = {0,1,2,5,10,20,50,100,200,350,500,800};
  Serial.printf("  %s :", label);
  for (unsigned i=0;i<sizeof(ms)/sizeof(ms[0]);i++) {
    while ((int)((micros()-t0)/1000) < ms[i]) { }
    Serial.printf(" %d=%d", ms[i], raw_mv());
  }
  Serial.println("  (ms=mV)");
}

void setup() {
  Serial.begin(115200);
  delay(600);
  Serial.println("\n================ pump_diag2 ================");
  cfg_io(PIN_PUMP);
  analogReadResolution(12);
  analogSetPinAttenuation(PIN_SENSE, ADC_11db);

  Serial.println("--- A. GPIO25 を Hi-Z(入力) にしたときの SENSE ---");
  gpio_set_direction((gpio_num_t)PIN_PUMP, GPIO_MODE_INPUT);
  delay(500);
  Serial.printf("  PUMP=Hi-Z: SENSE pin = %d mV\n", avg_mv(64));
  cfg_io(PIN_PUMP);
  gpio_set_level((gpio_num_t)PIN_PUMP, 0);
  delay(500);

  Serial.println("--- B. 静的レベルの立上り/立下りの形(時定数を見る) ---");
  ramp("LOW->HIGH", 1);
  ramp("HIGH->LOW", 0);
  delay(300);

  Serial.println("--- C. 20kHz トグル中を「HIGH位相」と「LOW位相」で別々に読む ---");
  for (int rep=0; rep<3; rep++) {
    long hs=0, ls=0; int hmax=0, lmax=0; int n=0;
    uint32_t t0 = millis();
    while (millis()-t0 < 1000) {
      for (int i=0;i<200;i++){ gpio_set_level((gpio_num_t)PIN_PUMP,1); delayMicroseconds(25);
                               gpio_set_level((gpio_num_t)PIN_PUMP,0); delayMicroseconds(25); }
      gpio_set_level((gpio_num_t)PIN_PUMP,1); delayMicroseconds(25);
      int h = raw_mv();                       // HIGH 位相で1点
      gpio_set_level((gpio_num_t)PIN_PUMP,0); delayMicroseconds(25);
      int l = raw_mv();                       // LOW 位相で1点
      hs+=h; ls+=l; if(h>hmax)hmax=h; if(l>lmax)lmax=l; n++;
    }
    gpio_set_level((gpio_num_t)PIN_PUMP,0);
    Serial.printf("  rep%d: HIGH位相 平均=%ld 最大=%d /  LOW位相 平均=%ld 最大=%d  (n=%d)\n",
                  rep, n?hs/n:0, hmax, n?ls/n:0, lmax, n);
  }

  Serial.println("--- D. 20kHz を 3 秒回して「止めた直後」から減衰を追う ---");
  Serial.println("     (本物の C2 に電荷が溜まっていれば、止めた後もしばらく電圧が残る)");
  uint32_t t0 = millis();
  while (millis()-t0 < 3000) {
    gpio_set_level((gpio_num_t)PIN_PUMP,1); delayMicroseconds(25);
    gpio_set_level((gpio_num_t)PIN_PUMP,0); delayMicroseconds(25);
  }
  gpio_set_level((gpio_num_t)PIN_PUMP,0);
  uint32_t t1 = micros();
  const int us[] = {0,200,500,1000,2000,5000,10000,20000,50000,100000,200000,400000};
  Serial.print("  停止後:");
  for (unsigned i=0;i<sizeof(us)/sizeof(us[0]);i++) {
    while ((int)(micros()-t1) < us[i]) { }
    Serial.printf(" %dus=%dmV", us[i], raw_mv());
  }
  Serial.println();
  Serial.println("--- 判定の読み方 ---");
  Serial.println("  ・C の HIGH位相 が LOW位相 とほぼ同じ大きさで振れる → SENSE は GPIO25 に直結相当(C1 を経ていない)");
  Serial.println("  ・D で停止直後に一瞬で 0 に落ちる      → SENSE 節点に C2 の蓄電が無い(=C2 の行が違う/未接続)");
  Serial.println("  ・D で数百 ms かけて落ちる             → C2 は効いている(ポンプが上がらないのは D1/D2 側)");
}
void loop() { delay(1000); }
