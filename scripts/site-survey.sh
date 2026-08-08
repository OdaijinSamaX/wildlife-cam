#!/usr/bin/env bash
# site-survey.sh -- 設置候補地の「使えるか」を 1 分で測る現地調査ツール。
# 非プログラマ向け。WiFi 電波・LTE 電波・実サイズ相当のアップロード疎通を続けて測り、
# 最後に「最小BOM可 / LTE単独(要注意) / 設置不可」を一言で判定する。
#
# 使い方（母艦から / Tailscale 経由）:
#   ssh wildlife-zero-ts '~/wildlife-cam/scripts/site-survey.sh "候補地A"'
# Pi 上で直接:
#   ~/wildlife-cam/scripts/site-survey.sh "候補地A"
#
# 引数:
#   $1  候補地名（記録用。省略可）
# 環境変数（省略時は既定値）:
#   SURVEY_UPLOAD_MB   アップロード試験のサイズ MB（既定 3 = 実クリップ約1本ぶん）
#   SURVEY_UPLOAD_URL  アップロード先。既定は公開の速度計測サーバ（秘密情報なし）。
#                      実運用の送信先で測りたい上級者向けに差し替え可。
#   SURVEY_TIMEOUT     アップロードの打ち切り秒数（既定 45。全体を約1分に収める）

set -uo pipefail

SITE="${1:-（未記入）}"
UPLOAD_MB="${SURVEY_UPLOAD_MB:-3}"
UPLOAD_URL="${SURVEY_UPLOAD_URL:-https://speed.cloudflare.com/__up}"
TIMEOUT="${SURVEY_TIMEOUT:-45}"
LTE_NETIF="wwan0"
BUDGET_MB_PER_HOUR="${WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR:-250}"

# 端末に出すときだけ色を付ける（パイプ/キャプチャ時は生のまま）
if [ -t 1 ]; then
  OK="\e[32m【OK】\e[0m"; NG="\e[31m【NG】\e[0m"; WARN="\e[33m【注意】\e[0m"
else
  OK="【OK】"; NG="【NG】"; WARN="【注意】"
fi

echo "======================================================"
echo " wildlife-cam 設置候補地 電波調査   $(date '+%Y-%m-%d %H:%M:%S %Z')"
echo " 候補地: $SITE"
echo "======================================================"

# --- 1. WiFi 電波（強い順に上位を表示） -----------------------------------
echo "■ 1. WiFi 電波"
wifi_top_ssid=""; wifi_top_signal=-1
if command -v nmcli >/dev/null 2>&1; then
  # 再スキャンして SIGNAL(0-100) の強い順に。IN-USE(*)/SSID/SIGNAL/BARS/CHAN。
  wifi_raw="$(nmcli --terse --fields IN-USE,SIGNAL,SSID,BARS,CHAN dev wifi list --rescan yes 2>/dev/null \
             | sort -t: -k2 -nr)"
  if [ -n "$wifi_raw" ]; then
    printf "   %-4s %-6s %-24s %-6s %s\n" "使用" "電波%" "SSID" "強さ" "CH"
    n=0
    while IFS=: read -r inuse signal ssid bars chan; do
      [ -z "${signal:-}" ] && continue
      mark=" "; [ "$inuse" = "*" ] && mark="*"
      [ -z "$ssid" ] && ssid="(非公開/不明)"
      printf "   %-4s %-6s %-24s %-6s %s\n" "$mark" "$signal" "$ssid" "$bars" "$chan"
      if [ "$n" -eq 0 ]; then wifi_top_ssid="$ssid"; wifi_top_signal="$signal"; fi
      n=$((n+1)); [ "$n" -ge 8 ] && break
    done <<< "$wifi_raw"
    if [ "$wifi_top_signal" -ge 55 ] 2>/dev/null; then
      echo -e "   => 最強: $wifi_top_ssid  電波 ${wifi_top_signal}%  $OK（既設WiFi至近とみなせる）"
    elif [ "$wifi_top_signal" -ge 40 ] 2>/dev/null; then
      echo -e "   => 最強: $wifi_top_ssid  電波 ${wifi_top_signal}%  $WARN（境界。数十cm動かすと変わる。要接続確認）"
    else
      echo -e "   => 最強: ${wifi_top_ssid:-なし}  電波 ${wifi_top_signal}%  $NG（WiFi は当てにできない）"
    fi
  else
    echo -e "   $NG WiFi が 1 つも見えません（電波なし、または nmcli 権限なし）"
  fi
