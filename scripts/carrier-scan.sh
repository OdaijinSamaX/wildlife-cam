#!/usr/bin/env bash
# carrier-scan.sh -- 設置候補地で「どのキャリアの電波が届くか」を全網まとめて測る。
#
# ねらい:
#   手持ちの SIM は docomo 系だけだが、Quectel EG25-G の AT+QSCAN は SIM の契約網に
#   関係なく周囲の全 PLMN のセルを RSRP/RSRQ 付きで列挙できる（firmware 依存）。
#   これを 1 コマンドにして、現地で「この場所で使える網」を非プログラマでも判定できる
#   ようにする。QSCAN 非対応 firmware では AT+COPS=? に自動フォールバックし、
#   在圏 PLMN と接続方式（LTE/3G/GSM）だけでも表示する。
#
# 使い方（母艦から / Tailscale 経由・root 必須）:
#   ssh wildlife-zero-ts 'sudo ~/wildlife-cam/scripts/carrier-scan.sh "候補地A"'
# Pi 上で直接:
#   sudo ~/wildlife-cam/scripts/carrier-scan.sh "候補地A"
#
# 引数:
#   $1                候補地名（記録用。省略可）
# オプション:
#   --yes             確認プロンプトを省略（無人・スクリプト実行用）
#   --dry-run         実機を一切触らず、何をするかだけ表示（安全な下見）
#   --self-test       AT を発行せず、内蔵の QSCAN/COPS サンプルでパーサを自己検証
#   --port <dev>      AT ポートを明示（既定は自動検出→ EG25 は通常 /dev/ttyUSB2）
#   --timeout <sec>   QSCAN のスキャン秒数（既定 60）
#
# ⚠ 所要時間と注意:
#   スキャン中は ModemManager を止めて AT ポートを占有するため、LTE が
#   おおむね 1〜3 分切れます。終了時に ModemManager と watchdog(timer) を必ず
#   元へ戻し、lte-his が再接続するのを待ってから結果を表示します（trap で保証）。
#   スキャン中の watchdog 誤発動を防ぐため wildlife-netwatch.timer も一時停止します。
#
# 判定基準（LTE セルの最良 RSRP）:
#   >= -100dBm ◎ / -110 ○ / -120 △ / それ未満 or 不検出 ×
#
# 依存: bash, stty, systemctl, mmcli(検出用), nmcli(復帰確認用)。追加パッケージ不要。
# 関連: 現地調査全体の手順は docs/site-survey-protocol.md（PR #6）で扱う。本スクリプトは
#       その「電波の到達キャリア」を測る道具で、記録 1 行は site-survey.sh と同じ流儀。

set -uo pipefail

# ---- 既定値・定数 ---------------------------------------------------------
AT_PORT="${EG25_AT_PORT:-}"          # 空なら自動検出
AT_PORT_CANDIDATES=(/dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1 /dev/ttyUSB0)
QSCAN_TIMEOUT=60                     # AT+QSCAN=3,<timeout> のスキャン秒数
LTE_CON="lte-his"                    # 復帰確認する NM プロファイル
NETWATCH_TIMER="wildlife-netwatch.timer"
MM_SERVICE="ModemManager.service"
APP_HOME="${WILDLIFE_CAM_HOME:-$HOME/wildlife-cam}"
RECONNECT_WAIT=60                    # 復帰後 lte-his 再接続をこの秒数まで待つ

SITE="（未記入）"
ASSUME_YES=0
DRY_RUN=0
SELF_TEST=0

# 端末に出すときだけ色を付ける（パイプ/キャプチャ時は生のまま）
if [ -t 1 ]; then
  OK="\e[32m【OK】\e[0m"; NG="\e[31m【NG】\e[0m"; WARN="\e[33m【注意】\e[0m"
else
  OK="【OK】"; NG="【NG】"; WARN="【注意】"
fi

now() { date +%s; }
say() { echo -e "$*"; }

