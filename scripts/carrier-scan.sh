#!/usr/bin/env bash
# carrier-scan.sh (v2) -- 設置候補地で「どのキャリアの電波が届くか」を実機で測る。
#
# v1 との違い（実機 wildlife-zero で確定した事実に合わせた書き換え）:
#   1) AT ポートの特定は **ModemManager を止める前に** 行う。MM 停止中は mmcli の
#      情報が空になり、停止後にポートを探すと必ず失敗する（v1 の不具合）。
#      既定フォールバックも実機に合わせて /dev/ttyUSB2 を先頭にした。
#   2) AT+QSCAN は本機の firmware（EG25GGBR07A08M2G）では非対応で確定。
#      → **主経路を AT+COPS 方式に変更**。QSCAN は `AT+QSCAN=?` が OK を返した
#      ときだけ試す opportunistic 扱いにした。
#   3) 実機でそのまま成功した手順に合わせた:
#        - 登録中セルの電波は AT+QENG="servingcell"（RSRP/RSRQ/SINR/band が取れる）
#        - 在圏キャリアの列挙は AT+COPS=2（登録切断）→ AT+COPS=?（**読み取り窓を
#          180〜240 秒とる**。登録中に COPS=? を出すと数秒で登録網 1 件しか
#          返らない＝ v1 のフォールバックが失敗した真因）→ AT+COPS=0（復帰）
#
# ねらい:
#   手持ちの SIM は docomo 系だけだが、上の手順なら周囲に「在圏できる」キャリアを
#   全 PLMN 列挙でき、登録中の網については RSRP で電波強度も判定できる。現地で
#   「この場所で使える網」を非プログラマでも 1 コマンドで確認できるようにする。
#
# 使い方（母艦から / Tailscale 経由・root 必須）:
#   ssh wildlife-zero-ts 'sudo ~/wildlife-cam/scripts/carrier-scan.sh "候補地A"'
# Pi 上で直接:
#   sudo ~/wildlife-cam/scripts/carrier-scan.sh "候補地A"
#
# 引数:
#   $1                 候補地名（記録用。省略可）
# オプション:
#   --yes              確認プロンプトを省略（無人・スクリプト実行用）
#   --dry-run          実機を一切触らず、何をするかだけ表示（安全な下見）
#   --self-test        AT を発行せず、実機で採取した QENG/COPS サンプルでパーサを自己検証
#   --port <dev>       AT ポートを明示（既定は MM 停止前に自動検出→ EG25 は通常 /dev/ttyUSB2）
#   --cops-window <s>  AT+COPS=? の読み取り窓（既定 210 秒。180〜240 を推奨）
#   --qscan-timeout <s> opportunistic QSCAN のスキャン秒数（既定 60）
#   --json             結果を JSON で stdout に出す（人間向けログは stderr）。survey-api
#                      の /api/fullscan から非同期起動する用途。--yes を暗黙で有効化する。
#
# ⚠ 所要時間と注意:
#   スキャン中は ModemManager を止めて AT ポートを占有し、AT+COPS=2 で網登録を
#   一時的に切るため、LTE がおおむね 3〜5 分切れます。終了時（および途中中断時）に
#   trap で必ず AT+COPS=0 を発行して**登録を復帰させてから** ModemManager と
#   watchdog(timer) を元へ戻し、lte-his が再接続するのを待って結果を表示します。
#   （登録を切ったまま MM を戻すのが最悪の失敗モードなので、そこを最優先で守る）
#   スキャン中の watchdog 誤発動を防ぐため wildlife-netwatch.timer も一時停止します。
#
# 判定基準（登録セルの RSRP）:
#   >= -100dBm ◎ / -110 ○ / -120 △ / それ未満 or 不検出 ×
#
# 依存: bash, stty, systemctl, mmcli(検出用), nmcli(復帰確認用)。追加パッケージ不要。
# 関連: 現地調査全体の手順は docs/site-survey-protocol.md（PR #6）。本スクリプトは
#       その「電波の到達キャリア」を測る道具で、記録 1 行は site-survey.sh と同じ流儀。

set -uo pipefail

# ---- 既定値・定数 ---------------------------------------------------------
AT_PORT="${EG25_AT_PORT:-}"          # 空なら MM 停止前に自動検出
AT_PORT_CANDIDATES=(/dev/ttyUSB2 /dev/ttyUSB3 /dev/ttyUSB1 /dev/ttyUSB0)
COPS_WINDOW=210                      # AT+COPS=? の読み取り窓（180〜240 推奨）
QSCAN_TIMEOUT=60                     # opportunistic AT+QSCAN=3,<timeout> の秒数
LTE_CON="lte-his"                    # 復帰確認する NM プロファイル
NETWATCH_TIMER="wildlife-netwatch.timer"
MM_SERVICE="ModemManager.service"
APP_HOME="${WILDLIFE_CAM_HOME:-$HOME/wildlife-cam}"
RECONNECT_WAIT=90                    # 復帰後 lte-his 再接続をこの秒数まで待つ

SITE="（未記入）"
ASSUME_YES=0
DRY_RUN=0
SELF_TEST=0
JSON_MODE=0                          # --json: 結果を JSON で stdout に、人間向けは stderr へ

# 端末に出すときだけ色を付ける（パイプ/キャプチャ時は生のまま）
if [ -t 1 ]; then
  OK="\e[32m【OK】\e[0m"; NG="\e[31m【NG】\e[0m"; WARN="\e[33m【注意】\e[0m"
else
  OK="【OK】"; NG="【NG】"; WARN="【注意】"
fi

now() { date +%s; }
# JSON モードでは人間向け出力を stderr に逃がし、stdout は最終 JSON だけにする。
say() { if [ "${JSON_MODE:-0}" -eq 1 ]; then echo -e "$*" >&2; else echo -e "$*"; fi; }

