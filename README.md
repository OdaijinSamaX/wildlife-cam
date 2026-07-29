# Wildlife Camera System MVP / v0.0.3

Raspberry Pi 5 + HC-SR501 PIR sensor + PiCamera3 による野生動物検知・録画・アップロードシステム。

このリポジトリには、既存の Raspberry Pi 録画コードに加えて、Cloudflare R2、Cloudflare Workers、Supabase/PostgreSQL、Vite + React で構成するクラウド保存・閲覧MVPを含めています。

v0.0.3 では親機子機構成を追加し、Raspberry Pi 5 を親機、Raspberry Pi Zero 2 W を子機として動かせるようにしました。子機が PIR とカメラを担当し、親機は Bluetooth 経由で動画を受け取って既存の Worker / R2 / Supabase 経路へアップロードします。

## MVP構成

```
Standalone mode
  Raspberry Pi / PC
    -> Cloudflare Worker API
    -> Cloudflare R2 private bucket
    -> Supabase PostgreSQL videos table

Parent-child mode (v0.0.3)
  Raspberry Pi Zero 2 W (child)
    -> Bluetooth relay
  Raspberry Pi 5 (parent)
    -> Cloudflare Worker API
  -> Cloudflare R2 private bucket
  -> Supabase PostgreSQL videos table
React Web UI
  -> Supabase Auth login
  -> Supabase RLS videos select
  -> Worker play-url endpoint
  -> Worker trap list/update endpoints for Web UI
  -> Worker trap-state endpoint for Pi polling
  -> Worker streams R2 object with expiring token
```

## 追加されたフォルダ

```
worker/             # Cloudflare Worker API
web/                # Vite + React Web UI
supabase/schema.sql # tables, indexes, RLS policies
pi/upload_video.py  # Pi/PC upload CLI
link.py            # parent-child relay transport
```

## v0.0.3 親機子機モード

実行モードは `WILDLIFE_NODE_ROLE` で切り替えます。

- `standalone`: 従来通り、1台で検知・録画・アップロードまで行う
- `parent`: Raspberry Pi 5。子機から動画を受信し、既存の WorkerUploader / DriveUploader でクラウドへ送る
- `child`: Raspberry Pi Zero 2 W。PIR とカメラを担当し、自分で armed 状態を取得して親機へ動画送信を行う

実運用では、役割固定のエントリポイントを使う方が安全です。

- `parent_main.py`: Pi 5 専用。Bluetooth 受信とサーバ送信だけを担当
- `child_main.py`: Pi Zero 2 W 専用。PIR 検知、録画、Pi 5 への転送だけを担当

主な環境変数:

```env
WILDLIFE_NODE_ROLE=parent
WILDLIFE_LINK_TRANSPORT=bluetooth
WILDLIFE_LINK_PORT=4
WILDLIFE_LINK_SERVICE_UUID=5e0ec070-4ef1-4f8e-9c12-7b0ac8cb3a11
```

補足:

- ローカルPC上で親子通信だけ先に試す場合は `WILDLIFE_LINK_TRANSPORT=tcp` を使えます
- `tcp` の場合、子機側に `WILDLIFE_PARENT_HOST=<親機IP>` が必要です
- `bluetooth` の `WILDLIFE_LINK_PORT` は RFCOMM チャネルです。`1` から `30` の範囲を使ってください
- Web UI の armed / disarmed は子機が Worker API から直接取得できます
- 子機は `get_arm_state` に自分の `trap_id` を含めて親機へ送ります
- そのため、検知停止の正は引き続きサーバ側です

詳細手順は [docs/v0.0.3-parent-child.md](docs/v0.0.3-parent-child.md) を参照してください。

## Supabase セットアップ

1. Supabase プロジェクトを作成します。
2. SQL Editor で `supabase/schema.sql` を実行します。
3. Authentication の Email/Password を有効化します。
4. 自分と友人のユーザーを Auth で作成します。
5. 最初の管理者を昇格します。

```sql
update public.profiles
set role = 'admin'
where email = 'you@example.com';
```

RLS は有効化済みです。`authenticated` かつ `profiles` に存在するユーザーだけが動画一覧を参照できます。trap の一覧取得と armed 更新は Worker 経由で行い、Worker 側で Supabase ユーザー確認と admin 権限確認を行います。

## Cloudflare R2 / Worker セットアップ

R2 バケットを作成します。