# ---- 引数パース -----------------------------------------------------------
parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --yes|-y)      ASSUME_YES=1 ;;
      --dry-run)     DRY_RUN=1 ;;
      --self-test)   SELF_TEST=1 ;;
      --port)        shift; AT_PORT="${1:-}" ;;
      --timeout)     shift; QSCAN_TIMEOUT="${1:-60}" ;;
      -h|--help)     grep -E '^#' "$0" | grep -v '^#!' | sed -E 's/^# ?//'; exit 0 ;;
      --*)           echo "不明なオプション: $1" >&2; exit 2 ;;
      *)             SITE="$1" ;;
    esac
    shift
  done
}

# ===========================================================================
# パーサ部（実機非依存・自己検証対象）
# ===========================================================================

# MCC/MNC からキャリアの内部キーを返す。未知は "other:MCC-MNC"。
# 日本の主要 PLMN のみ対応（docomo は複数 MNC、au/KDDI も複数 MNC を持つ）。
carrier_key() {
  local mcc="$1" mnc="$2"
  # MNC はゼロ詰め 2 桁で来る想定だが、念のため数値化して比較する。
  local m=$((10#${mnc:-99}))
  if [ "$mcc" != "440" ] && [ "$mcc" != "441" ]; then
    printf 'other:%s-%s\n' "$mcc" "$mnc"; return
  fi
  case "$m" in
    0|1|2|3|9|10|12|13|14|15|49) echo docomo ;;      # NTT docomo
    50|51|52|53|54|70|71|72|73|74|75|76) echo au ;;  # KDDI / 沖縄セルラー
    20|21|4|6|161|162|163|164|165) echo softbank ;;  # SoftBank / WCP
    11) echo rakuten ;;                              # 楽天モバイル
    *) printf 'other:%s-%s\n' "$mcc" "$mnc" ;;
  esac
}

# 内部キー → 表示名
carrier_label() {
  case "$1" in
    docomo)   echo "docomo" ;;
    au)       echo "au(KDDI)" ;;
    softbank) echo "SoftBank" ;;
    rakuten)  echo "楽天(Rakuten)" ;;
    other:*)  echo "その他(${1#other:})" ;;
    *)        echo "$1" ;;
  esac
}

# LTE の DL EARFCN → バンド番号（日本で使う主要バンドのみ）。不明は空。
earfcn_to_band() {
  local e="${1:-}"
  case "$e" in ''|*[!0-9]*) echo ""; return ;; esac
  if   [ "$e" -ge 0     ] && [ "$e" -le 599   ]; then echo "B1"
  elif [ "$e" -ge 1200  ] && [ "$e" -le 1949  ]; then echo "B3"
  elif [ "$e" -ge 2750  ] && [ "$e" -le 3449  ]; then echo "B7"
  elif [ "$e" -ge 3450  ] && [ "$e" -le 3799  ]; then echo "B8"
  elif [ "$e" -ge 4750  ] && [ "$e" -le 4949  ]; then echo "B11"
  elif [ "$e" -ge 5850  ] && [ "$e" -le 5999  ]; then echo "B18"
  elif [ "$e" -ge 6000  ] && [ "$e" -le 6149  ]; then echo "B19"
  elif [ "$e" -ge 6150  ] && [ "$e" -le 6449  ]; then echo "B20"
  elif [ "$e" -ge 8690  ] && [ "$e" -le 9039  ]; then echo "B26"
  elif [ "$e" -ge 9210  ] && [ "$e" -le 9659  ]; then echo "B28"
  elif [ "$e" -ge 39650 ] && [ "$e" -le 41589 ]; then echo "B41"
  elif [ "$e" -ge 41590 ] && [ "$e" -le 43589 ]; then echo "B42"
  else echo "B?"
  fi
}

# RSRP 生値 → dBm。EG25 の QSCAN は実 dBm(負値)で返すのが通常。
# 非負の値は 3GPP の RSRP インデックス(0..97)とみなし dBm=idx-140 で換算する。
normalize_rsrp() {
  local v="${1:-}"
  case "$v" in
    ''|*[!0-9-]*) echo ""; return ;;
    -*) echo "$v"; return ;;                 # 既に dBm（負値）
    *)  if [ "$v" -le 97 ]; then echo $(( v - 140 )); else echo "-$v"; fi ;;
  esac
}