# ---- 引数パース -----------------------------------------------------------
parse_args() {
  while [ $# -gt 0 ]; do
    case "$1" in
      --yes|-y)         ASSUME_YES=1 ;;
      --dry-run)        DRY_RUN=1 ;;
      --self-test)      SELF_TEST=1 ;;
      --json)           JSON_MODE=1; ASSUME_YES=1 ;;   # 機械可読出力。無人前提なので --yes も暗黙 ON
      --port)           shift; AT_PORT="${1:-}" ;;
      --cops-window)    shift; COPS_WINDOW="${1:-210}" ;;
      --qscan-timeout)  shift; QSCAN_TIMEOUT="${1:-60}" ;;
      -h|--help)        grep -E '^#' "$0" | grep -v '^#!' | sed -E 's/^# ?//'; exit 0 ;;
      --*)              echo "不明なオプション: $1" >&2; exit 2 ;;
      *)                SITE="$1" ;;
    esac
    shift
  done
}

# ===========================================================================
# パーサ部（実機非依存・自己検証対象）
# ===========================================================================

# MCC/MNC からキャリアの内部キーを返す。未知は "other:MCC-MNC"。
# 日本の主要 PLMN のみ対応（docomo は複数 MNC、au/KDDI も複数 MNC を持つ）。
#   44010=docomo系 / 44011=楽天 / 44020,44021=SoftBank系 / 44050-44054=au(KDDI)系
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
# QENG の band 欄が数値で取れるときはそちらを優先し、これは EARFCN 由来の裏取り用。
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

# QENG/QSCAN の band 欄（数値インデックス）→ 表示。空/非数値は空。
band_disp() {
  local b="${1:-}" earfcn="${2:-}"
  case "$b" in
    ''|*[!0-9]*) earfcn_to_band "$earfcn" ;;   # band 欄が無ければ EARFCN から推定
    *)           echo "B$b" ;;
  esac
}

# RSRP 生値 → dBm。EG25 の QENG/QSCAN は実 dBm(負値)で返すのが通常。
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

# QENG servingcell(stdin) → TSV: key<TAB>rsrp_dbm<TAB>rsrq<TAB>rssi<TAB>sinr<TAB>band<TAB>earfcn<TAB>rat
# 実機の LTE 応答例:
#   +QENG: "servingcell","NOCONN","LTE","FDD",440,10,950FE00,43,6100,19,3,3,909A,-71,-5,-47,30,-
# フィールド: 0="servingcell" 1=state 2=RAT 3=duplex 4=MCC 5=MNC 6=cellID 7=PCID
#            8=EARFCN 9=band 10=UL_BW 11=DL_BW 12=TAC 13=RSRP 14=RSRQ 15=RSSI 16=SINR 17=CQI
# 非 LTE(WCDMA/GSM) は欄位置が異なるためキャリア検出のみ（信号は空）。
parse_qeng() {
  local line rest rat mcc mnc earfcn band rsrp rsrq rssi sinr key
  while IFS= read -r line; do
    case "$line" in
      *'+QENG:'*'servingcell'*) ;;
      *) continue ;;
    esac
    rest="${line#*+QENG:}"
    rest="${rest#"${rest%%[![:space:]]*}"}"   # 先頭空白を除去
    local IFS=','
    # shellcheck disable=SC2206
    local f=($rest)
    unset IFS
    rat="${f[2]:-}"; rat="${rat//\"/}"; rat="${rat//[[:space:]]/}"
    case "$rat" in
      LTE|NR5G|NR)
        mcc="${f[4]:-}";    mcc="${mcc//[[:space:]]/}"
        mnc="${f[5]:-}";    mnc="${mnc//[[:space:]]/}"
        earfcn="${f[8]:-}"; earfcn="${earfcn//[[:space:]]/}"
        band="${f[9]:-}";   band="${band//[[:space:]]/}"
        rsrp="${f[13]:-}";  rsrp="${rsrp//[[:space:]]/}"
        rsrq="${f[14]:-}";  rsrq="${rsrq//[[:space:]]/}"
        rssi="${f[15]:-}";  rssi="${rssi//[[:space:]]/}"
        sinr="${f[16]:-}";  sinr="${sinr//[[:space:]]/}"
        [ -z "$mcc" ] || [ -z "$mnc" ] && continue
        key="$(carrier_key "$mcc" "$mnc")"
        rsrp="$(normalize_rsrp "$rsrp")"
        printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
          "$key" "$rsrp" "$rsrq" "$rssi" "$sinr" "$(band_disp "$band" "$earfcn")" "$earfcn" "$rat"
        ;;
      WCDMA|TD-SCDMA|GSM)
        # 非 LTE は MCC/MNC が f[3],f[4] に来る。検出のみ（信号は空）。
        mcc="${f[3]:-}"; mcc="${mcc//[[:space:]]/}"
        mnc="${f[4]:-}"; mnc="${mnc//[[:space:]]/}"
        case "$mcc" in ''|*[!0-9]*) continue ;; esac
        key="$(carrier_key "$mcc" "$mnc")"
        printf '%s\t\t\t\t\t\t\t%s\n' "$key" "$rat"
        ;;
      *) continue ;;
    esac
  done
}

# COPS 生出力(stdin) → TSV: carrier<TAB>act_label
# 実機の応答例:
#   +COPS: (0,"IIJ","IIJ","44010",7),(0,"44050","44050","44050",7),(0,"KDDI(au)","KDDI(au)","44051",7),...,,(0-4),(0-2)
# グループ = (stat,"long","short","numeric",act)。末尾の (0-4)/(0-2) は
# <mode>/<format> の対応表なので numeric が数値でない → スキップされる。
parse_cops() {
  local raw grp inside numeric act mcc mnc key
  raw="$(cat)"
  while [ -n "$raw" ]; do
    case "$raw" in
      *'('*')'*) ;;
      *) break ;;
    esac
    grp="${raw#*(}"; grp="${grp%%)*}"; raw="${raw#*)}"
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

