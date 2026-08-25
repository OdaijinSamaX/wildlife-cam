#!/usr/bin/env bash
# 13日無人運転用ラッパ。再起動のたびに epoch を +1 して seq_regress を避ける。
#   ESP32 側ルール: epoch > cur_epoch なら BOOTSTRAP やり直し / epoch < cur_epoch は破棄
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
# 鍵と epoch を置くディレクトリ。★このリポジトリは public なので実際の場所は書かない。
#   運用者が WILDLIFE_GAMMA_STATE で渡す（systemd unit の Environment= で設定する）。
#   詳細は firmware/README.md「鍵の用意」。
STATE="${WILDLIFE_GAMMA_STATE:-}"
[ -n "$STATE" ] || {
  echo "[fatal] WILDLIFE_GAMMA_STATE が未設定。鍵と epoch を置くディレクトリを指定すること"
  exit 1
}
EPOCH_FILE="$STATE/epoch"
KEY_FILE="$STATE/gamma-hmac.key"

[ -f "$KEY_FILE" ] || { echo "[fatal] 鍵ファイルが無い: $KEY_FILE"; exit 1; }

mkdir -p "$STATE"
epoch=$(cat "$EPOCH_FILE" 2>/dev/null || echo 0)
case "$epoch" in ''|*[!0-9]*) epoch=0 ;; esac
epoch=$((epoch + 1))
if [ "$epoch" -gt 65000 ]; then epoch=1; fi   # uint16 の範囲に収める
echo "$epoch" > "$EPOCH_FILE"

echo "[gamma-run] epoch=$epoch で開始 ($(date -Is))"
exec "$HERE/run_ble.sh" ble_advertiser.py \
     --epoch "$epoch" \
     --key-file "$KEY_FILE" \
     --duration 1300000
