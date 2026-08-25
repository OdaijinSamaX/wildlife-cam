#!/usr/bin/env bash
# Pi 側で BLE 広告を出すための前後処理。終了時に必ず原状復帰する。
# 手順の出典: HANDOFF「Pi 側の広告を出すには毎回この手順が要る」
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"

restore() {
  echo "[restore] 原状復帰を開始"
  sudo systemctl start bluetooth >/dev/null 2>&1 || true
  sudo /usr/sbin/rfkill block bluetooth >/dev/null 2>&1 || true
  sudo hciconfig hci0 down >/dev/null 2>&1 || true
  echo "[restore] bluetoothd=$(systemctl is-active bluetooth) rfkill=$(/usr/sbin/rfkill list bluetooth | grep -c 'Soft blocked: yes')"
}
trap restore EXIT INT TERM

echo "[prep] bluetoothd 停止 (しないと hci0 を奪われて EBUSY)"
sudo systemctl stop bluetooth
echo "[prep] rfkill soft block 解除"
sudo /usr/sbin/rfkill unblock bluetooth
sleep 0.5
sudo hciconfig hci0 down >/dev/null 2>&1 || true
echo "[prep] hci0 の状態: $(hciconfig hci0 | sed -n '2p' | tr -s ' ')"

echo "[run] $*"
sudo python3 "$HERE/$@"