# QSCAN 生出力(stdin) → TSV: rat<TAB>carrier<TAB>rsrp_dbm<TAB>rsrq<TAB>band<TAB>earfcn<TAB>pci
# 行例: +QSCAN: "LTE",440,10,1500,300,-92,-9,...  （opportunistic：対応 firmware のみ）
parse_qscan() {
  local line rest type mcc mnc earfcn pci rsrp rsrq
  while IFS= read -r line; do
    case "$line" in
      *'+QSCAN:'*) ;;
      *) continue ;;
    esac
    rest="${line#*+QSCAN:}"
    rest="${rest#"${rest%%[![:space:]]*}"}"
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
        printf '%s\t%s\t\t\t\t\t\n' "$type" "$key"
        ;;
    esac
  done
}

# ===========================================================================
# 集計とレポート
# ===========================================================================

# 表示順（既知キャリア→その他）
ORDER=(docomo au softbank rakuten)

rec_name() { # 記録行用の短い名前
  case "$1" in docomo) echo docomo;; au) echo au;; softbank) echo SB;; rakuten) echo 楽天;; other:*) echo "${1#other:}";; *) echo "$1";; esac
}

join_by() { local sep="$1"; shift; local out="${1:-}"; shift || true; local x; for x in "$@"; do out="$out$sep$x"; done; printf '%s' "$out"; }

# 統合レポート。$1=QENG TSV / $2=COPS TSV / $3=QSCAN TSV（いずれも空可）。
render_report() {
  local qeng_tsv="$1" cops_tsv="$2" qscan_tsv="${3:-}"

  # --- QENG: 登録中セル（1 件想定） ---
  local serv_key="" serv_rsrp="" serv_rsrq="" serv_rssi="" serv_sinr="" serv_band="" serv_earfcn="" serv_rat=""
  if [ -n "$qeng_tsv" ]; then
    local qk qr qrq qrs qsi qb qe qrt
    while IFS=$'\t' read -r qk qr qrq qrs qsi qb qe qrt; do
      [ -z "${qk:-}" ] && continue
      # RSRP を持つ行（LTE 等）を優先採用
      if [ -n "$qr" ] || [ -z "$serv_key" ]; then
        serv_key="$qk"; serv_rsrp="$qr"; serv_rsrq="$qrq"; serv_rssi="$qrs"
        serv_sinr="$qsi"; serv_band="$qb"; serv_earfcn="$qe"; serv_rat="$qrt"
      fi
      [ -n "$qr" ] && break
    done <<< "$qeng_tsv"
  fi

  # --- COPS: 在圏キャリアの方式 ---
  declare -A act_of
  local order_dyn=("${ORDER[@]}")
  if [ -n "$cops_tsv" ]; then
    local ck ca
    while IFS=$'\t' read -r ck ca; do
      [ -z "${ck:-}" ] && continue
      case " ${order_dyn[*]} " in *" $ck "*) ;; *) order_dyn+=("$ck") ;; esac
      if [ -z "${act_of[$ck]:-}" ] || [ "$ca" = "LTE" ]; then act_of["$ck"]="$ca"; fi
    done <<< "$cops_tsv"
  fi

  # --- QSCAN(opportunistic): キャリア別最良 RSRP ---
  # 空連想配列に ${#arr[@]} を使うと古い bash では set -u に触れるため、件数は
  # 明示カウンタ qscan_n で持つ。
  declare -A qscan_rsrp qscan_band
  local qscan_n=0
  if [ -n "$qscan_tsv" ]; then
    local sr sk srsrp srsrq sband searfcn spci
    while IFS=$'\t' read -r sr sk srsrp srsrq sband searfcn spci; do
      [ -z "${sk:-}" ] && continue
      case " ${order_dyn[*]} " in *" $sk "*) ;; *) order_dyn+=("$sk") ;; esac
      if [ -n "$srsrp" ]; then
        if [ -z "${qscan_rsrp[$sk]:-}" ]; then qscan_n=$((qscan_n+1)); fi
        if [ -z "${qscan_rsrp[$sk]:-}" ] || [ "$srsrp" -gt "${qscan_rsrp[$sk]}" ]; then
          qscan_rsrp["$sk"]="$srsrp"; qscan_band["$sk"]="$sband"
        fi
      fi
    done <<< "$qscan_tsv"
  fi

  # 登録中の網も在圏にカウント
  if [ -n "$serv_key" ] && [ -z "${act_of[$serv_key]:-}" ]; then
    act_of["$serv_key"]="${serv_rat:-在圏}"
    case " ${order_dyn[*]} " in *" $serv_key "*) ;; *) order_dyn+=("$serv_key") ;; esac
  fi

  # === ① キャリア別 在圏/圏外表 ===
  say "■ ① キャリア別 在圏/圏外（AT+COPS=? / 各社の電波強度は取得不可）"
  printf "   %-14s %-8s %s\n" "キャリア" "在圏" "接続方式"
  local k label
  for k in "${order_dyn[@]}"; do
    label="$(carrier_label "$k")"
    if [ -n "${act_of[$k]:-}" ]; then
      printf "   %-14s %-8s %s\n" "$label" "在圏 ○" "${act_of[$k]}"
    else
      case "$k" in
        docomo|au|softbank|rakuten)
          printf "   %-14s %-8s %s\n" "$label" "圏外 ×" "-" ;;
        *) : ;;   # 未知キャリアは在圏時のみ表示
      esac
    fi
  done

  # === ② 登録中の網（QENG の RSRP で判定） ===
  say "------------------------------------------------------"
  say "■ ② 登録中の網（AT+QENG=\"servingcell\" / 電波強度で判定）"
  local serv_mark=""
  if [ -n "$serv_key" ] && [ -n "$serv_rsrp" ]; then
    serv_mark="$(rate_rsrp "$serv_rsrp")"
    printf "   %-14s %-6s %-9s %-7s %-7s %s\n" "キャリア" "判定" "RSRP" "RSRQ" "SINR" "バンド"
    printf "   %-14s  %-5s %-9s %-7s %-7s %s\n" \
      "$(carrier_label "$serv_key")" "$serv_mark" \
      "${serv_rsrp}dBm" "${serv_rsrq:-?}dB" "${serv_sinr:-?}" "${serv_band:-?}"
  elif [ -n "$serv_key" ]; then
    printf "   %-14s %s（%s、RSRP 取得不可）\n" "$(carrier_label "$serv_key")" "登録中" "${serv_rat:-?}"
  else
    say "   $WARN 登録中セルを取得できませんでした（QENG 応答なし／未登録の可能性）"
  fi

  # === opportunistic QSCAN の結果（対応 firmware のときだけ） ===
  if [ "$qscan_n" -gt 0 ]; then
    say "------------------------------------------------------"
    say "■ （opportunistic）周辺セル走査 QSCAN のキャリア別 最良 RSRP"
    for k in "${order_dyn[@]}"; do
      [ -z "${qscan_rsrp[$k]:-}" ] && continue
      printf "   %-14s %-5s %-9s %s\n" \
        "$(carrier_label "$k")" "$(rate_rsrp "${qscan_rsrp[$k]}")" \
        "${qscan_rsrp[$k]}dBm" "${qscan_band[$k]:-?}"
    done
  fi

  # === ③ サマリ + 記録行 ===
  local -a summary_parts rec_parts
  for k in "${order_dyn[@]}"; do
    label="$(carrier_label "$k")"
    if [ "$k" = "$serv_key" ] && [ -n "$serv_rsrp" ]; then
      summary_parts+=("${label} ${serv_mark}(${serv_rsrp}dBm)")
      rec_parts+=("$(rec_name "$k")=${serv_mark}(${serv_rsrp}dBm,${serv_band:-?})")
    elif [ -n "${qscan_rsrp[$k]:-}" ]; then
      summary_parts+=("${label} $(rate_rsrp "${qscan_rsrp[$k]}")(${qscan_rsrp[$k]}dBm)")
      rec_parts+=("$(rec_name "$k")=$(rate_rsrp "${qscan_rsrp[$k]}")(${qscan_rsrp[$k]}dBm)")
    elif [ -n "${act_of[$k]:-}" ]; then
      summary_parts+=("${label} 在圏(${act_of[$k]})")
      rec_parts+=("$(rec_name "$k")=在圏(${act_of[$k]})")
    else
      case "$k" in
        docomo|au|softbank|rakuten)
          summary_parts+=("${label} ×")
          rec_parts+=("$(rec_name "$k")=×") ;;
      esac
    fi
  done

  say "------------------------------------------------------"
  say "■ ③ この場所で使える網"
  say "   $(join_by ' / ' "${summary_parts[@]}")"
  say "------------------------------------------------------"
  say "■ 記録用（スマホに控える1行）"
  say "   場所=$SITE / $(join_by ' / ' "${rec_parts[@]}") / 方式=QENG+COPS"
}

