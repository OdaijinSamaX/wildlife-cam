#!/usr/bin/env bash
# wildlife-netwatch -- 屋久島など WiFi の無い場所での恒久ネットワーク自己復旧
#
# 60 秒ごとに systemd timer から oneshot で起動され、1 回分の健全性判定と
# （必要なら）復旧措置を行って終了する。状態は /run に持ち、再起動判定用の
# 永続情報だけ /var/lib に置く。root で実行される前提（nmcli のシステム接続・
# systemctl restart・reboot を行うため）。
#
# 設計方針:
#  - 単一指標に依存しない: L3(ping) / DNS / L7(204) の 3 点で判定する。
#  - 誤発動しない: 自宅で WiFi が正常なときは健全判定になり、一切手を出さない。
#  - 段階的エスカレーション: 軽い措置から順に。各措置の後で必ず再判定し、
#    回復したら即座に連続失敗カウンタを 0 に戻す。
#  - reboot は最後の手段。1 時間に 1 回まで。録画・アップロード中は待つ。
#  - スクリプト自身が落ちても壊れないよう、set -e は使わず全て自前で握る。

set -uo pipefail

# ---- 設定 -----------------------------------------------------------------
PING_HOSTS=(1.1.1.1 8.8.8.8)
DNS_NAMES=(www.google.com one.one.one.one)
L7_URLS=(http://connectivitycheck.gstatic.com/generate_204 http://cp.cloudflare.com/generate_204)

WIFI_CON="wifi-iot"       # 自宅 WiFi プロファイル (metric 600)
WIFI_DEV="wlan0"
LTE_CON="lte-his"         # LTE プロファイル (metric 900)
LTE_DEV="cdc-wdm0"        # ModemManager/NM から見た gsm デバイス
LTE_NETIF="wwan0"         # 実際に経路が立つネットワーク IF

WIFI_PENALTY_SECS=600     # 「つながらない WiFi」降格後、WiFi へ戻さない時間
REBOOT_AFTER_SECS=1800    # 連続で外に出られない状態がこの秒数続いたら reboot 検討 (=30分)
REBOOT_MIN_INTERVAL=3600  # reboot は最低この間隔を空ける (=1時間)
RECHECK_SLEEP=12          # 復旧措置後に効果が出るのを待つ秒数
CAM_HOME="/home/odaijinsamax/wildlife-cam"
CAM_ACTIVE_WINDOW=180     # videos/ がこの秒数以内に更新 = 録画/送信中とみなす

STATE_DIR="/run/wildlife-netwatch"
PERSIST_DIR="/var/lib/wildlife-netwatch"
LOG="/var/log/wildlife-net.log"

FAIL_FILE="$STATE_DIR/consecutive_failures"
FIRST_FAIL_FILE="$STATE_DIR/first_fail_epoch"
LAST_ACTION_FILE="$STATE_DIR/last_action"      # "epoch<TAB>説明"
STATUS_FILE="$STATE_DIR/status"                # net-status.sh 用の最新スナップショット
WIFI_PENALTY_FILE="$STATE_DIR/wifi_penalty_until"
ONLINE_SINCE_FILE="$STATE_DIR/online_since"
LAST_REBOOT_FILE="$PERSIST_DIR/last_reboot_epoch"

mkdir -p "$STATE_DIR" "$PERSIST_DIR" 2>/dev/null || true
touch "$LOG" 2>/dev/null || true

now() { date +%s; }
stamp() { date '+%Y-%m-%d %H:%M:%S'; }

# ---- 小物 -----------------------------------------------------------------
read_int() { # ファイルから整数を読む。無ければ 0。
  local f="$1" v
  v="$(cat "$f" 2>/dev/null)" || v=""
  case "$v" in
    ''|*[!0-9]*) echo 0 ;;
    *) echo "$v" ;;
  esac
}

log_line() { # journal(stdout) と /var/log/wildlife-net.log の両方へ 1 行
  local msg="$1"
  echo "$msg"
  printf '%s %s\n' "$(stamp)" "$msg" >>"$LOG" 2>/dev/null || true
}

record_action() { # 最後に打った復旧措置を記録
  printf '%s\t%s\n' "$(now)" "$1" >"$LAST_ACTION_FILE" 2>/dev/null || true
  log_line "ACTION: $1"
}

default_route_dev() {
  ip -o route show default 2>/dev/null \
    | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}'
}

lte_available() { # LTE 経路が使える状態か（降格判断の前提）
  ip -o route show default 2>/dev/null | grep -q "dev $LTE_NETIF" && return 0
  nmcli -t -f DEVICE,STATE device 2>/dev/null | grep -q "^$LTE_DEV:connected" && return 0
  return 1
}

# ---- 健全性判定 -----------------------------------------------------------
# それぞれ 0=OK / 1=NG を返し、結果はグローバルに残す。
L3_OK=1; DNS_OK=1; L7_OK=1

