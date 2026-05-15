# Wildlife Camera System

Raspberry Pi 5 + HC-SR501 PIR sensor + PiCamera3 による野生動物検知・録画・アップロードシステム。

## ハードウェア配料

| HC-SR501 | Pi 5 ピン | 機能 |
|----------|-----------|------|
| VCC | Pin 2 | 5V電源 |
| OUT | Pin 11 | GPIO17 |
| GND | Pin 9 | GND |

## セットアップ手順

### 1. Raspberry Piへのデプロイ

```bash
# Pi上でディレクトリ作成
mkdir -p /home/pi/wildlife-cam/{videos,logs,config,gas}

# ファイルをコピー（開発マシンから実行）
scp -r /Users/shimpeikikukawa/wildlife-cam/* pi@<RPI_IP>:/home/pi/wildlife-cam/
```

### 2. 依存ライブラリのインストール（Pi上で実行）

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-gpiozero ffmpeg
pip3 install python-dotenv requests
```

### 3. Google Apps Script のデプロイ

1. https://script.google.com にアクセス
2. 「新しいプロジェクト」を作成
3. `gas/upload.gs` の内容をエディタに貼り付けて保存
4. 「デプロイ」→「新しいデプロイ」
5. 種類: ウェブアプリ
6. 実行者: 自分（Me）
7. アクセス権限: 全員（Anyone）
8. 「デプロイ」をクリックし、表示されたURLをコピー

### 4. 環境変数の設定

```bash
nano /home/pi/wildlife-cam/config/.env
```

`GOOGLE_SCRIPT_URL=` の行に取得したURLを記入：
```
GOOGLE_SCRIPT_URL=https://script.google.com/macros/s/YOUR_SCRIPT_ID/exec
LOG_LEVEL=INFO
VIDEO_RETENTION_ON_FAIL=true
```

### 5. 起動テスト

```bash
cd /home/pi/wildlife-cam
python3 main.py
```

### 6. 自動起動設定（systemd）

```bash
sudo nano /etc/systemd/system/wildlife-cam.service
```

```ini
[Unit]
Description=Wildlife Camera System
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/wildlife-cam/main.py
WorkingDirectory=/home/pi/wildlife-cam
User=pi
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable wildlife-cam
sudo systemctl start wildlife-cam
sudo systemctl status wildlife-cam
```

## ログ確認

```bash
tail -f /home/pi/wildlife-cam/logs/wildlife.log
```

## フォルダ構成

```
/home/pi/wildlife-cam/
├── main.py          # メインエントリポイント
├── sensor.py        # PIRセンサー制御
├── camera.py        # 録画モジュール
├── uploader.py      # Google Driveアップロード
├── logger.py        # ログユーティリティ
├── config/
│   └── .env         # 環境変数（GOOGLE_SCRIPT_URL等）
├── gas/
│   └── upload.gs    # Google Apps Script
├── videos/          # 録画一時保存（アップロード後削除）
└── logs/
    └── wildlife.log # システムログ
```

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| `gpiozero` エラー | `sudo apt install python3-gpiozero` |
| `picamera2` エラー | `sudo apt install python3-picamera2` |
| アップロード失敗 | `.env` の `GOOGLE_SCRIPT_URL` を確認 |
| 録画ファイルが残る | `LOG_LEVEL=DEBUG` でログ詳細確認 |