# ---- JSON 出力（--json）用のヘルパ ---------------------------------------
# 文字列を JSON 文字列としてクオート/エスケープ。改行/タブは空白へ潰す。
json_str() {
  local s="${1:-}"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"
  s="${s//$'\n'/ }"; s="${s//$'\r'/}"; s="${s//$'\t'/ }"
  printf '"%s"' "$s"
}
# 整数/負整数なら生値、そうでなければ null。
json_num() {
  local v="${1:-}"
  case "$v" in
    ''|-|*[!0-9-]*) echo "null" ;;
    *)              echo "$v" ;;
  esac
}

# render_report と同じ集計を JSON で stdout へ出す（--json 用）。
# 形: {site, time, method, serving:{...}|null, carriers_present:[{...}]}
render_report_json() {
  local qeng_tsv="$1" cops_tsv="$2" qscan_tsv="${3:-}"

  # --- QENG: 登録中セル（render_report と同じ選び方） ---
  local serv_key="" serv_rsrp="" serv_rsrq="" serv_rssi="" serv_sinr="" serv_band="" serv_earfcn="" serv_rat=""
  if [ -n "$qeng_tsv" ]; then
    local qk qr qrq qrs qsi qb qe qrt
    while IFS=$'\t' read -r qk qr qrq qrs qsi qb qe qrt; do
      [ -z "${qk:-}" ] && continue
      if [ -n "$qr" ] || [ -z "$serv_key" ]; then
        serv_key="$qk"; serv_rsrp="$qr"; serv_rsrq="$qrq"; serv_rssi="$qrs"
        serv_sinr="$qsi"; serv_band="$qb"; serv_earfcn="$qe"; serv_rat="$qrt"
      fi
      [ -n "$qr" ] && break
    done <<< "$qeng_tsv"
  fi

  # --- COPS: 在圏キャリアの方式 ---
  declare -A act_of
  local order_dyn=("${ORDER[@]}")
  if [ -n "$cops_tsv" ]; then
    local ck ca
    while IFS=$'\t' read -r ck ca; do
      [ -z "${ck:-}" ] && continue
      case " ${order_dyn[*]} " in *" $ck "*) ;; *) order_dyn+=("$ck") ;; esac
      if [ -z "${act_of[$ck]:-}" ] || [ "$ca" = "LTE" ]; then act_of["$ck"]="$ca"; fi
    done <<< "$cops_tsv"
  fi

  # --- QSCAN(opportunistic): キャリア別最良 RSRP ---
  declare -A qscan_rsrp qscan_band
  if [ -n "$qscan_tsv" ]; then
    local sr sk srsrp srsrq sband searfcn spci
    while IFS=$'\t' read -r sr sk srsrp srsrq sband searfcn spci; do
      [ -z "${sk:-}" ] && continue
      case " ${order_dyn[*]} " in *" $sk "*) ;; *) order_dyn+=("$sk") ;; esac
      if [ -n "$srsrp" ]; then
        if [ -z "${qscan_rsrp[$sk]:-}" ] || [ "$srsrp" -gt "${qscan_rsrp[$sk]}" ]; then
          qscan_rsrp["$sk"]="$srsrp"; qscan_band["$sk"]="$sband"
        fi
      fi
    done <<< "$qscan_tsv"
  fi

  if [ -n "$serv_key" ] && [ -z "${act_of[$serv_key]:-}" ]; then
    act_of["$serv_key"]="${serv_rat:-在圏}"
    case " ${order_dyn[*]} " in *" $serv_key "*) ;; *) order_dyn+=("$serv_key") ;; esac
  fi

  # --- serving オブジェクト ---
  local serv_json="null"
  if [ -n "$serv_key" ]; then
    serv_json=$(printf '{"carrier":%s,"label":%s,"rsrp_dbm":%s,"rsrq_db":%s,"sinr":%s,"band":%s,"earfcn":%s,"rat":%s,"rating":%s}' \
      "$(json_str "$serv_key")" "$(json_str "$(carrier_label "$serv_key")")" \
      "$(json_num "$serv_rsrp")" "$(json_num "$serv_rsrq")" "$(json_num "$serv_sinr")" \
      "$(json_str "$serv_band")" "$(json_str "$serv_earfcn")" "$(json_str "$serv_rat")" \
      "$( [ -n "$serv_rsrp" ] && json_str "$(rate_rsrp "$serv_rsrp")" || echo null )")
  fi

  # --- carriers_present 配列 ---
  local -a parts=()
  local k label present act rsrp band rating obj
  for k in "${order_dyn[@]}"; do
    label="$(carrier_label "$k")"
    present=false; act=null; rsrp=null; band=null; rating=null
    if [ "$k" = "$serv_key" ] && [ -n "$serv_rsrp" ]; then
      present=true; act="$(json_str "${serv_rat:-LTE}")"; rsrp="$(json_num "$serv_rsrp")"
      band="$(json_str "$serv_band")"; rating="$(json_str "$(rate_rsrp "$serv_rsrp")")"
    elif [ -n "${qscan_rsrp[$k]:-}" ]; then
      present=true; rsrp="$(json_num "${qscan_rsrp[$k]}")"; band="$(json_str "${qscan_band[$k]:-}")"
      rating="$(json_str "$(rate_rsrp "${qscan_rsrp[$k]}")")"
      [ -n "${act_of[$k]:-}" ] && act="$(json_str "${act_of[$k]}")"
    elif [ -n "${act_of[$k]:-}" ]; then
      present=true; act="$(json_str "${act_of[$k]}")"
    else
      case "$k" in docomo|au|softbank|rakuten) present=false ;; *) continue ;; esac
    fi
    obj=$(printf '{"carrier":%s,"label":%s,"present":%s,"act":%s,"rsrp_dbm":%s,"band":%s,"rating":%s}' \
      "$(json_str "$k")" "$(json_str "$label")" "$present" "$act" "$rsrp" "$band" "$rating")
    parts+=("$obj")
  done

  printf '{"site":%s,"time":%s,"method":"QENG+COPS","serving":%s,"carriers_present":[%s]}\n' \
    "$(json_str "$SITE")" "$(json_str "$(date -u +%Y-%m-%dT%H:%M:%SZ)")" \
    "$serv_json" "$(join_by ',' "${parts[@]}")"
}