```bash
cd worker
npm install
npx wrangler r2 bucket create wildlife-cam-videos
```

`worker/wrangler.toml` の `SUPABASE_URL` と `APP_ORIGIN` を環境に合わせて変更します。

ローカル開発用に `worker/.dev.vars.example` を `worker/.dev.vars` へコピーし、値を設定します。本番は Wrangler secrets を使います。

```bash
npx wrangler secret put DEVICE_API_KEY
npx wrangler secret put WORKER_SIGNING_SECRET
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npx wrangler secret put SUPABASE_ANON_KEY
```

ローカル起動:

```bash
cd worker
npm run dev
```

Pi や別端末からローカル Worker を叩くときは、`http://localhost:8787` や `http://192.168.x.x:8787` ではなく、Cloudflare Tunnel を使う方が安定します。

```bash
cd worker
npm run dev -- --tunnel
```

この場合、`wrangler` が表示する `https://...trycloudflare.com` を Pi 側の `--api-url` に使います。`trycloudflare.com` のURLは一時的で、Worker を再起動すると変わります。

デプロイ:

```bash
cd worker
npm run deploy
```

本番で使っている Worker:

- `https://wildlife-cam-api.yabakei-wildlife-detection-project-mvp.workers.dev`

## Web UI セットアップ

```bash
cd web
npm install
copy .env.example .env
npm run dev
```

`web/.env`:

```env
VITE_SUPABASE_URL=https://YOUR_PROJECT_REF.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
VITE_WORKER_API_URL=http://localhost:8787
```

注意:

- `VITE_SUPABASE_URL` は `https://YOUR_PROJECT_REF.supabase.co` の形にしてください
- `/rest/v1/` を付けないでください
- `VITE_WORKER_API_URL` は、Worker を `--tunnel` で動かす場合は `https://...trycloudflare.com` に置き換えます
- Vite のポートは `5173` 固定とは限りません。使用中なら `5174`, `5175`, `5176` とずれることがあります

Cloudflare Pages へデプロイする場合は、ビルドコマンドを `npm run build`、出力ディレクトリを `dist`、環境変数に上記3つを設定します。

Wrangler から直接デプロイする場合:

```bash
cd web
npm run build
npx wrangler pages deploy dist --project-name wildlife-cam-web
```

本番で見るべき URL:

- 固定の確認用デプロイURLではなく `https://wildlife-cam-web.pages.dev` を使います
- `https://3d996045.wildlife-cam-web.pages.dev` のようなデプロイ固有URLは古い版を指し続けることがあります

## Pi / PC からのアップロード

```bash
pip install requests
python pi/upload_video.py \
  --file ./videos/event_001.mp4 \
  --trap-id YMK-001 \
  --captured-at "2026-05-18T02:14:00+09:00" \
  --api-url http://localhost:8787 \
  --device-token change-me-device-token
```

環境変数でも指定できます。

```bash
export WILDLIFE_API_URL=https://wildlife-cam-api.YOUR_SUBDOMAIN.workers.dev
export WILDLIFE_DEVICE_TOKEN=change-me-device-token
export TRAP_ID=YMK-001
```

失敗時は `upload_queue/` にJSONが残ります。実運用ではこのキューを定期的に再試行する systemd timer か cron を追加してください。

既存の `main.py` も、`WILDLIFE_API_URL`、`WILDLIFE_DEVICE_TOKEN`、`TRAP_ID` が設定されていれば Worker API へアップロードします。未設定の場合は従来の Google Apps Script アップロードにフォールバックします。

親機子機構成では、`WILDLIFE_API_URL` と `WILDLIFE_DEVICE_TOKEN` を Pi Zero 2 W にも置くと、armed/disarmed の判断を子機自身が行えます。Pi 5 は引き続き受信とサーバ送信だけを担当します。

Pi 側の補足:

- `--api-url http://localhost:8787` は Pi 上では使えません。Pi から見た `localhost` は Pi 自身です
- ローカル検証では `wrangler dev -- --tunnel` で表示された `https://...trycloudflare.com` を使うのが簡単です
- Raspberry Pi のユーザーが `pi` とは限らないため、作業パスは `/home/pi/...` に決め打ちしないでください
- 例えばユーザーが `odaijinsamax` の場合は `/home/odaijinsamax/wildlife-cam` を使います

Pi の実行例:

