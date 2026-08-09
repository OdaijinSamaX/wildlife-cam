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
# ---- 撮影・送信の状態（送信量上限） ----
STATUS_FILE=""
for d in "${WILDLIFE_STATE_DIR:-}" /var/lib/wildlife-cam "$APP_HOME/state"; do
  [ -n "$d" ] && [ -r "$d/status" ] && { STATUS_FILE="$d/status"; break; }
done

mode=""; on_lte=0; bu=0; bc=0; bblocked=0; bresume=0; recs_hr=0
if [ -n "$STATUS_FILE" ]; then
  while IFS='=' read -r k v; do
    case "$k" in
      mode) mode="$v" ;;
      on_lte) on_lte="$v" ;;
      budget_used_bytes) bu="$v" ;;
      budget_cap_bytes) bc="$v" ;;
      budget_blocked) bblocked="$v" ;;
      budget_resume_epoch) bresume="$v" ;;
      recordings_last_hour) recs_hr="$v" ;;
    esac
  done < "$STATUS_FILE"
fi

to_mb() { echo $(( ${1:-0} / 1048576 )); }

if [ -n "$STATUS_FILE" ]; then
  if [ "$on_lte" = "1" ]; then
    rem=$(( bc - bu )); [ "$rem" -lt 0 ] && rem=0
    line="送信量(直近1時間): $(to_mb "$bu")MB / $(to_mb "$bc")MB (残り $(to_mb "$rem")MB)"
    if [ "$bblocked" = "1" ]; then
      echo "$warn $line"
    else
      echo "$ok $line"
    fi
  else
    echo "$ok 送信量: WiFi 接続中のため上限なし（LTE のときだけ制限）"
  fi
  echo "     直近1時間の録画本数: ${recs_hr} 本"
else
  echo "$warn 撮影・送信状態: まだ記録がありません（サービス起動直後の可能性）"
fi

# 送信保留（未送信）クリップの本数・容量
pend_n=0; pend_bytes=0
if [ -d "$APP_HOME/videos" ]; then
  while read -r sz; do
    [ -n "$sz" ] || continue
    pend_n=$(( pend_n + 1 )); pend_bytes=$(( pend_bytes + sz ))
  done < <(find "$APP_HOME/videos" -maxdepth 1 -type f -name '*.mp4' -printf '%s\n' 2>/dev/null)
fi
if [ "$pend_n" -gt 0 ]; then
  msg="送信保留(SDに待機中): ${pend_n} 本 / $(to_mb "$pend_bytes")MB"
  if [ "$bblocked" = "1" ] && [ "$bresume" -gt 0 ]; then
    resume_hm="$(date -d "@$bresume" '+%H:%M' 2>/dev/null || echo '?')"
    msg="$msg  （予算切れ。${resume_hm} 頃から順次送信再開）"
  fi
  echo "$warn $msg"
else
  echo "$ok 送信保留: なし（未送信の動画は貯まっていません）"
fi

# SD が今のペースであと何時間もつか（おおよそ。1本≒2.4MiBで概算）
if [[ "${free_bytes:-}" =~ ^[0-9]+$ ]] && [ "$recs_hr" -gt 0 ]; then
  per_hr=$(( recs_hr * 2516582 ))
  hours_left=$(( free_bytes / per_hr ))
  echo "     SD 残り持続目安: 約 ${hours_left} 時間（直近ペース ${recs_hr}本/時 で概算）"
fi

echo "------------------------------------------------------"
if [ -x "$APP_HOME/scripts/net-status.sh" ]; then
  "$APP_HOME/scripts/net-status.sh"
else
  echo "$ng ネット診断: scripts/net-status.sh がありません"
fi
echo "======================================================"