# RSRP(dBm) → ◎/○/△/×。空/不明は ×。
rate_rsrp() {
  local d="${1:-}"
  case "$d" in ''|*[!0-9-]*) echo "×"; return ;; esac
  if   [ "$d" -ge -100 ]; then echo "◎"
  elif [ "$d" -ge -110 ]; then echo "○"
  elif [ "$d" -ge -120 ]; then echo "△"
  else echo "×"
  fi
}

# QSCAN 生出力(stdin) → TSV: rat<TAB>carrier<TAB>rsrp_dbm<TAB>rsrq<TAB>band<TAB>earfcn<TAB>pci
# 行例: +QSCAN: "LTE",440,10,1500,300,-92,-9,...
# GSM/WCDMA は信号カラム位置が違うため、キャリア検出(mcc/mnc)のみ拾い信号は空にする。
parse_qscan() {
  local line rest type mcc mnc earfcn pci rsrp rsrq
  while IFS= read -r line; do
    case "$line" in
      *'+QSCAN:'*) ;;
      *) continue ;;
    esac
    rest="${line#*+QSCAN:}"
    rest="${rest#"${rest%%[![:space:]]*}"}"   # 先頭空白を除去
    # カンマ分割（IFS を局所化）
    local IFS=','
    # shellcheck disable=SC2206
    local f=($rest)
    unset IFS
    type="${f[0]//\"/}"; type="${type//[[:space:]]/}"
    mcc="${f[1]:-}"; mcc="${mcc//[[:space:]]/}"
    mnc="${f[2]:-}"; mnc="${mnc//[[:space:]]/}"
    [ -z "$mcc" ] || [ -z "$mnc" ] && continue
    local key; key="$(carrier_key "$mcc" "$mnc")"
    case "$type" in
      LTE|NR5G|NR)
        earfcn="${f[3]:-}"; earfcn="${earfcn//[[:space:]]/}"
        pci="${f[4]:-}";    pci="${pci//[[:space:]]/}"
        rsrp="${f[5]:-}";   rsrp="${rsrp//[[:space:]]/}"
        rsrq="${f[6]:-}";   rsrq="${rsrq//[[:space:]]/}"
        rsrp="$(normalize_rsrp "$rsrp")"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
          "$type" "$key" "$rsrp" "$rsrq" "$(earfcn_to_band "$earfcn")" "$earfcn" "$pci"
        ;;
      *)
        # 2G/3G は信号を空にして検出のみ記録
        printf '%s\t%s\t\t\t\t\t\n' "$type" "$key"
        ;;
    esac
  done
}

# COPS 生出力(stdin) → TSV: carrier<TAB>act_label
# 行例: +COPS: (2,"NTT DOCOMO","DOCOMO","44010",7),(1,"KDDI","au","44051",7),,(0-4),(0-2)
parse_cops() {
  local raw grp inside numeric act mcc mnc key
  raw="$(cat)"
  # "(...)" のグループを 1 つずつ取り出す
  while [ -n "$raw" ]; do
    case "$raw" in
      *'('*')'*) ;;
      *) break ;;
    esac
    grp="${raw#*(}"; grp="${grp%%)*}"; raw="${raw#*)}"
    # grp = stat,"long","short","numeric",act
    inside="$grp"
    local IFS=','
    # shellcheck disable=SC2206
    local c=($inside)
    unset IFS
    numeric="${c[3]:-}"; numeric="${numeric//\"/}"; numeric="${numeric//[[:space:]]/}"
    act="${c[4]:-}"; act="${act//[[:space:]]/}"
    case "$numeric" in ''|*[!0-9]*) continue ;; esac
    mcc="${numeric:0:3}"; mnc="${numeric:3}"
    key="$(carrier_key "$mcc" "$mnc")"
    local act_label
    case "$act" in
      0|1|3) act_label="GSM/2G" ;;
      2|4|5|6) act_label="3G" ;;
      7) act_label="LTE" ;;
      11|12|13) act_label="5G" ;;
      *) act_label="方式${act:-?}" ;;
    esac
    printf '%s\t%s\n' "$key" "$act_label"
  done
}