# ===========================================================================
# AT 実行（実機・root 必須）
# ===========================================================================

at_probe() { # ポート $1 が AT に OK を返すか
  local port="$1"
  stty -F "$port" 115200 cs8 -cstopb -parenb raw -echo min 0 time 5 2>/dev/null || return 1
  exec 8<>"$port" 2>/dev/null || return 1
  printf 'AT\r\n' >&8 2>/dev/null || { at_close; return 1; }
  local start=$SECONDS line
  while IFS= read -r -t 2 line <&8; do
    case "$line" in *OK*) at_close; return 0 ;; esac
    (( SECONDS - start >= 3 )) && break
  done
  at_close
  return 1
}

at_close() { exec 8>&- 2>/dev/null || true; exec 8<&- 2>/dev/null || true; }

# AT コマンド発行。$1=コマンド $2=全体タイムアウト秒 $3=進捗ラベル(任意)。
# 標準出力に応答本文、戻り値は OK=0 / ERROR・timeout=1。
# $3 を与えると待機中の経過秒を端末(stderr)に表示する（長い COPS=? 窓向け）。
at_cmd() {
  local cmd="$1" deadline="${2:-10}" prog="${3:-}" line acc="" start rc=1 elapsed last_tick=0
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
    elapsed=$(( SECONDS - start ))
    if [ -n "$prog" ] && [ -t 2 ] && [ $(( elapsed - last_tick )) -ge 6 ]; then
      last_tick=$elapsed
      printf '\r   %s … 経過 %ds / 最大 %ds ' "$prog" "$elapsed" "$deadline" >&2
    fi
    (( elapsed >= deadline )) && { rc=1; break; }
  done
  [ -n "$prog" ] && [ -t 2 ] && printf '\r%*s\r' 62 '' >&2   # 進捗行を消す
  at_close
  printf '%s' "$acc"
  return "$rc"
}