```bash
python3 ~/wildlife-cam/upload_video.py \
  --file ~/wildlife-cam/videos/test.mp4 \
  --trap-id YMK-001 \
  --captured-at "2026-05-19T08:00:00+09:00" \
  --api-url https://YOUR_TEMP_TUNNEL.trycloudflare.com \
  --device-token YOUR_DEVICE_API_KEY
```

## API

### `POST /upload-url`

Device token required: `x-device-token`

Input:

```json
{
  "trap_id": "YMK-001",
  "captured_at": "2026-05-18T02:14:00+09:00",
  "filename": "event_001.mp4"
}
```

Output:

```json
{
  "upload_url": "https://.../upload/<token>",
  "r2_key": "videos/YMK-001/2026/05/18/<id>-event_001.mp4",
  "expires_at": "2026-05-18T..."
}
```

### `PUT /upload/:token`

Uploads the video body to R2. The R2 bucket remains private.

### `POST /videos`

Device token required: `x-device-token`

Registers metadata in Supabase.

### `GET /traps/:trap_id`

Device token required: `x-device-token`

Pi が armed 状態を取得します。初回アクセス時は `traps` に自動登録され、既定値は `is_armed = true` です。

### `GET /traps`

Supabase bearer token required.

Web UI が trap 一覧を取得します。`traps` は Web から直接 Supabase を読まず、Worker 経由で取得します。

### `PATCH /traps/:trap_id`

Supabase bearer token required.

Web UI の admin が armed 状態を切り替えます。Worker 側で admin 権限を確認します。

### `GET /play-url/:video_id`

Supabase bearer token required. Returns an expiring Worker URL that streams the private R2 object.

## curl 検証例

```bash
API=http://localhost:8787
TOKEN=change-me-device-token

UPLOAD_INFO=$(curl -s -X POST "$API/upload-url" \
  -H "content-type: application/json" \
  -H "x-device-token: $TOKEN" \
  -d '{"trap_id":"YMK-001","captured_at":"2026-05-18T02:14:00+09:00","filename":"event_001.mp4"}')

UPLOAD_URL=$(echo "$UPLOAD_INFO" | jq -r .upload_url)
R2_KEY=$(echo "$UPLOAD_INFO" | jq -r .r2_key)

curl -X PUT "$UPLOAD_URL" \
  -H "content-type: video/mp4" \
  --data-binary @./videos/event_001.mp4

curl -X POST "$API/videos" \
  -H "content-type: application/json" \
  -H "x-device-token: $TOKEN" \
  -d "{\"trap_id\":\"YMK-001\",\"captured_at\":\"2026-05-18T02:14:00+09:00\",\"r2_key\":\"$R2_KEY\"}"
```

## ローカル検証結果

2026-05-19 時点で、以下はローカルで確認済みです。

1. Raspberry Pi から `pi/upload_video.py` で動画をアップロードできる
2. Worker が動画を受け取り、R2 に保存できる
3. Worker が `videos` テーブルへメタデータを登録できる
4. Supabase Auth で Web UI にログインできる
5. Web UI に `videos` 一覧が表示される
6. Web UI から動画を再生できる
7. Web UI から trap の監視 ON/OFF を切り替えられる

ローカル検証で実際に使った構成:

- Web UI: `http://localhost:<vite-port>`
- Worker: `npm run dev -- --tunnel`
- Pi の `--api-url`: `https://...trycloudflare.com`

再生まわりの実装メモ:

- 動画配信は `GET /play-url/:video_id` で期限付きURLを払い出し、`GET /play/:token` で R2 オブジェクトを返します
- ブラウザ再生には `Content-Range` と `Content-Length` の整合性が重要です
- ローカル開発では Vite のポート変動があるため、Worker 側 CORS は `localhost` の実際の Origin を返す実装にしています

armed 制御まわりの実装メモ:

- trap ごとの ON/OFF 状態は `traps.is_armed` で管理します
- Pi は `GET /traps/:trap_id` を定期取得し、`is_armed=false` の間は動体検知・録画・upload を行いません
- Worker 側でも disarmed trap に対する `/upload-url`、`PUT /upload/:token`、`POST /videos` を拒否します
- Web の trap 一覧と armed 更新は Worker 経由で行います。Supabase RLS の切り分けを UI へ持ち込まないためです
- `OFF -> ON` に戻した直後は録画が始まるのではなく、動体検知待機に戻ります。Pi ログには `Trap <id> is armed -- resuming motion detection` が出ます