# ===========================================================================
# 集計とレポート
# ===========================================================================

# 表示順（既知キャリア→その他）
ORDER=(docomo au softbank rakuten)

# QSCAN の TSV(stdin) を集計してレポートを出力
render_qscan_report() {
  local tsv; tsv="$(cat)"
  declare -A best_rsrp best_rsrq best_band seen_lte seen_other
  local order_dyn=("${ORDER[@]}")

  local rat key rsrp rsrq band earfcn pci
  while IFS=$'\t' read -r rat key rsrp rsrq band earfcn pci; do
    [ -z "${key:-}" ] && continue
    # 未知キャリアも順序に追加（重複回避）
    case " ${order_dyn[*]} " in *" $key "*) ;; *) order_dyn+=("$key") ;; esac
    if [ -n "$rsrp" ]; then
      seen_lte["$key"]=1
      if [ -z "${best_rsrp[$key]:-}" ] || [ "$rsrp" -gt "${best_rsrp[$key]}" ]; then
        best_rsrp["$key"]="$rsrp"; best_rsrq["$key"]="$rsrq"; best_band["$key"]="$band"
      fi
    else
      seen_other["$key"]="${seen_other[$key]:+${seen_other[$key]},}$rat"
    fi
  done <<< "$tsv"

  say "■ キャリア別 最良セル（LTE/5G）"
  printf "   %-14s %-7s %-8s %-6s %s\n" "キャリア" "判定" "RSRP" "RSRQ" "バンド"
  local k label rdbm mark rq bd
  local -a summary_parts rec_parts
  for k in "${order_dyn[@]}"; do
    # docomo/au/softbank/rakuten は必ず 1 行出す（不検出なら ×）
    label="$(carrier_label "$k")"
    if [ -n "${best_rsrp[$k]:-}" ]; then
      rdbm="${best_rsrp[$k]}"; mark="$(rate_rsrp "$rdbm")"
      rq="${best_rsrq[$k]:-?}"; bd="${best_band[$k]:-?}"
      printf "   %-14s  %-6s %-8s %-6s %s\n" "$label" "$mark" "${rdbm}dBm" "${rq}dB" "$bd"
      rec_parts+=("$(rec_name "$k")=${mark}(${rdbm}dBm)")
    elif [ -n "${seen_other[$k]:-}" ]; then
      printf "   %-14s  %-6s %-8s %-6s %s\n" "$label" "△?" "電波不明" "-" "${seen_other[$k]} のみ検出"
      rec_parts+=("$(rec_name "$k")=△?(${seen_other[$k]})")
      mark="△?"
    else
      case "$k" in
        docomo|au|softbank|rakuten)
          printf "   %-14s  %-6s %-8s %-6s %s\n" "$label" "×" "不検出" "-" "-"
          rec_parts+=("$(rec_name "$k")=×")
          mark="×" ;;
        *) continue ;;
      esac
    fi
    summary_parts+=("${label} ${mark}")
  done

  say "------------------------------------------------------"
  say "■ この場所で使える網"
  say "   $(join_by ' / ' "${summary_parts[@]}")"
  say "------------------------------------------------------"
  say "■ 記録用（スマホに控える1行）"
  say "   場所=$SITE / $(join_by ' / ' "${rec_parts[@]}") / 方式=QSCAN"
}

