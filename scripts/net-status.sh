#!/usr/bin/env bash
# net-status.sh -- いまネットにつながっているかを日本語で 1 画面表示する。
# 非プログラマ向け。OK / NG が一目で分かることを最優先にする。
#
# 使い方（母艦から）:  ssh wildlife-zero-ts '~/wildlife-cam/scripts/net-status.sh'
#           Pi 上で:  ~/wildlife-cam/scripts/net-status.sh

set -uo pipefail

STATE_DIR="/run/wildlife-netwatch"
STATUS_FILE="$STATE_DIR/status"
LAST_ACTION_FILE="$STATE_DIR/last_action"
LAST_REBOOT_FILE="/var/lib/wildlife-netwatch/last_reboot_epoch"
LOG="/var/log/wildlife-net.log"

LTE_NETIF="wwan0"

now() { date +%s; }

# 秒数を「Xd Yh Zm」形式の日本語に
human_dur() {
  local s="${1:-0}" d h m
  [ "$s" -lt 0 ] 2>/dev/null && s=0
  d=$(( s / 86400 )); s=$(( s % 86400 ))
  h=$(( s / 3600 )); s=$(( s % 3600 ))
  m=$(( s / 60 ))
  local out=""
  [ "$d" -gt 0 ] && out="${out}${d}日"
  [ "$h" -gt 0 ] && out="${out}${h}時間"
  out="${out}${m}分"
  echo "$out"
}

epoch_to_jst() { # epoch -> "MM/DD HH:MM"、0/空なら "なし"
  local e="${1:-0}"
  case "$e" in ''|0|*[!0-9]*) echo "なし"; return ;; esac
  date -d "@$e" '+%m/%d %H:%M'
}

# 端末に出すときだけ色を付ける（パイプ/キャプチャ時に生のエスケープを見せない）
if [ -t 1 ]; then
  OK="\e[32m【OK】\e[0m"; NG="\e[31m【NG】\e[0m"
else
  OK="【OK】"; NG="【NG】"
fi
ok_ng() { [ "$1" -eq 0 ] 2>/dev/null && echo -e "$OK" || echo -e "$NG"; }

echo "======================================================"
echo " wildlife-zero ネットワーク状態   $(date '+%Y-%m-%d %H:%M:%S')"
echo "======================================================"

# --- 1. どの回線で外に出ているか ---
route_dev="$(ip -o route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
case "$route_dev" in
  wlan0)  route_jp="WiFi (wlan0)" ;;
  "$LTE_NETIF"|wwan0) route_jp="LTE (wwan0)" ;;
  "")     route_jp="経路なし(!)" ;;
  *)      route_jp="$route_dev" ;;
esac
echo " 現在の通信回線 : $route_jp"

# --- 2. 実際に外に出られるか（その場で確認） ---
dns_rc=1; l7_rc=1
timeout 6 getent ahostsv4 www.google.com >/dev/null 2>&1 && dns_rc=0
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://connectivitycheck.gstatic.com/generate_204 2>/dev/null)" || code=""
[ "$code" = "204" ] && l7_rc=0
printf " 名前解決(DNS) : %b\n" "$(ok_ng $dns_rc)"
printf " インターネット: %b\n" "$(ok_ng $l7_rc)"
if [ "$dns_rc" -eq 0 ] && [ "$l7_rc" -eq 0 ]; then
  echo " => 総合判定    : オンライン ✅"
else
  echo " => 総合判定    : オフライン ❌（下の watchdog が自動で復旧を試みます）"
fi

echo "------------------------------------------------------"
# --- 3. LTE の状態 ---
lte="$(mmcli -m any 2>/dev/null)"
if [ -n "$lte" ]; then
  sig="$(echo "$lte"  | grep -m1 'signal quality' | sed -E 's/.*: *([0-9]+%).*/\1/')"
  op="$(echo "$lte"   | grep -m1 'operator name'  | sed -E 's/.*: *//')"
  st="$(echo "$lte"   | grep -m1 '  state'        | sed -E 's/.*: *//; s/\x1b\[[0-9;]*m//g')"
  at="$(echo "$lte"   | grep -m1 'access tech'    | sed -E 's/.*: *//')"
  apn="$(nmcli -g gsm.apn con show lte-his 2>/dev/null)"
  echo " LTE 状態      : ${st:-不明}  電波 ${sig:-?}  (${at:-?})"
  echo " LTE 接続先    : ${op:-不明}   APN ${apn:-?}"
else
  echo " LTE 状態      : モデムが見つかりません(!)"
fi

echo "------------------------------------------------------"
# --- 4. watchdog の直近判定と復旧履歴 ---
if [ -r "$STATUS_FILE" ]; then
  # shellcheck disable=SC1090
  verdict=""; fail=""; checked_at=""; online_since=""
  while IFS='=' read -r k v; do
    case "$k" in
      verdict) verdict="$v" ;;
      fail) fail="$v" ;;
      checked_at) checked_at="$v" ;;
      online_since) online_since="$v" ;;
    esac
  done <"$STATUS_FILE"
  vj="$verdict"; [ "$verdict" = "OK" ] && vj="正常" ; [ "$verdict" = "NG" ] && vj="異常(連続${fail}回)"
  echo " 監視の直近判定: ${vj:-不明}   （$(epoch_to_jst "${checked_at:-0}") 時点）"
  if [ -n "${online_since:-}" ] && [ "${online_since:-0}" -gt 0 ] 2>/dev/null; then
    echo " 連続オンライン: $(human_dur $(( $(now) - online_since )))"
  else
    echo " 連続オンライン: （現在オフライン、または起動直後）"
  fi
else
  echo " 監視の直近判定: watchdog がまだ動いていません"
fi

if [ -r "$LAST_ACTION_FILE" ]; then
  a_ts="$(cut -f1 "$LAST_ACTION_FILE" 2>/dev/null)"
  a_msg="$(cut -f2- "$LAST_ACTION_FILE" 2>/dev/null)"
  echo " 最後の復旧措置: $(epoch_to_jst "${a_ts:-0}")  $a_msg"
else
  echo " 最後の復旧措置: なし（一度も介入していない＝安定）"
fi
echo " 最後の再起動  : $(epoch_to_jst "$(cat "$LAST_REBOOT_FILE" 2>/dev/null || echo 0)") (watchdog 起因)"

echo "------------------------------------------------------"
# --- 5. 直近の障害履歴（ログから NG/RECOVERED/ACTION を抜粋） ---
echo " 直近のできごと (新しい順):"
if [ -r "$LOG" ]; then
  grep -E 'UNHEALTHY|RECOVERED|ACTION|reboot' "$LOG" 2>/dev/null | tail -n 6 | tac \
    | sed 's/^/   /' || echo "   （記録なし）"
  [ -s "$LOG" ] || echo "   （まだ記録がありません）"
else
  echo "   （ログファイルがまだありません）"
fi
echo "======================================================"
