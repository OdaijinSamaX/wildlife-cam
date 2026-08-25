// pump_diag3 — 「どのピンが、どのピンに繋がっているか」を総当たりで出す
//   diag2 で GPIO34 が GPIO25 に追従したが、テスターの抵抗値は正しい配線を示唆した。
//   矛盾しているので、対照実験をする:
//     ・GPIO25 以外(26/27)を振っても GPIO34 が動くなら、配線ではなく測定系の artifact
//     ・GPIO34 以外の ADC ピンも一緒に動くなら、共通要因(電源/隣接列の容量結合)
//   駆動側 × 読み側の全組合せを出す。
#include <Arduino.h>
#include "driver/gpio.h"

static const int DRV[]  = {25, 26, 27};                 // 出力にして振るピン
static const int ADCP[] = {32, 33, 34, 35, 36, 39};     // ADC1 の読み側

static void as_out(int pin) {
  gpio_config_t c = {};
  c.pin_bit_mask = 1ULL << pin;
  c.mode = GPIO_MODE_INPUT_OUTPUT;
  c.pull_up_en = GPIO_PULLUP_DISABLE;
  c.pull_down_en = GPIO_PULLDOWN_DISABLE;
  c.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&c);
  gpio_set_level((gpio_num_t)pin, 0);
}
static void as_hiz(int pin) {
  gpio_config_t c = {};
  c.pin_bit_mask = 1ULL << pin;
  c.mode = GPIO_MODE_INPUT;
  c.pull_up_en = GPIO_PULLUP_DISABLE;
  c.pull_down_en = GPIO_PULLDOWN_DISABLE;
  c.intr_type = GPIO_INTR_DISABLE;
  gpio_config(&c);
}
static int avg(int pin, int n) { long s=0; for(int i=0;i<n;i++) s+=analogReadMilliVolts(pin); return (int)(s/n); }

void setup() {
  Serial.begin(115200);
  delay(700);
  Serial.println("\n================ pump_diag3 ================");
  analogReadResolution(12);
  for (unsigned j=0;j<sizeof(ADCP)/sizeof(ADCP[0]);j++) analogSetPinAttenuation(ADCP[j], ADC_11db);

  // 全駆動ピンをまず Hi-Z にして基準を取る
  for (unsigned i=0;i<sizeof(DRV)/sizeof(DRV[0]);i++) as_hiz(DRV[i]);
  delay(300);
  Serial.print("全駆動ピン Hi-Z のとき :");
  for (unsigned j=0;j<sizeof(ADCP)/sizeof(ADCP[0]);j++) Serial.printf("  GPIO%d=%d", ADCP[j], avg(ADCP[j],32));
  Serial.println("  (mV)");
  Serial.println();

  for (unsigned i=0;i<sizeof(DRV)/sizeof(DRV[0]);i++) {
    int d = DRV[i];
    for (unsigned k=0;k<sizeof(DRV)/sizeof(DRV[0]);k++) as_hiz(DRV[k]);   // 他は Hi-Z
    as_out(d);
    for (int lvl=0; lvl<=1; lvl++) {
      gpio_set_level((gpio_num_t)d, lvl);
      delay(400);
      Serial.printf("GPIO%d を %-4s にすると :", d, lvl ? "HIGH" : "LOW");
      for (unsigned j=0;j<sizeof(ADCP)/sizeof(ADCP[0]);j++) Serial.printf("  GPIO%d=%d", ADCP[j], avg(ADCP[j],32));
      Serial.println("  (mV)");
    }
    gpio_set_level((gpio_num_t)d, 0);
    as_hiz(d);
    Serial.println();
  }

  Serial.println("読み方:");
  Serial.println("  ・GPIO25 を振ったときだけ GPIO34 が動く → SENSE は本当に PUMP 系に繋がっている");
  Serial.println("  ・GPIO26/27 を振っても GPIO34 が動く   → 配線ではなく測定系/電源の共通要因");
  Serial.println("  ・GPIO34 以外の ADC も一緒に動く        → 浮いたピン同士の容量結合(=そのピンは未接続)");
  Serial.println("  ・HIGH で 1600mV 前後なら 100k/100k 分圧が効いている(=3134 とは意味が違う)");
}
void loop() { delay(2000); }