# COPS フォールバックのレポート
render_cops_report() {
  local tsv; tsv="$(cat)"
  declare -A act_of
  local order_dyn=("${ORDER[@]}")
  local key act
  while IFS=$'\t' read -r key act; do
    [ -z "${key:-}" ] && continue
    case " ${order_dyn[*]} " in *" $key "*) ;; *) order_dyn+=("$key") ;; esac
    # LTE を優先して残す
    if [ -z "${act_of[$key]:-}" ] || [ "$act" = "LTE" ]; then act_of["$key"]="$act"; fi
  done <<< "$tsv"

  say "■ 在圏キャリア（AT+COPS=? フォールバック / 電波強度は取得不可）"
  local k label rec_parts=() summary_parts=()
  for k in "${order_dyn[@]}"; do
    label="$(carrier_label "$k")"
    if [ -n "${act_of[$k]:-}" ]; then
      printf "   %-14s 在圏 ○（%s）\n" "$label" "${act_of[$k]}"
      summary_parts+=("${label} ○(${act_of[$k]})")
      rec_parts+=("$(rec_name "$k")=在圏(${act_of[$k]})")
    else
      case "$k" in
        docomo|au|softbank|rakuten)
          printf "   %-14s 圏外 ×\n" "$label"
          summary_parts+=("${label} ×")
          rec_parts+=("$(rec_name "$k")=×") ;;
      esac
    fi
  done
  say "------------------------------------------------------"
  say "■ この場所で使える網（在圏のみ・強度不明）"
  say "   $(join_by ' / ' "${summary_parts[@]}")"
  say "------------------------------------------------------"
  say "■ 記録用（スマホに控える1行）"
  say "   場所=$SITE / $(join_by ' / ' "${rec_parts[@]}") / 方式=COPS"
}

rec_name() { # 記録行用の短い名前
  case "$1" in docomo) echo docomo;; au) echo au;; softbank) echo SB;; rakuten) echo 楽天;; other:*) echo "${1#other:}";; *) echo "$1";; esac
}

join_by() { local sep="$1"; shift; local out="${1:-}"; shift || true; local x; for x in "$@"; do out="$out$sep$x"; done; printf '%s' "$out"; }

# ===========================================================================
# AT 実行（実機・root 必須）
# ===========================================================================

detect_at_port() {
  [ -n "$AT_PORT" ] && { [ -e "$AT_PORT" ] && return 0 || { echo "指定ポートがありません: $AT_PORT" >&2; return 1; }; }
  local p
  for p in "${AT_PORT_CANDIDATES[@]}"; do
    [ -e "$p" ] || continue
    if at_probe "$p"; then AT_PORT="$p"; return 0; fi
  done
  return 1
}

at_probe() { # ポート $1 が AT に OK を返すか
  local port="$1" out
  stty -F "$port" 115200 cs8 -cstopb -parenb raw -echo min 0 time 5 2>/dev/null || return 1
  exec 8<>"$port" 2>/dev/null || return 1
  printf 'AT\r\n' >&8 2>/dev/null || { at_close; return 1; }
  out=""
  local start=$SECONDS line
  while IFS= read -r -t 2 line <&8; do
    out+="$line"
    case "$line" in *OK*) at_close; return 0 ;; esac
    (( SECONDS - start >= 3 )) && break
  done
  at_close
  return 1
}

at_close() { exec 8>&- 2>/dev/null || true; exec 8<&- 2>/dev/null || true; }

# AT コマンド発行。$1=コマンド $2=全体タイムアウト秒。標準出力に応答本文、
# 戻り値は OK=0 / ERROR・timeout=1。
at_cmd() {
  local cmd="$1" deadline="${2:-10}" line acc="" start rc=1
  stty -F "$AT_PORT" 115200 cs8 -cstopb -parenb raw -echo min 0 time 10 2>/dev/null || return 1
  exec 8<>"$AT_PORT" 2>/dev/null || return 1
  printf '%s\r\n' "$cmd" >&8
  start=$SECONDS
  while :; do
    if IFS= read -r -t 3 line <&8; then
      line="${line%$'\r'}"
      acc+="$line"$'\n'
      case "$line" in
        OK) rc=0; break ;;
        ERROR|+CME[[:space:]]ERROR*|+CMS[[:space:]]ERROR*) rc=1; break ;;
      esac
    fi
    (( SECONDS - start >= deadline )) && { rc=1; break; }
  done
  at_close
  printf '%s' "$acc"
  return "$rc"
}

# ===========================================================================
# 復旧（trap で必ず呼ばれる・冪等）
# ===========================================================================
RESTORED=0
NETWATCH_WAS_ACTIVE=0

