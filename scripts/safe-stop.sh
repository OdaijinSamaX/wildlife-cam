#!/usr/bin/env bash
# 電池交換前の安全停止。
set -euo pipefail

SERVICE="wildlife-cam.service"
echo "カメラを安全に停止しています…"
sudo -n systemctl stop "$SERVICE"
for _ in $(seq 1 20); do
  if ! systemctl is-active --quiet "$SERVICE"; then
    sync
    echo "【OK】カメラは停止しました。電源を切って電池を交換できます。"
    exit 0
  fi
  sleep 1
done
echo "【NG】停止を確認できません。まだ電源を抜かないでください。" >&2
exit 1