# MM 稼働中に mmcli からモデムの AT ポートを引く（v1 の不具合＝停止後探索の修正）。
mmcli_at_port() {
  command -v mmcli >/dev/null 2>&1 || return 1
  local midx p
  midx="$(mmcli -L 2>/dev/null | grep -oE '/Modem/[0-9]+' | head -1 | grep -oE '[0-9]+$')"
  [ -n "$midx" ] || return 1
  p="$(mmcli -m "$midx" 2>/dev/null | tr ',' '\n' | grep -oE 'ttyUSB[0-9]+ \(at\)' | head -1 | grep -oE 'ttyUSB[0-9]+')"
  [ -n "$p" ] || return 1
  echo "/dev/$p"
}

# AT ポートの特定（**ModemManager を止める前に**呼ぶこと）。
resolve_at_port() {
  if [ -n "$AT_PORT" ]; then
    [ -e "$AT_PORT" ] && return 0 || { say "$NG 指定ポートがありません: $AT_PORT" >&2; return 1; }
  fi
  local p
  if p="$(mmcli_at_port)" && [ -n "$p" ] && [ -e "$p" ]; then AT_PORT="$p"; return 0; fi
  # フォールバック: 実在する候補の先頭（既定は /dev/ttyUSB2）
  for p in "${AT_PORT_CANDIDATES[@]}"; do
    [ -e "$p" ] && { AT_PORT="$p"; return 0; }
  done
  return 1
}

# MM 停止後に、実際に AT が通るポートを最終確認（通らなければ候補を総当り）。
confirm_at_port_live() {
  at_probe "$AT_PORT" && return 0
  local p
  for p in "${AT_PORT_CANDIDATES[@]}"; do
    [ "$p" = "$AT_PORT" ] && continue
    [ -e "$p" ] || continue
    if at_probe "$p"; then AT_PORT="$p"; return 0; fi
  done
  return 1
}

# ===========================================================================
# 復旧（trap で必ず呼ばれる・冪等）
#   最優先: 登録を切ったままにしない = MM を戻す前に AT+COPS=0 を発行する
# ===========================================================================
RESTORED=0
NETWATCH_WAS_ACTIVE=0
COPS_DEREGISTERED=0