restore() {
  [ "$RESTORED" -eq 1 ] && return 0
  RESTORED=1
  at_close
  say ""
  say "── 後片付け（回線と watchdog を元に戻します）──"
  # 1) ModemManager を戻す
  systemctl start "$MM_SERVICE" >/dev/null 2>&1 \
    && say "$OK ModemManager を再開しました" \
    || say "$NG ModemManager の再開に失敗（手動確認: systemctl start $MM_SERVICE）"
  # 2) lte-his 再接続を待つ
  local i connected=0
  for ((i=0; i<RECONNECT_WAIT; i+=3)); do
    if nmcli -t -f NAME,DEVICE con show --active 2>/dev/null | grep -q "^${LTE_CON}:"; then
      connected=1; break
    fi
    # モデムが見えたら明示的に張り直しを試みる
    if mmcli -L 2>/dev/null | grep -qi 'Modem/'; then
      nmcli con up "$LTE_CON" >/dev/null 2>&1 || true
    fi
    sleep 3
  done
  [ "$connected" -eq 1 ] \
    && say "$OK lte-his 再接続を確認しました" \
    || say "$WARN lte-his の再接続を確認できませんでした（watchdog が自動復旧を試みます）"
  # 3) watchdog timer を戻す（元が動いていた場合のみ）
  if [ "$NETWATCH_WAS_ACTIVE" -eq 1 ]; then
    systemctl start "$NETWATCH_TIMER" >/dev/null 2>&1 \
      && say "$OK $NETWATCH_TIMER を再開しました" \
      || say "$NG $NETWATCH_TIMER の再開に失敗（手動確認: systemctl start $NETWATCH_TIMER）"
  fi
}

# ===========================================================================
# 自己検証（--self-test）: 実機に触れずパーサの妥当性を確認する
# ===========================================================================
FIXTURE_QSCAN='
AT+QSCAN=3,60
+QSCAN: "LTE",440,10,1500,300,-92,-9,150,3
+QSCAN: "LTE",440,10,6100,111,-105,-12,120,5
+QSCAN: "LTE",440,51,3750,44,-108,-11,90,7
+QSCAN: "LTE",440,20,1850,22,-118,-14,60,9
+QSCAN: "WCDMA",440,10,10700,0,-100,0
+QSCAN: "LTE",440,11,5900,7,-125,-16,40,11
OK
'
FIXTURE_COPS='+COPS: (2,"NTT DOCOMO","DOCOMO","44010",7),(1,"KDDI","au","44051",7),(1,"SoftBank","SoftBank","44020",2),(1,"Rakuten","Rakuten","44011",7),,(0-4),(0-2)
OK'

