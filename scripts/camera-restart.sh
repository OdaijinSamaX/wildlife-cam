#!/usr/bin/env bash
# wildlife-cam.service だけを立て直す。
set -euo pipefail

SERVICE="wildlife-cam.service"
echo "カメラサービスを再起動しています…"
sudo -n systemctl reset-failed "$SERVICE"
sudo -n systemctl restart "$SERVICE"
for _ in $(seq 1 30); do
  if systemctl is-active --quiet "$SERVICE"; then
    echo "【OK】カメラサービスは動作中です。"
    exit 0
  fi
  sleep 1
done
echo "【NG】再起動できませんでした。field-status.sh で状態を確認してください。" >&2
exit 1