else
  echo -e "   $NG nmcli がありません（Pi 以外で実行していませんか）"
fi

echo "------------------------------------------------------"
# --- 2. LTE 電波と現在の回線 ----------------------------------------------
echo "■ 2. LTE 電波"
route_dev="$(ip -o route show default 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="dev"){print $(i+1); exit}}')"
case "$route_dev" in
  wlan0)          route_jp="WiFi (wlan0)" ;;
  "$LTE_NETIF")   route_jp="LTE (wwan0)" ;;
  "")             route_jp="経路なし(!)" ;;
  *)              route_jp="$route_dev" ;;
esac
echo "   現在の通信回線: $route_jp"

lte_sig_num=-1
lte="$(mmcli -m any 2>/dev/null)"
if [ -n "$lte" ]; then
  sig="$(echo "$lte" | grep -m1 'signal quality' | sed -E 's/.*: *([0-9]+)%.*/\1/')"
  op="$(echo "$lte"  | grep -m1 'operator name'  | sed -E 's/.*: *//')"
  at="$(echo "$lte"  | grep -m1 'access tech'    | sed -E 's/.*: *//')"
  [ -n "$sig" ] && lte_sig_num="$sig"
  if [ "$lte_sig_num" -ge 40 ] 2>/dev/null; then
    echo -e "   LTE 電波: ${lte_sig_num}%  (${at:-?}, ${op:-?})  $OK"
  elif [ "$lte_sig_num" -ge 20 ] 2>/dev/null; then
    echo -e "   LTE 電波: ${lte_sig_num}%  (${at:-?}, ${op:-?})  $WARN（弱い。送信が遅くなりがち）"
  else
    echo -e "   LTE 電波: ${lte_sig_num:-?}%  (${at:-?}, ${op:-?})  $NG（LTE も当てにできない）"
  fi
else
  echo -e "   $NG LTE モデムが見つかりません"
fi

echo "------------------------------------------------------"
# --- 3. インターネット疎通（実際に外へ出られるか） -------------------------
echo "■ 3. インターネット疎通"
dns_rc=1; l7_rc=1
timeout 6 getent ahostsv4 www.google.com >/dev/null 2>&1 && dns_rc=0
code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 6 http://connectivitycheck.gstatic.com/generate_204 2>/dev/null)" || code=""
[ "$code" = "204" ] && l7_rc=0
online=1
if [ "$dns_rc" -eq 0 ] && [ "$l7_rc" -eq 0 ]; then
  online=0
  echo -e "   $OK オンライン（名前解決・外部到達ともに成功）"
else
  echo -e "   $NG オフライン（DNS=$( [ $dns_rc -eq 0 ] && echo OK || echo NG ) / 外部到達=$( [ $l7_rc -eq 0 ] && echo OK || echo NG )）"
fi

echo "------------------------------------------------------"
# --- 4. 実サイズ相当アップロード疎通（約1分） -----------------------------
echo "■ 4. アップロード実測（${UPLOAD_MB}MB を送って速度を測る）"
up_mbps=""; up_verdict="$NG"; up_note="未実施"
if [ "$online" -ne 0 ]; then
  echo -e "   $WARN オフラインのため送信試験はスキップします"
  up_note="オフラインでスキップ"