self_test() {
  local pass=0 fail=0
  check() { # $1=説明 $2=実際 $3=期待
    if [ "$2" = "$3" ]; then pass=$((pass+1)); say "$OK $1"; else fail=$((fail+1)); say "$NG $1  期待='$3' 実際='$2'"; fi
  }

  say "== ユニット: carrier_key / earfcn_to_band / normalize_rsrp / rate_rsrp =="
  check "440-10 → docomo"          "$(carrier_key 440 10)"   "docomo"
  check "440-51 → au"              "$(carrier_key 440 51)"   "au"
  check "440-20 → softbank"        "$(carrier_key 440 20)"   "softbank"
  check "440-11 → rakuten"         "$(carrier_key 440 11)"   "rakuten"
  check "310-260 → other"          "$(carrier_key 310 260)"  "other:310-260"
  check "EARFCN 1500 → B3"         "$(earfcn_to_band 1500)"  "B3"
  check "EARFCN 6100 → B19"        "$(earfcn_to_band 6100)"  "B19"
  check "EARFCN 3750 → B8"         "$(earfcn_to_band 3750)"  "B8"
  check "EARFCN 5900 → B18"        "$(earfcn_to_band 5900)"  "B18"
  check "RSRP -92 → -92"           "$(normalize_rsrp -92)"   "-92"
  check "RSRP idx 45 → -95"        "$(normalize_rsrp 45)"    "-95"
  check "rate -92 → ◎"            "$(rate_rsrp -92)"        "◎"
  check "rate -108 → ○"           "$(rate_rsrp -108)"       "○"
  check "rate -118 → △"           "$(rate_rsrp -118)"       "△"
  check "rate -125 → ×"           "$(rate_rsrp -125)"       "×"

  say ""
  say "== 結合: QSCAN パース→キャリア別最良 RSRP =="
  local parsed; parsed="$(printf '%s\n' "$FIXTURE_QSCAN" | parse_qscan)"
  # docomo の最良は -92（-105 ではなく）
  local doc_best; doc_best="$(printf '%s\n' "$parsed" | awk -F'\t' '$2=="docomo" && $3!="" {print $3}' | sort -n | tail -1)"
  check "docomo 最良 RSRP = -92"   "$doc_best" "-92"
  local au_best; au_best="$(printf '%s\n' "$parsed" | awk -F'\t' '$2=="au" && $3!="" {print $3}' | sort -n | tail -1)"
  check "au 最良 RSRP = -108"      "$au_best" "-108"

  say ""
  say "== 結合: QSCAN レポート出力の判定マーク =="
  local report; report="$(printf '%s\n' "$FIXTURE_QSCAN" | parse_qscan | render_qscan_report)"
  check "docomo が ◎"  "$(printf '%s\n' "$report" | grep -q 'docomo .*◎' && echo yes)" "yes"
  check "au が ○"      "$(printf '%s\n' "$report" | grep -q 'au(KDDI).*○' && echo yes)" "yes"
  check "SoftBank が △" "$(printf '%s\n' "$report" | grep -q 'SoftBank.*△' && echo yes)" "yes"
  check "楽天 が ×"    "$(printf '%s\n' "$report" | grep -q '楽天.*×' && echo yes)" "yes"
  say ""
  say "  --- QSCAN レポート例（参考表示）---"
  printf '%s\n' "$report" | sed 's/^/  /'

  say ""
  say "== 結合: COPS フォールバックのパース =="
  local cparsed; cparsed="$(printf '%s\n' "$FIXTURE_COPS" | parse_cops)"
  check "docomo 在圏(LTE)"   "$(printf '%s\n' "$cparsed" | grep -q '^docomo	LTE' && echo yes)" "yes"
  check "au 在圏(LTE)"       "$(printf '%s\n' "$cparsed" | grep -q '^au	LTE' && echo yes)" "yes"
  check "softbank 在圏(3G)"  "$(printf '%s\n' "$cparsed" | grep -q '^softbank	3G' && echo yes)" "yes"
  check "rakuten 在圏(LTE)"  "$(printf '%s\n' "$cparsed" | grep -q '^rakuten	LTE' && echo yes)" "yes"
  say ""
  say "  --- COPS レポート例（参考表示）---"
  printf '%s\n' "$FIXTURE_COPS" | parse_cops | render_cops_report | sed 's/^/  /'

  say ""
  say "======================================================"
  if [ "$fail" -eq 0 ]; then
    say "$OK 自己検証 全 ${pass} 件パス"
    return 0
  else
    say "$NG 自己検証 失敗 ${fail} 件 / 成功 ${pass} 件"
    return 1
  fi
}

# ===========================================================================
# メイン（実機スキャン）
# ===========================================================================
confirm() {
  [ "$ASSUME_YES" -eq 1 ] && return 0
  say "$WARN これから電波スキャンを行います。スキャン中 LTE がおおむね 1〜3 分切れます。"
  say "      （終了時に自動で回線と watchdog を元に戻します）"
  if [ ! -t 0 ]; then
    say "$NG 対話端末ではないため中断しました。無人実行なら --yes を付けてください。"
    exit 1
  fi
  local ans
  read -r -p "続行しますか? [y/N] " ans
  case "$ans" in [yY]|[yY][eE][sS]) return 0 ;; *) say "中断しました。"; exit 1 ;; esac
}

