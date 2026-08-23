#!/usr/bin/env bash
# Wildlife Camera System -- Deploy to Raspberry Pi
# Usage:
#   ./deploy.sh wildlife-parent
#   ./deploy.sh 192.168.68.65 [user]

set -euo pipefail

TARGET="${1:-}"
PI_USER="${2:-odaijinsamax}"
REMOTE_DIR="${REMOTE_DIR:-/home/odaijinsamax/wildlife-cam}"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$TARGET" ]; then
  echo "Usage:"
  echo "  $0 wildlife-parent"
  echo "  $0 192.168.68.65 [user]"
  exit 1
fi

if [[ "$TARGET" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  SSH_TARGET="${PI_USER}@${TARGET}"
else
  SSH_TARGET="${TARGET}"
fi

echo "[deploy] Connecting to ${SSH_TARGET}..."

echo "[deploy] Creating remote directories..."
ssh "${SSH_TARGET}" "mkdir -p ${REMOTE_DIR}/{videos,logs,config,gas}"

echo "[deploy] Ensuring persistent state dir /var/lib/wildlife-cam..."
# 送信予算カウンタ等の永続状態を再起動をまたいで残す。書けなければ ~/wildlife-cam/state に退避する。
ssh "${SSH_TARGET}" "sudo install -d -o ${PI_USER} -g ${PI_USER} /var/lib/wildlife-cam" \
  || echo "[deploy] /var/lib/wildlife-cam を作れませんでした。app_home/state に退避します(非致命)"

echo "[deploy] Copying files..."
# リポジトリ全体を同期する。services/ (survey-api の測定エンジン+静的ページ) も
# この一括 rsync に含まれる。テスト成果物や仮想環境は除外する。
rsync -avz --exclude="*.pyc" --exclude="__pycache__" --exclude=".env" \
  --exclude="videos/" --exclude="logs/" --exclude=".venv/" \
  --exclude="hardware/" \
  "${LOCAL_DIR}/" "${SSH_TARGET}:${REMOTE_DIR}/"

echo "[deploy] Installing dependencies on Pi..."
ssh "${SSH_TARGET}" "
  sudo apt-get update -qq
  sudo apt-get install -y python3-picamera2 python3-gpiozero ffmpeg bluetooth bluez libbluetooth-dev
  pip3 install --quiet python-dotenv requests pybluez2
"

echo "[deploy] Applying network failover hardening (idempotent)..."
# lte-his の DNS 修復・永続ジャーナル・wildlife-netwatch(60秒監視) を一括適用する。
# lte-his プロファイルが無いノードでは中で警告して安全にスキップされる。
ssh "${SSH_TARGET}" "sudo bash ${REMOTE_DIR}/scripts/setup-network.sh" \
  || echo "[deploy] setup-network.sh はスキップ/失敗しました (非致命)。手動で確認してください"

echo "[deploy] Done. Next steps:"
echo "  1. Edit ${REMOTE_DIR}/config/.env and set GOOGLE_SCRIPT_URL"
echo "  2. Standalone: ssh ${SSH_TARGET} 'cd ${REMOTE_DIR} && python3 main.py'"
echo "  3. Parent service: sudo systemctl restart wildlife-cam-parent"
echo "  4. Child service: sudo systemctl restart wildlife-cam-child"
echo "  5. 電波調査 API (survey-api): 初回のみ systemd 常駐化 + tailscale serve 公開が必要。"
echo "     手順は ${REMOTE_DIR}/services/survey-api/README.md 参照:"
echo "       sudo cp services/survey-api/survey-api.service /etc/systemd/system/ && sudo systemctl enable --now survey-api"
echo "       sudo tailscale serve --bg --set-path /api http://127.0.0.1:18085/api   # / は静的ページ"