check_l3() { # どちらか 1 つでも ping が通れば L3 OK（片方の障害で誤判定しない）
  local h
  for h in "${PING_HOSTS[@]}"; do
    if ping -c1 -W2 "$h" >/dev/null 2>&1; then L3_OK=0; return 0; fi
  done
  L3_OK=1; return 1
}

check_dns() { # どちらか 1 つでも名前が引ければ DNS OK
  local n
  for n in "${DNS_NAMES[@]}"; do
    # 応答なしの DNS でブロックしないよう timeout で頭を抑える
    if timeout 6 getent ahostsv4 "$n" >/dev/null 2>&1; then DNS_OK=0; return 0; fi
  done
  DNS_OK=1; return 1
}

check_l7() { # どちらか 1 つでも 204 が返れば L7 OK（DNS+経路+到達性を一括検証）
  local u code
  for u in "${L7_URLS[@]}"; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 "$u" 2>/dev/null)" || code=""
    if [ "$code" = "204" ]; then L7_OK=0; return 0; fi
  done
  L7_OK=1; return 1
}

# 「実際にネットが使えるか」= L7 が本命。ただし L7 サーバ側の一時障害で
# 誤判定しないよう、DNS+L3 が両方生きていれば救済的に健全扱いにする。
is_healthy() {
  check_l3; check_dns; check_l7
  if [ "$L7_OK" -eq 0 ]; then return 0; fi
  if [ "$DNS_OK" -eq 0 ] && [ "$L3_OK" -eq 0 ]; then return 0; fi
  return 1
}

health_summary() {
  local l3 dns l7
  [ "$L3_OK" -eq 0 ] && l3=OK || l3=NG
  [ "$DNS_OK" -eq 0 ] && dns=OK || dns=NG
  [ "$L7_OK" -eq 0 ] && l7=OK || l7=NG
  echo "l3=$l3 dns=$dns l7=$l7 route=$(default_route_dev)"
}

# ---- 復旧措置 -------------------------------------------------------------
act_lte_up() {
  record_action "nmcli con up $LTE_CON (LTE 張り直し)"
  timeout 45 nmcli con up "$LTE_CON" >/dev/null 2>&1 || true
}

act_wifi_demote() {
  # 「つながらない WiFi に居座る」対策。default 経路が wlan0 なのに外に出られず、
  # かつ LTE が使えるときだけ WiFi を一時的に切り離し、ペナルティ期間 LTE に載せる。
  local dev; dev="$(default_route_dev)"
  if [ "$dev" != "$WIFI_DEV" ]; then
    log_line "wifi-demote skip: default route is '$dev' (wlan0 ではない)"
    return
  fi
  if ! lte_available; then
    log_line "wifi-demote skip: LTE が使えないので WiFi は切らない"
    return
  fi
  record_action "wlan0 を一時降格し LTE へ載せ替え (${WIFI_PENALTY_SECS}s)"
  # autoconnect を切らないと NM が即座に WiFi を張り直してしまう。
  nmcli con mod "$WIFI_CON" connection.autoconnect no >/dev/null 2>&1 || true
  nmcli con down "$WIFI_CON" >/dev/null 2>&1 || true
  echo "$(( $(now) + WIFI_PENALTY_SECS ))" >"$WIFI_PENALTY_FILE" 2>/dev/null || true
  timeout 45 nmcli con up "$LTE_CON" >/dev/null 2>&1 || true
}

restore_wifi_if_due() {
  # ペナルティが切れていたら WiFi を復帰させる。watchdog が途中で死んでも
  # 次回起動時にここで自己修復する（WiFi が autoconnect=no のまま固定されない）。
  local until_ts autoc
  until_ts="$(read_int "$WIFI_PENALTY_FILE")"
  autoc="$(nmcli -g connection.autoconnect con show "$WIFI_CON" 2>/dev/null)"
  if [ "$until_ts" -gt 0 ] && [ "$(now)" -lt "$until_ts" ]; then
    return  # ペナルティ継続中
  fi
  # ペナルティ切れ、または記録なし。autoconnect が no なら戻す。
  if [ "$autoc" = "no" ]; then
    log_line "WiFi ペナルティ終了 -- wlan0 を復帰 (autoconnect=yes)"
    nmcli con mod "$WIFI_CON" connection.autoconnect yes >/dev/null 2>&1 || true
    nmcli con up "$WIFI_CON" >/dev/null 2>&1 || true
  fi
  [ "$until_ts" -gt 0 ] && rm -f "$WIFI_PENALTY_FILE"
}

act_modem_reset() {
  record_action "モデム再初期化 (nmcli radio wwan off/on)"
  nmcli radio wwan off >/dev/null 2>&1 || true
  sleep 3
  nmcli radio wwan on  >/dev/null 2>&1 || true
  sleep 8
  timeout 45 nmcli con up "$LTE_CON" >/dev/null 2>&1 || true
}

act_restart_nm() {
  record_action "systemctl restart NetworkManager ModemManager"
  systemctl restart ModemManager >/dev/null 2>&1 || true
  systemctl restart NetworkManager >/dev/null 2>&1 || true
  sleep 8
}