restore() {
  [ "$RESTORED" -eq 1 ] && return 0
  RESTORED=1
  say ""
  say "── 後片付け（登録復帰 → 回線と watchdog を元に戻します）──"
  # 0) 登録を切っていたら、AT ポートを手放す前に必ず復帰させる（最悪モード回避）
  if [ "$COPS_DEREGISTERED" -eq 1 ]; then
    if [ -n "$AT_PORT" ] && [ -e "$AT_PORT" ] && at_cmd "AT+COPS=0" 30 >/dev/null 2>&1; then
      say "$OK 網登録を自動復帰しました（AT+COPS=0）"
    else
      say "$WARN AT+COPS=0 に失敗（ModemManager 再開後に自動再登録されるはず）"
    fi
    COPS_DEREGISTERED=0
  fi
  at_close
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
#   fixture は実機 wildlife-zero で今朝そのまま採取した応答 2 行。
# ===========================================================================
FIXTURE_QENG='AT+QENG="servingcell"
+QENG: "servingcell","NOCONN","LTE","FDD",440,10,950FE00,43,6100,19,3,3,909A,-71,-5,-47,30,-
OK'
FIXTURE_COPS='+COPS: (0,"IIJ","IIJ","44010",7),(0,"44050","44050","44050",7),(0,"KDDI(au)","KDDI(au)","44051",7),(0,"440 52","440 52","44052",7),(0,"440 53","440 53","44053",7),(0,"44054","44054","44054",7),,(0-4),(0-2)
OK'
# opportunistic QSCAN（対応 firmware のときだけ通る経路）の合成 fixture
FIXTURE_QSCAN='+QSCAN: "LTE",440,10,6100,111,-71,-5,120,5
+QSCAN: "LTE",440,51,3750,44,-108,-11,90,7
OK'

self_test() {
  local pass=0 fail=0
  check() { # $1=説明 $2=実際 $3=期待
    if [ "$2" = "$3" ]; then pass=$((pass+1)); say "$OK $1"; else fail=$((fail+1)); say "$NG $1  期待='$3' 実際='$2'"; fi
  }

  say "== ユニット: carrier_key / band_disp / normalize_rsrp / rate_rsrp =="
  check "440-10 → docomo"          "$(carrier_key 440 10)"   "docomo"
  check "440-50 → au"              "$(carrier_key 440 50)"   "au"
  check "440-54 → au"              "$(carrier_key 440 54)"   "au"
  check "440-20 → softbank"        "$(carrier_key 440 20)"   "softbank"
  check "440-11 → rakuten"         "$(carrier_key 440 11)"   "rakuten"
  check "310-260 → other"          "$(carrier_key 310 260)"  "other:310-260"
  check "band 19 → B19"            "$(band_disp 19 6100)"    "B19"
  check "band 欄なし→EARFCN 6100"  "$(band_disp '' 6100)"    "B19"
  check "EARFCN 3750 → B8"         "$(earfcn_to_band 3750)"  "B8"
  check "RSRP -71 → -71"           "$(normalize_rsrp -71)"   "-71"
  check "RSRP idx 45 → -95"        "$(normalize_rsrp 45)"    "-95"
  check "rate -71 → ◎"            "$(rate_rsrp -71)"        "◎"
  check "rate -108 → ○"           "$(rate_rsrp -108)"       "○"
  check "rate -118 → △"           "$(rate_rsrp -118)"       "△"
  check "rate -125 → ×"           "$(rate_rsrp -125)"       "×"

  say ""
  say "== 結合: QENG servingcell（実機の朝の応答）パース =="
  local qtsv; qtsv="$(printf '%s\n' "$FIXTURE_QENG" | parse_qeng)"
  check "QENG キャリア = docomo"   "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $1}')" "docomo"
  check "QENG RSRP = -71"          "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $2}')" "-71"
  check "QENG RSRQ = -5"           "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $3}')" "-5"
  check "QENG SINR = 30"           "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $5}')" "30"
  check "QENG band = B19"          "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $6}')" "B19"
  check "QENG EARFCN = 6100"       "$(printf '%s\n' "$qtsv" | awk -F'\t' 'NR==1{print $7}')" "6100"

  say ""
  say "== 結合: COPS（実機の朝の応答）パース =="
  local ctsv; ctsv="$(printf '%s\n' "$FIXTURE_COPS" | parse_cops)"
  check "docomo 在圏(LTE)"   "$(printf '%s\n' "$ctsv" | grep -qP '^docomo\tLTE' && echo yes)" "yes"
  check "au 在圏(LTE)"       "$(printf '%s\n' "$ctsv" | grep -qP '^au\tLTE' && echo yes)" "yes"
  check "au は 5 PLMN 検出"  "$(printf '%s\n' "$ctsv" | awk -F'\t' '$1=="au"' | wc -l | tr -d ' ')" "5"
  check "softbank は不在"    "$(printf '%s\n' "$ctsv" | grep -qP '^softbank\t' && echo yes || echo no)" "no"

  say ""
  say "== 結合: 統合レポート（QENG＋COPS）の判定・サマリ =="
  local report; report="$(render_report "$qtsv" "$ctsv" "")"
  check "登録中 docomo が ◎"     "$(printf '%s\n' "$report" | grep -qE 'docomo.*◎' && echo yes)" "yes"
  check "au が在圏 ○"            "$(printf '%s\n' "$report" | grep -qE 'au\(KDDI\).*在圏 ○' && echo yes)" "yes"
  check "SoftBank が圏外 ×"      "$(printf '%s\n' "$report" | grep -qE 'SoftBank.*圏外 ×' && echo yes)" "yes"
  check "楽天 が圏外 ×"          "$(printf '%s\n' "$report" | grep -qE '楽天.*圏外 ×' && echo yes)" "yes"
  check "サマリに -71dBm"         "$(printf '%s\n' "$report" | grep -qE 'この場所で使える網' && printf '%s\n' "$report" | grep -qE '\-71dBm' && echo yes)" "yes"
  check "記録行に 方式=QENG+COPS" "$(printf '%s\n' "$report" | grep -qE '方式=QENG\+COPS' && echo yes)" "yes"
  say ""
  say "  --- 統合レポート例（参考表示）---"
  printf '%s\n' "$report" | sed 's/^/  /'

  say ""
  say "== 結合: opportunistic QSCAN が使えた場合の augment =="
  local rtq; rtq="$(render_report "$qtsv" "$ctsv" "$(printf '%s\n' "$FIXTURE_QSCAN" | parse_qscan)")"
  check "QSCAN 節に au -108dBm"   "$(printf '%s\n' "$rtq" | grep -qE 'au\(KDDI\).*\-108dBm' && echo yes)" "yes"

  say ""
  say "== 結合: --json 出力（render_report_json） =="
  local rj; rj="$(render_report_json "$qtsv" "$ctsv" "")"
  check "JSON 登録中セル=docomo"   "$(printf '%s' "$rj" | grep -qE '"serving":\{"carrier":"docomo"' && echo yes)" "yes"
  check "JSON serving RSRP=-71"    "$(printf '%s' "$rj" | grep -qE '"rsrp_dbm":-71' && echo yes)" "yes"
  check "JSON docomo 在圏 present"  "$(printf '%s' "$rj" | grep -qE '"carrier":"docomo","label":"docomo","present":true' && echo yes)" "yes"
  check "JSON softbank 圏外 false"  "$(printf '%s' "$rj" | grep -qE '"carrier":"softbank"[^}]*"present":false' && echo yes)" "yes"
  check "JSON method=QENG+COPS"     "$(printf '%s' "$rj" | grep -qE '"method":"QENG\+COPS"' && echo yes)" "yes"
  if command -v python3 >/dev/null 2>&1; then
    check "JSON パース可(python3)"  "$(printf '%s' "$rj" | python3 -c 'import sys,json;json.load(sys.stdin);print("yes")' 2>/dev/null)" "yes"
  fi

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
  say "$WARN これから電波スキャンを行います。スキャン中 LTE がおおむね 3〜5 分切れます。"
  say "      （終了時に自動で網登録を復帰し、回線と watchdog を元に戻します）"
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
  say " wildlife-cam 全キャリア電波スキャン v2 (EG25-G / COPS+QENG)"
  say " 候補地: $SITE   $(date '+%Y-%m-%d %H:%M:%S %Z')"
  say "======================================================"
  confirm

  # --- ① AT ポートは MM を止める前に特定する（v1 の不具合修正の要） ---
  if ! resolve_at_port; then
    say "$NG AT ポートを特定できません（EG25 は通常 /dev/ttyUSB2）。--port で指定してください。"
    exit 1
  fi
  say "$OK AT ポート: $AT_PORT （ModemManager 稼働中に特定）"

  # watchdog timer が動いていれば止める（誤発動防止）。戻すのは restore。
  if systemctl is-active --quiet "$NETWATCH_TIMER"; then
    NETWATCH_WAS_ACTIVE=1
    systemctl stop "$NETWATCH_TIMER" >/dev/null 2>&1 \
      && say "$OK $NETWATCH_TIMER を一時停止しました" \
      || say "$WARN $NETWATCH_TIMER の停止に失敗（続行します）"
  fi

  # ここから先は何があっても restore を通す（COPS=0 復帰を保証）
  trap restore EXIT INT TERM

  say "・ModemManager を停止して AT ポートを確保します…"
  systemctl stop "$MM_SERVICE" >/dev/null 2>&1 || say "$WARN ModemManager の停止に失敗（続行を試みます）"
  sleep 2

  if ! confirm_at_port_live; then
    say "$NG AT ポートに応答がありません（$AT_PORT）。モデム状態を確認してください。"
    exit 1
  fi
  say "$OK AT 応答を確認: $AT_PORT"

  # --- ② 登録中セルの電波（COPS で登録を切る前に取得） ---
  say "・AT+QENG=\"servingcell\" を発行します（登録中セルの RSRP/band）…"
  local qeng_out qeng_tsv=""
  qeng_out="$(at_cmd 'AT+QENG="servingcell"' 15)"
  if printf '%s\n' "$qeng_out" | grep -q '+QENG:'; then
    qeng_tsv="$(printf '%s\n' "$qeng_out" | parse_qeng)"
  else
    say "$WARN QENG 応答が取れませんでした（続行して COPS 一覧は取得します）"
  fi

  # --- ③ 在圏キャリア列挙: COPS=2（切断）→ COPS=?（長い窓）→ COPS=0（復帰） ---
  say "・AT+COPS=2 で網登録を一時切断します…"
  local cops_out="" cops_tsv="" qscan_tsv=""
  if at_cmd "AT+COPS=2" 30 >/dev/null; then
    COPS_DEREGISTERED=1
    say "$OK 登録切断（この後 AT+COPS=? を最大 ${COPS_WINDOW}s 読み取ります）"
    say "・AT+COPS=? を発行します（在圏キャリアの全 PLMN 列挙・時間がかかります）…"
    cops_out="$(at_cmd "AT+COPS=?" "$COPS_WINDOW" "在圏キャリアを走査中")"
    if printf '%s\n' "$cops_out" | grep -q '+COPS:'; then
      cops_tsv="$(printf '%s\n' "$cops_out" | parse_cops)"
      say "$OK 在圏キャリアの列挙を取得しました"
    else
      say "$WARN COPS=? の応答が取れませんでした（窓を延ばすなら --cops-window）"
    fi

    # --- opportunistic QSCAN: サポートされているときだけ試す ---
    if at_cmd "AT+QSCAN=?" 10 >/dev/null 2>&1; then
      say "・AT+QSCAN 対応 firmware のようです。QSCAN=3,${QSCAN_TIMEOUT} も取得します…"
      local qscan_out
      qscan_out="$(at_cmd "AT+QSCAN=3,${QSCAN_TIMEOUT}" $((QSCAN_TIMEOUT+30)) "周辺セルを走査中")"
      if printf '%s\n' "$qscan_out" | grep -q '+QSCAN:'; then
        qscan_tsv="$(printf '%s\n' "$qscan_out" | parse_qscan)"
      fi
    else
      say "$WARN AT+QSCAN は非対応（この firmware では既知）。COPS+QENG のみで判定します。"
    fi

    # --- 登録を復帰（restore の保険より前に明示実行） ---
    say "・AT+COPS=0 で網登録を復帰します…"
    if at_cmd "AT+COPS=0" 30 >/dev/null; then
      COPS_DEREGISTERED=0
      say "$OK 網登録を復帰しました"
    else
      say "$WARN AT+COPS=0 の明示復帰に失敗（後片付けで再試行します）"
    fi
  else
    say "$WARN AT+COPS=2 に失敗しました。登録中セル(QENG)のみで判定します。"
  fi

  # 回線と watchdog を戻す（lte-his 再接続を待つ）
  restore

  say ""
  say "======================================================"
  say " スキャン結果   候補地: $SITE"
  say "======================================================"
  if [ -z "$qeng_tsv" ] && [ -z "$cops_tsv" ]; then
    say "$NG QENG も COPS も取得できませんでした。モデム状態を確認してください（mmcli -m any）。"
    exit 1
  fi
  if [ "$JSON_MODE" -eq 1 ]; then
    # stdout は JSON だけ（人間向けは say 経由で stderr に出ている）
    render_report_json "$qeng_tsv" "$cops_tsv" "$qscan_tsv"
  else
    render_report "$qeng_tsv" "$cops_tsv" "$qscan_tsv"
    say "======================================================"
    # 最後に現在のネット状態を表示（回線が戻ったか確認）
    if [ -x "$APP_HOME/scripts/net-status.sh" ]; then
      say ""
      "$APP_HOME/scripts/net-status.sh" || true
    fi
  fi
}

dry_run() {
  # ポート特定を MM 停止前に「読み取りだけ」試す（実機を変更しない）
  local port_disp="${AT_PORT:-}"
  if [ -z "$port_disp" ]; then
    if port_disp="$(mmcli_at_port 2>/dev/null)" && [ -n "$port_disp" ]; then
      port_disp="$port_disp（mmcli より）"
    else
      port_disp="自動検出（候補: ${AT_PORT_CANDIDATES[*]}／既定 /dev/ttyUSB2）"
    fi
  fi
  say "======================================================"
  say " [DRY-RUN] 実機には一切触れません。実行時に行うこと:"
  say "======================================================"
  say " 候補地            : $SITE"
  say " 1) AT ポート特定   : ${port_disp}（**MM 停止前**に確定＝v1 不具合の修正）"
  say " 2) 停止する timer  : $NETWATCH_TIMER（誤発動防止・終了時に再開）"
  say " 3) 停止する service: $MM_SERVICE（AT ポート占有・終了時に再開）"
  say " 4) 発行コマンド    : AT+QENG=\"servingcell\" → AT+COPS=2 → AT+COPS=?（窓 ${COPS_WINDOW}s）→ AT+COPS=0"
  say "                      （AT+QSCAN=? が OK のときだけ QSCAN=3,${QSCAN_TIMEOUT} も取得）"
  say " 5) 復帰の保証      : trap で **COPS=0 → MM 再開 → lte-his 再接続待ち(最大 ${RECONNECT_WAIT}s)**"
  say " 6) 想定断時間      : おおむね 3〜5 分"
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