real_scan() {
  if [ "$(id -u)" -ne 0 ]; then
    say "$NG root で実行してください（ModemManager 停止と AT ポート占有のため）:  sudo $0 ..." >&2
    exit 1
  fi

  say "======================================================"
  say " wildlife-cam 全キャリア電波スキャン (EG25-G QSCAN)"
  say " 候補地: $SITE   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  say "======================================================"
  confirm

  # watchdog timer が動いていれば止める（誤発動防止）。戻すのは restore。
  if systemctl is-active --quiet "$NETWATCH_TIMER"; then
    NETWATCH_WAS_ACTIVE=1
    systemctl stop "$NETWATCH_TIMER" >/dev/null 2>&1 \
      && say "$OK $NETWATCH_TIMER を一時停止しました" \
      || say "$WARN $NETWATCH_TIMER の停止に失敗（続行します）"
  fi

  # ここから先は何があっても restore を通す
  trap restore EXIT INT TERM

  say "・ModemManager を停止して AT ポートを確保します…"
  systemctl stop "$MM_SERVICE" >/dev/null 2>&1 || say "$WARN ModemManager の停止に失敗（続行を試みます）"
  sleep 2

  if ! detect_at_port; then
    say "$NG AT ポートが見つかりません（EG25 は通常 /dev/ttyUSB2）。--port で指定してください。"
    exit 1
  fi
  say "$OK AT ポート: $AT_PORT"

  # QSCAN 発行（スキャン秒数 + 余裕 30s を全体タイムアウトに）
  say "・AT+QSCAN=3,${QSCAN_TIMEOUT} を発行します（最大 $((QSCAN_TIMEOUT+30)) 秒）…"
  local qout rc
  qout="$(at_cmd "AT+QSCAN=3,${QSCAN_TIMEOUT}" $((QSCAN_TIMEOUT+30)))"; rc=$?

  # 復帰させてから結果表示（lte-his 再接続を待つ）
  restore
  say ""
  say "======================================================"
  say " スキャン結果   候補地: $SITE"
  say "======================================================"

  if [ "$rc" -eq 0 ] && printf '%s\n' "$qout" | grep -q '+QSCAN:'; then
    printf '%s\n' "$qout" | parse_qscan | render_qscan_report
  else
    say "$WARN QSCAN が使えませんでした（firmware 非対応の可能性）。AT+COPS=? にフォールバックします。"
    # フォールバックは ModemManager を再度止めて実行
    systemctl stop "$MM_SERVICE" >/dev/null 2>&1 || true
    RESTORED=0
    trap restore EXIT INT TERM
    sleep 2
    detect_at_port || { say "$NG AT ポート再取得に失敗"; exit 1; }
    local cout crc
    cout="$(at_cmd "AT+COPS=?" 90)"; crc=$?
    restore
    say ""
    if [ "$crc" -eq 0 ] && printf '%s\n' "$cout" | grep -q '+COPS:'; then
      printf '%s\n' "$cout" | parse_cops | render_cops_report
    else
      say "$NG QSCAN も COPS も取得できませんでした。モデム状態を確認してください（mmcli -m any）。"
      exit 1
    fi
  fi

  say "======================================================"
  # 最後に現在のネット状態を表示（回線が戻ったか確認）
  if [ -x "$APP_HOME/scripts/net-status.sh" ]; then
    say ""
    "$APP_HOME/scripts/net-status.sh" || true
  fi
}

dry_run() {
  say "======================================================"
  say " [DRY-RUN] 実機には一切触れません。実行時に行うこと:"
  say "======================================================"
  say " 候補地            : $SITE"
  say " 1) 停止する timer  : $NETWATCH_TIMER（誤発動防止・終了時に再開）"
  say " 2) 停止する service: $MM_SERVICE（AT ポート占有・終了時に再開）"
  say " 3) AT ポート       : ${AT_PORT:-自動検出（候補: ${AT_PORT_CANDIDATES[*]}）}"
  say " 4) 発行コマンド    : AT+QSCAN=3,${QSCAN_TIMEOUT}（失敗時 AT+COPS=? へ）"
  say " 5) 想定断時間      : おおむね 1〜3 分（終了時 lte-his 再接続を待って結果表示）"
  say ""
  say " パーサ確認は  $0 --self-test  で実機なしに検証できます。"
}

main() {
  parse_args "$@"
  if [ "$SELF_TEST" -eq 1 ]; then self_test; exit $?; fi
  if [ "$DRY_RUN" -eq 1 ]; then dry_run; exit 0; fi
  real_scan
}

main "$@"