## ハードウェア配料

| HC-SR501 | Pi 5 ピン | 機能 |
|----------|-----------|------|
| VCC | Pin 2 | 5V電源 |
| OUT | Pin 11 | GPIO17 |
| GND | Pin 9 | GND |

HC-SR501 のジャンパは **リピート(H)** 側にしてください。ノンリピート(L)だと出力 HIGH が 1〜2 秒で切れ、`wait_for_sustained_motion(1.0)` を満たせません。

### IR 投光器（850nm・12V）

録画中だけ点灯します。Pi とは別の 12V 電源系（単3×8の電池BOX）で駆動し、2SK4017 で 12V 側のローサイドを断続します。**GND だけは Pi と共通**にしてください（MOSFET がゲート電圧の基準を持てないため）。

| 接続 | 先 |
|------|-----|
| Pi GPIO18 (Pin 12) | 100Ω → 2SK4017 ゲート |
| 2SK4017 ゲート | 10kΩ → GND（プルダウン・必須） |
| 2SK4017 ドレイン | IR投光器 (−) |
| 2SK4017 ソース | GND（Pi の GND と電池BOX(−)の共通点） |
| 電池BOX (+12V) | IR投光器 (+) |

- 10kΩ プルダウンが無いと、Pi 起動中の GPIO ハイインピーダンス期間に投光器が点灯します
- IR は LED なのでフライバックダイオードは不要です
- 2SK4017 は 4V 駆動指定のため、3.3V GPIO では半開き運転になります。推力が要らない LED 負荷では実用上問題ありませんが、発熱は確認してください
- 投光器に光量センサーが内蔵されているため、昼夜の判定はソフト側に持ちません
- 環境変数: `WILDLIFE_IR_ENABLED`（`0` で無効・既定は有効）、`WILDLIFE_IR_WARMUP`（録画開始前の先行点灯秒数・既定 0.5）
- ⚠️ `bench_solenoid.py` も GPIO18 を使います。ソレノイド機構を実装する際は、どちらかのピンを必ず変えてください

## セットアップ手順

親機子機構成では、Pi Zero 2 W に `child_main.py`、Pi 5 に `parent_main.py` を配置して別サービスで起動してください。`main.py` は従来の単体運用や互換用途として残しています。

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

注意:

- `wildlife-cam.service` が動いている状態で `python3 main.py` を重ねて起動すると `GPIO busy` になります
- 手動確認時は先に `sudo systemctl stop wildlife-cam`、常駐運用へ戻すときは `sudo systemctl start wildlife-cam` を使います

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

親機子機構成の systemd は次を使います。

- Pi Zero 2 W: [wildlife-cam-child.service](wildlife-cam-child.service)
- Pi 5: [wildlife-cam-parent.service](wildlife-cam-parent.service)

運用上は、Pi の電源 ON/OFF と監視 ON/OFF は別です。

- service が動いている: Pi アプリ自体は常駐中
- Web UI で `監視中` / `停止中` を切り替える: 検知・録画・upload を許可するかどうか

## ログ確認

```bash
tail -f /home/pi/wildlife-cam/logs/wildlife.log
```

systemd 運用中はこちらの方が正確です:

```bash
journalctl -u wildlife-cam -f
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
| Pi から Worker に繋がらない | `wrangler dev -- --tunnel` を使い、`https://...trycloudflare.com` を `--api-url` に指定 |
| Supabase ログイン後に一覧が出ない | `supabase/schema.sql` の実行漏れ、`profiles` 未作成、RLS を確認 |
| 動画一覧は見えるが再生できない | `VITE_WORKER_API_URL` が古い tunnel URL のまま、または Worker 側 `APP_ORIGIN` / CORS を確認 |
| `VITE_SUPABASE_URL` で認証が壊れる | `/rest/v1/` を付けずにプロジェクトURLだけを設定 |
| `監視状態` に trap が出ない | `public.traps` が作成済みか、Pi が `/traps/:trap_id` を叩いているか、Web が最新デプロイかを確認 |
| `GPIO busy` | `wildlife-cam.service` と手動起動の二重起動を疑う。`sudo systemctl status wildlife-cam` で確認 |
| `停止中` にはなるが `監視中` に戻した時に何も起きない | 直後に録画は始まらず、動体検知待機へ戻るのが正しい挙動。Pi ログの `is armed -- resuming motion detection` を確認 |