else
  bytes=$(( UPLOAD_MB * 1024 * 1024 ))
  payload="$(mktemp /tmp/site-survey.XXXXXX)"
  # 圧縮で速度が水増しされないよう乱数で埋める（実動画に近い非圧縮データ）
  head -c "$bytes" /dev/urandom > "$payload" 2>/dev/null
  echo "   送信中… (最大 ${TIMEOUT} 秒で打ち切り)"
  metrics="$(curl -s -o /dev/null --max-time "$TIMEOUT" \
             -w '%{http_code} %{size_upload} %{speed_upload} %{time_total}' \
             -X POST --data-binary @"$payload" "$UPLOAD_URL" 2>/dev/null)" || metrics=""
  rm -f "$payload"
  http_code="$(echo "$metrics" | awk '{print $1}')"
  size_up="$(echo "$metrics" | awk '{print $2}')"
  speed_up="$(echo "$metrics" | awk '{print $3}')"   # bytes/sec
  time_total="$(echo "$metrics" | awk '{print $4}')"
  if [ -n "$speed_up" ] && awk "BEGIN{exit !($speed_up>0)}" 2>/dev/null; then
    up_mbps="$(awk "BEGIN{printf \"%.2f\", $speed_up*8/1000000}")"
    sent_mb="$(awk "BEGIN{printf \"%.1f\", ${size_up:-0}/1048576}")"
    echo "   実測: ${up_mbps} Mbps  （${sent_mb}MB を ${time_total}s で送信, HTTP ${http_code:-?}）"
    # 夜間12時間 最大3GB を送り切るのに必要な時間の目安
    night_min="$(awk "BEGIN{printf \"%.0f\", 3072*8/($up_mbps)/60}")"
    echo "   目安: 3GB(夜間最大)を送るのに約 ${night_min} 分ぶんの上り速度"
    if awk "BEGIN{exit !($up_mbps>=2)}"; then
      up_verdict="$OK"; up_note="十分（${up_mbps} Mbps）"
    elif awk "BEGIN{exit !($up_mbps>=0.5)}"; then
      up_verdict="$WARN"; up_note="ぎりぎり（${up_mbps} Mbps／送信予算に依存）"
    else
      up_verdict="$NG"; up_note="遅すぎ（${up_mbps} Mbps／貯まる一方）"
    fi
    echo -e "   => 判定: $up_verdict $up_note"
  else
    echo -e "   $NG 送信できませんでした（HTTP ${http_code:-なし}／時間切れの可能性）"
    up_note="送信失敗/時間切れ"
  fi
fi

echo "======================================================"
# --- 5. 総合判定マトリクス ------------------------------------------------
echo "■ 総合判定"
wifi_close=0; [ "$wifi_top_signal" -ge 55 ] 2>/dev/null && [ "$online" -eq 0 ] && wifi_close=1
lte_usable=0; [ "$lte_sig_num" -ge 20 ] 2>/dev/null && lte_usable=1
up_fast=0; [ -n "$up_mbps" ] && awk "BEGIN{exit !($up_mbps>=0.5)}" && up_fast=1

if [ "$wifi_close" -eq 1 ]; then
  echo -e "   $OK 【最小BOM可】既設WiFi至近。¥1〜2万円台の最小構成で設置可。"
  echo "      WiFi 接続時は送信量の上限なし（LTE 課金の心配なし）。まず WiFi へ接続設定を。"
elif [ "$online" -eq 0 ] && [ "$lte_usable" -eq 1 ] && [ "$up_fast" -eq 1 ]; then
  echo -e "   $WARN 【LTE単独・要注意】WiFi は弱いが LTE で運用可。ただし従量課金に注意。"
  echo "      送信量上限は既定 ${BUDGET_MB_PER_HOUR}MB/時（夜間12hで最大約3GB）。"
  echo "      詳細は docs/upload-budget.md / field_limits.py を参照。上限は WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR で調整可。"
else
  echo -e "   $NG 【設置不可】WiFi も LTE も実用に足りません。別の候補地を探してください。"
  echo "      （数十cm〜数m 動かす、地上高を上げる、窓/開けた方角へ向ける、で改善することがあります）"
fi

echo "------------------------------------------------------"
# --- 6. 記録用サマリ（この行をそのまま控える） ---------------------------
echo "■ 記録用（スマホに控える1行）"
wifi_disp="${wifi_top_signal}%"; [ "$wifi_top_signal" -lt 0 ] 2>/dev/null && wifi_disp="なし"
lte_disp="${lte_sig_num}%"; [ "$lte_sig_num" -lt 0 ] 2>/dev/null && lte_disp="なし"
echo "   候補地=$SITE / WiFi=${wifi_top_ssid:-なし}(${wifi_disp}) / LTE=${lte_disp} / オンライン=$( [ $online -eq 0 ] && echo OK || echo NG ) / 上り=${up_mbps:-計測不可}Mbps"
echo "======================================================"
