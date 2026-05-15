#!/bin/bash
# Wildlife Camera System -- Deploy to Raspberry Pi
# Usage: ./deploy.sh <PI_IP_ADDRESS>
# Example: ./deploy.sh 192.168.1.100

set -e

PI_IP="${1}"
PI_USER="pi"
REMOTE_DIR="/home/pi/wildlife-cam"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ -z "$PI_IP" ]; then
  echo "Usage: $0 <PI_IP_ADDRESS>"
  exit 1
fi

echo "[deploy] Connecting to ${PI_USER}@${PI_IP}..."

echo "[deploy] Creating remote directories..."
ssh "${PI_USER}@${PI_IP}" "mkdir -p ${REMOTE_DIR}/{videos,logs,config,gas}"

echo "[deploy] Copying files..."
rsync -avz --exclude="*.pyc" --exclude="__pycache__" --exclude=".env" \
  --exclude="videos/" --exclude="logs/" \
  "${LOCAL_DIR}/" "${PI_USER}@${PI_IP}:${REMOTE_DIR}/"

echo "[deploy] Installing dependencies on Pi..."
ssh "${PI_USER}@${PI_IP}" "
  sudo apt-get update -qq
  sudo apt-get install -y python3-picamera2 python3-gpiozero ffmpeg
  pip3 install --quiet python-dotenv requests
"

echo "[deploy] Done. Next steps:"
echo "  1. Edit ${REMOTE_DIR}/config/.env and set GOOGLE_SCRIPT_URL"
echo "  2. Run: ssh ${PI_USER}@${PI_IP} 'cd ${REMOTE_DIR} && python3 main.py'"