act_restart_tailscale() {
  record_action "systemctl restart tailscaled"
  systemctl restart tailscaled >/dev/null 2>&1 || true
  sleep 5
}

cam_is_busy() { # 録画/送信中か（videos/ の最近更新で判定）
  local vdir="$CAM_HOME/videos" f age
  [ -d "$vdir" ] || return 1
  while IFS= read -r f; do
    age=$(( $(now) - $(stat -c %Y "$f" 2>/dev/null || echo 0) ))
    if [ "$age" -ge 0 ] && [ "$age" -lt "$CAM_ACTIVE_WINDOW" ]; then
      return 0
    fi
  done < <(find "$vdir" -maxdepth 1 -name '*.mp4' 2>/dev/null)
  return 1
}

act_reboot() {
  local last_reboot elapsed
  last_reboot="$(read_int "$LAST_REBOOT_FILE")"
  if [ "$last_reboot" -gt 0 ]; then
    elapsed=$(( $(now) - last_reboot ))
    if [ "$elapsed" -lt "$REBOOT_MIN_INTERVAL" ]; then
      log_line "reboot 抑止: 前回 reboot から ${elapsed}s (< ${REBOOT_MIN_INTERVAL}s)。再起動ループ防止のため見送る"
      return
    fi
  fi
  if cam_is_busy; then
    log_line "reboot 保留: 録画/アップロード中とみられる (videos/ が直近更新)。次周期に持ち越す"
    return
  fi
  record_action "!!! 最後の手段として reboot を実行 !!!"
  echo "$(now)" >"$LAST_REBOOT_FILE" 2>/dev/null || true
  sync
  systemctl reboot
}

# ---- メイン ---------------------------------------------------------------
main() {
  # 0) WiFi ペナルティの後始末（健全でも壊れていても最初に必ず）
  restore_wifi_if_due

  local fail first_fail
  fail="$(read_int "$FAIL_FILE")"
  first_fail="$(read_int "$FIRST_FAIL_FILE")"

  if is_healthy; then
    local summary; summary="$(health_summary)"
    if [ "$fail" -gt 0 ]; then
      log_line "RECOVERED after $fail failure(s) [$summary]"
    fi
    echo 0 >"$FAIL_FILE"
    rm -f "$FIRST_FAIL_FILE"
    [ -s "$ONLINE_SINCE_FILE" ] || echo "$(now)" >"$ONLINE_SINCE_FILE"
    write_status "OK" "$fail"
    return 0
  fi

  # --- ここから不健全 ---
  rm -f "$ONLINE_SINCE_FILE"
  fail=$(( fail + 1 ))
  echo "$fail" >"$FAIL_FILE"
  if [ "$first_fail" -eq 0 ]; then
    first_fail="$(now)"; echo "$first_fail" >"$FIRST_FAIL_FILE"
  fi
  local down_secs=$(( $(now) - first_fail ))
  local summary; summary="$(health_summary)"
  log_line "UNHEALTHY fail=$fail down=${down_secs}s [$summary]"
  write_status "NG" "$fail"

  # 30 分以上ずっと駄目なら（段位に関わらず）reboot を検討
  if [ "$down_secs" -ge "$REBOOT_AFTER_SECS" ]; then
    act_reboot
    recheck_and_reset "$fail"
    return 0
  fi

  case "$fail" in
    1) log_line "段階1: 観測のみ（一過性の可能性）" ;;
    2) act_lte_up ;;
    3) act_wifi_demote ;;
    4) act_modem_reset ;;
    5) act_restart_nm ;;
    6) act_restart_tailscale ;;
    *)
      # 7 回目以降、30 分の reboot 閾値に達するまで手を変えて叩き続ける
      case $(( fail % 3 )) in
        0) act_restart_nm ;;
        1) act_lte_up ;;
        2) act_modem_reset ;;
      esac
      ;;
  esac

  recheck_and_reset "$fail"
}

recheck_and_reset() {
  local prev_fail="$1"
  [ "$prev_fail" -le 1 ] && return 0   # 段階1 は措置なし=再判定不要
  sleep "$RECHECK_SLEEP"
  if is_healthy; then
    log_line "RECOVERED by escalation step $prev_fail [$(health_summary)]"
    echo 0 >"$FAIL_FILE"
    rm -f "$FIRST_FAIL_FILE"
    echo "$(now)" >"$ONLINE_SINCE_FILE"
    write_status "OK" 0
  else
    write_status "NG" "$prev_fail"
  fi
}

write_status() { # net-status.sh がそのまま読める key=value スナップショット
  local verdict="$1" fail="$2"
  {
    echo "verdict=$verdict"
    echo "fail=$fail"
    echo "checked_at=$(now)"
    echo "route=$(default_route_dev)"
    echo "$(health_summary)"
    echo "online_since=$(read_int "$ONLINE_SINCE_FILE")"
  } >"$STATUS_FILE" 2>/dev/null || true
}

main "$@"
