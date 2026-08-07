#!/usr/bin/env bash
# カメラ実演の一発診断。Pi上で実行する。
set -uo pipefail

APP_HOME="${WILDLIFE_CAM_HOME:-$HOME/wildlife-cam}"
SERVICE="wildlife-cam.service"
MIN_FREE_BYTES="${WILDLIFE_MIN_FREE_BYTES:-2147483648}"

ok='【OK】'; ng='【NG】'; warn='【注意】'
echo "======================================================"
echo " wildlife-cam 現地診断  $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo "======================================================"

if timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -qx yes; then
  echo "$ok 時刻: ネット時刻に同期済み"
else
  echo "$warn 時刻: 未同期です。表示時刻が正しいか確認してください"
fi

free_bytes="$(df -B1 --output=avail "$APP_HOME" 2>/dev/null | tail -1 | tr -d ' ')"
if [[ "$free_bytes" =~ ^[0-9]+$ ]]; then
  free_human="$(numfmt --to=iec-i --suffix=B "$free_bytes" 2>/dev/null || echo "$free_bytes bytes")"
  if [ "$free_bytes" -ge "$MIN_FREE_BYTES" ]; then
    echo "$ok SDカード空き: $free_human"
  else
    echo "$ng SDカード空き: $free_human（2 GiB未満）"
  fi
else
  echo "$ng SDカード空き: 確認できません"
fi

if systemctl is-active --quiet "$SERVICE"; then
  pid="$(systemctl show -p MainPID --value "$SERVICE")"
  restarts="$(systemctl show -p NRestarts --value "$SERVICE")"
  echo "$ok カメラサービス: 動作中（PID $pid、再起動 $restarts 回）"
else
  echo "$ng カメラサービス: 停止中"
fi

latest="$(find "$APP_HOME/videos" "$APP_HOME/videos/quarantine" -maxdepth 1 -type f -name '*.mp4' -printf '%T@ %s %p\n' 2>/dev/null | sort -nr | head -1)"
if [ -n "$latest" ]; then
  read -r epoch size path <<<"$latest"
  recorded="$(date -d "@${epoch%%.*}" '+%Y-%m-%d %H:%M:%S' 2>/dev/null || echo "時刻不明")"
  size_human="$(numfmt --to=iec-i --suffix=B "$size" 2>/dev/null || echo "$size bytes")"
  echo "$ok 直近の保存動画: $recorded  $size_human"
  echo "     $path"
else
  echo "$warn 直近の保存動画: なし（送信成功後は削除されるため正常な場合もあります）"
fi

echo "------------------------------------------------------"
if [ -x "$APP_HOME/scripts/net-status.sh" ]; then
  "$APP_HOME/scripts/net-status.sh"
else
  echo "$ng ネット診断: scripts/net-status.sh がありません"
fi
echo "======================================================"
