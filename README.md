# Wildlife Camera System β

Wildlife Camera is an open-source, field-resilient camera system for Raspberry Pi.
It detects motion, records short clips, and uploads them through Wi-Fi or LTE to a private cloud archive.
The current β deployment runs standalone on a Pi Zero 2 W and is designed to fail safe during network loss, power loss, and unstable mobile coverage.
The repository also contains a React dashboard, a Cloudflare Worker API, and an earlier parent-child operating mode.

野外に置いた Raspberry Pi で動体を検知し、短い動画を録画してクラウドへ送るシステムです。
現在の主構成は **Pi Zero 2 W 1台で完結する standalone β** です。通信が不安定な場所や不意の電源断を前提に、撮影継続、送信保留、自己復旧、現地診断を実装しています。

## この repo の位置づけ

`wildlife-` を接頭辞とした構成の中で、この repo は**野外に置く観測装置の製品ライン**を担当します。

| 名前 | 対象 | 状態 |
|---|---|---|
| `wildlife-loop` | 事業全体。観測から捕獲、返礼までの一周 | 構想 |
| **`wildlife-cam`** | **野外観測装置の製品ライン（この repo）** | **屋久島で稼働** |
| `wildlife-log` | 検知イベントを受け取り、記録として貯めて配信する基盤 | γ版で構築中 |
| `wildlife-trap` | 罠そのものの開発 | 構想 |
| `wildlife-fly` | ドローンによる広域の観測 | 構想 |

## 現場導入の実績

2026年8月、屋久島の海岸林に β版を設置しました。国内外来種のタヌキがウミガメの卵と孵化した幼体を捕食する現場で、保全NPOへ**有償で納品**しています。

- モバイルバッテリー1本での**無人連続稼働 20時間**（実測）
- **LTE 単独運用**（Wi-Fi 不要）。遠隔から状態確認と設定変更ができる
- 1台あたりの部材実費は数万円台。設計・製作とも内製

**現在はプロトタイプです。** 箱罠のセンサーと連動して「罠が作動した瞬間の映像を送る」ことが最低限の実装要件で、これが動いた時点で製品版に移ります。現状は「動物が出た」までは分かりますが、「罠が落ちた」はまだ分かりません。

## バージョン規約 (世代管理)

**世代 = マイナー番号**で管理します (全体を 0.x に留めるのは研究開発版であることの明示)。
詳細と各版の変更履歴は [`CHANGELOG.md`](CHANGELOG.md) を参照してください。

| 世代 | 版系列 | 意味 |
|---|---|---|
| α | 0.1.x | プロトタイプ期 (親子機/クラウドMVP) |
| β | 0.2.x | 屋久島設置版 (単機フィールド投入・現地耐障害化) |
| γ | 0.3.x | 回収後の進化 (透明送信ゲート・エージェント化) |

タグは「フィールドの機体に配備した状態」に打ち、GitHub Release に変更概要を残します。
v1.0.0 は複数台の実運用移管を達成した時点のために予約しています。

## 現行アーキテクチャ

### Standalone β（主構成）
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
services/survey-api/ # 電波調査ページ + ローカル測定エンジン (mmcli/nmcli, tailscale serve 公開)
```

現地調査の道具箱 (toolbox): `scripts/site-survey.sh` / `scripts/carrier-scan.sh` に加え、
スマホから Pi のモデムで測って記録できる **電波調査ページ** を
[`services/survey-api/`](services/survey-api/README.md) で提供する (tailscale serve で公開)。

## v0.0.3 親機子機モード

実行モードは `WILDLIFE_NODE_ROLE` で切り替えます。

- `standalone`: 従来通り、1台で検知・録画・アップロードまで行う
- `parent`: Raspberry Pi 5。子機から動画を受信し、既存の WorkerUploader / DriveUploader でクラウドへ送る
- `child`: Raspberry Pi Zero 2 W。PIR とカメラを担当し、自分で armed 状態を取得して親機へ動画送信を行う

ハードウェア:

- Raspberry Pi Zero 2 W
- Raspberry Pi Camera Module 3 NoIR
- HC-SR501 PIR センサー（GPIO17）
- Quectel EG25-G LTE モデム（NetworkManager + ModemManager）
- 850nm IR 投光器（GPIO18、別電源、GND共通）
- Wi-Fi / LTE / Tailscale

データフロー:

```text
PIR motion
  -> Pi Zero 2 W records an MP4 clip
  -> local SD queue (videos/)
  -> Cloudflare Worker API
  -> private Cloudflare R2 object
  -> Supabase metadata and authentication
  -> Vite + React dashboard
```

`main.py` が `runtime.py` の standalone loopを起動し、armed状態が有効な間だけPIRを監視します。動画は送信成功後にSDから削除し、通信断・送信量上限到達・upload失敗時は `videos/` に残して再送します。

### Parent-child α（別モード）

以前の Pi Zero 2 W（child）+ Raspberry Pi 5（parent）構成も残しています。

- `child_main.py`: PIR、録画、parentへの転送
- `parent_main.py`: childから受信し、クラウドへupload
- transport: Bluetooth RFCOMM または開発用TCP
- service: [`wildlife-cam-child.service`](wildlife-cam-child.service) / [`wildlife-cam-parent.service`](wildlife-cam-parent.service)

新規の現地運用では standalone を主に使います。parent-childの詳細は [`docs/v0.0.3-parent-child.md`](docs/v0.0.3-parent-child.md) を参照してください。

## 現在の主要機能

### Arm gate: 通信断は保留

- Worker上の `traps.is_armed` を監視許可の正とします。
- [`arm_monitor.py`](arm_monitor.py) の `ArmStateMonitor` が背景threadで状態を取得し、PIR loopはメモリ上の状態だけを読みます。
- 初回取得前、通信失敗、または状態が古くなった場合は `comms_loss` として **保留（撮影しない）** に倒れます。
- 通信確認の遅延がPIRの0.1秒samplingを塞がないため、LTEのIPv6 blackholeでも検知loopが止まりません。

### Field limiter: LTE送信予算

- LTE時だけ、直近1時間のupload量を `WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR`（既定250MB）以内に抑えます。
- 上限到達後も **撮影は続け、uploadだけを止めてSDに保存** します。rolling windowが空けば自動再開します。
- backlogが `WILDLIFE_UPLOAD_NEWEST_FIRST_BACKLOG`（既定10本）を超えると、実演価値の高い新しい動画を優先します。
- 状態は再起動をまたいで永続化します。詳細は [`docs/upload-budget.md`](docs/upload-budget.md) を参照してください。
- 撮影cooldownとburst circuit breakerも実装済みですが、撮り逃しを避けるため既定では無効です。

### 遠隔設定チェーン (v0.2.x)

- 録画秒数・撮影間隔・PIR持続判定は **Webの罠カードから遠隔変更**できます。
  設定は R2 (`trap-config/<trap_id>.json`) に保存され、Piがarm確認ポーリング(約10秒毎)の
  応答で受け取って次の周回から適用します (優先順位: サーバ設定 > `.env` > 既定値)。
- 通信断時は直近に取得済みのサーバ値をメモリで維持するため、設定は現地で生き続けます。
- **PIR持続判定 (3秒ゲート)**: HC-SR501の誤検知パルス (実測幅約1.9秒) を、
  「HIGHがN秒継続して初めて検知」のソフトゲートで遮断します。誤検知→送信→
  送信のRFがPIRを再発報させる自己増殖ループの実測に基づく対策です。

### エージェントチャット「カメラに聞く」 (v0.2.x)

- Webに**読み取り専用**の質問窓口があります。認証済みユーザー (NPO協力者のviewer含む)
  が質問を投稿すると、Pi上のブリッジ ([`pi/agent_chat_bridge.py`](pi/agent_chat_bridge.py))
  が機器状態資料を組み立て、ツール無しのZeroClaw受付エージェント経由でLLMが回答します。
- この窓口から機器操作は**構造的に不可能**です (操作系エンドポイント自体が存在しない)。
  操作系は管理者のTelegramチャンネルに分離しています。

### ネットワーク自己復旧

- `wildlife-netwatch.timer` が60秒ごとにL3、IPv4 DNS、HTTP到達性を確認します。
- 連続失敗に応じてLTE再接続、Wi-Fi一時降格、modem再初期化、daemon再起動を段階的に行います。
- 最終手段のrebootにはrate limitがあり、無限再起動を避けます。
- `scripts/setup-network.sh` がLTE DNS、永続journal、timer、logrotateを冪等に設定します。
- 詳細は [`docs/network-failover-hardening.md`](docs/network-failover-hardening.md) を参照してください。

### カメラとIR

- Pi Zero 2 W向けにRAW streamを無効化し、camera/encoderのmemory pressureを抑えます。
- `WILDLIFE_LENS_POSITION`（既定0.5 dioptre）でCamera Module 3の焦点をmanual固定します。
- 録画中だけGPIO18でIR投光器へ給電し、例外時もcontext managerで消灯します。
- `systemd` watchdogはmain loopの停止を検出し、短時間の再起動loopは `StartLimit` で抑えます。

### IPv4優先とRTCなし対策

- `scripts/setup-network.sh` が `/etc/gai.conf` にIPv4優先の管理blockを追加し、LTEの到達不能なIPv6を先に待つ問題を避けます。
- RTCがないため、起動直後の時刻は正確とは限りません。`field-status.sh` でNTP同期状態を表示します。
- 同じwall clock秒に録画しても、filenameへ連番を付けて既存動画を上書きしません。
- networkの継続時間表示はuptimeを上限にして、NTP同期による時計jumpの誤表示を抑えます。

### SD queueと電源断耐性

- 0-byteまたは簡易検査に失敗したMP4は隔離し、恒久失敗の1本でqueue全体を詰まらせません。
- 空き容量が2GiBを下回る前に古い動画を整理し、削除理由をlogへ残します。
- runtime状態はtemp file + atomic renameで更新します。
- systemd serviceはcrashから復帰し、camera hangはwatchdogが検出します。

## セットアップ

### 1. Piの依存package

Raspberry Pi OS上で次を導入します。

```bash
sudo apt update
sudo apt install -y python3-picamera2 python3-gpiozero ffmpeg network-manager modemmanager
python3 -m pip install python-dotenv requests
```

### 2. 設定

repository直下の `config/.env` を作成します。秘密情報はcommitしないでください。

```env
WILDLIFE_NODE_ROLE=standalone
TRAP_ID=YOUR-TRAP-ID
WILDLIFE_API_URL=https://YOUR-WORKER.example.workers.dev
WILDLIFE_DEVICE_TOKEN=YOUR_DEVICE_TOKEN

CAMERA_WIDTH=1920
CAMERA_HEIGHT=1080
# 2Mbps: 1080p 30秒で約4.5MB。獣種の判別には十分で、SIM寿命が桁で延びる (屋久島実測)
CAMERA_BITRATE=2000000
# バッファ2: CMA(カメラ用連続メモリ)の枯渇による録画開始失敗を緩和 (Zero 2 W)
CAMERA_BUFFER_COUNT=2
WILDLIFE_LENS_POSITION=0.5

# フィールド運用値 (Webの罠カードから遠隔上書き可能。ここは通信断時のフォールバック)
WILDLIFE_RECORD_SECONDS=30
WILDLIFE_MOTION_COOLDOWN_SEC=300
WILDLIFE_MOTION_SUSTAIN_SEC=3.0

WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR=250
```

代表的なoptional設定:

| 変数 | 既定 | 説明 |
|---|---:|---|
| `WILDLIFE_IR_ENABLED` | `1` | `0` でIR出力を無効化 |
| `WILDLIFE_IR_WARMUP` | `0.5` | 録画前のIR先行点灯秒数 |
| `WILDLIFE_LENS_POSITION` | `0.5` | manual焦点位置（dioptre） |
| `WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR` | `250` | LTEのrolling upload上限 |
| `WILDLIFE_UPLOAD_NEWEST_FIRST_BACKLOG` | `10` | 新しい動画優先へ切り替えるqueue本数 |
| `WILDLIFE_MIN_FREE_BYTES` | `2147483648` | 録画用に残す最小空き容量 |
| `WILDLIFE_VIDEO_MAX_AGE_DAYS` | `14` | local clipの保存日数 |
| `WILDLIFE_RECORD_SECONDS` | `10` | 1回の録画秒数 (Webから遠隔変更可) |
| `WILDLIFE_MOTION_COOLDOWN_SEC` | `0` | 撮影cooldown。`0` は無効 (Webから遠隔変更可) |
| `WILDLIFE_MOTION_SUSTAIN_SEC` | `1.0` | PIRがこの秒数HIGHを続けて初めて検知 (誤検知フィルタ・Webから遠隔変更可) |
| `WILDLIFE_BURST_PAUSE_ENABLED` | `0` | burst circuit breaker |

### 3. Deploy

母艦からSSH hostまたはIPを指定します。

```bash
./deploy.sh <pi-ssh-host>
```

`deploy.sh` はsourceを同期し、依存packageとnetwork hardeningを適用します。`.env`、録画、logは上書きしません。

standalone serviceを初めて導入する場合:

```bash
sudo install -m 0644 wildlife-cam.service /etc/systemd/system/wildlife-cam.service
sudo systemctl daemon-reload
sudo systemctl enable --now wildlife-cam.service
```

service fileのuser・working directoryは配備先に合わせて確認してください。repositoryには秘密鍵、API key、credentialsを置かないでください。

## 運用toolbox

以下はPi上のrepository rootから実行する例です。

| Tool | 用途 | 代表例 |
|---|---|---|
| `scripts/net-status.sh` | Wi-Fi/LTE、IPv4 DNS、Internet、netwatch履歴を日本語で表示 | `./scripts/net-status.sh` |
| `scripts/field-status.sh` | 時刻、SD、camera service、送信予算、保留動画、networkを一画面表示 | `./scripts/field-status.sh` |
| `scripts/site-survey.sh` | 候補地のWi-Fi/LTE、Internet、upload速度を約1分で判定 | `./scripts/site-survey.sh "候補地A"` |
| `scripts/carrier-scan.sh` | EG25-Gの `AT+COPS=?` で周囲の登録可能networkを列挙。実行中はLTEを一時停止 | `sudo ./scripts/carrier-scan.sh "候補地A" --yes` |
| `scripts/setup-network.sh` | LTE DNS、IPv4優先、journal、netwatchを冪等適用 | `sudo ./scripts/setup-network.sh` |
| `deploy.sh` | 母艦からPiへsourceと設定unitを配備 | `./deploy.sh <pi-ssh-host>` |

電池交換前の安全停止とservice復旧:

```bash
./scripts/safe-stop.sh
./scripts/camera-restart.sh
```

非プログラマ向けの復旧手順は [`docs/field-recovery-guide.md`](docs/field-recovery-guide.md) にあります。

## 現地調査

候補地ではPiへ給電してnetwork接続を待ち、次を実行します。

```bash
./scripts/site-survey.sh "候補地A"
sudo ./scripts/carrier-scan.sh "候補地A" --yes
```

Wi-Fi/LTE電波、Internet到達、upload実測、設置可否の読み方、記録templateは [`docs/site-survey-protocol.md`](docs/site-survey-protocol.md) を参照してください。carrier scanはLTEを一時中断するため、camera実演中には実行しないでください。

## Cloud backend

repositoryには次を含みます。

- `worker/`: Cloudflare Worker。device upload、trap arm state、署名付き再生URL
- `web/`: Vite + React dashboard。Supabase Auth、動画一覧、armed切替
- `supabase/schema.sql`: videos、traps、profiles、RLS
- private R2 bucket: MP4 object保存

### Worker

```bash
cd worker
npm ci
npx wrangler r2 bucket create <r2-bucket-name>
npx wrangler secret put DEVICE_API_KEY
npx wrangler secret put WORKER_SIGNING_SECRET
npx wrangler secret put SUPABASE_SERVICE_ROLE_KEY
npx wrangler secret put SUPABASE_ANON_KEY
npm run deploy
```

project固有URLとsecretはenvironmentまたはWrangler secretで管理します。

### Web UI

`web/.env`:

```env
VITE_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
VITE_SUPABASE_ANON_KEY=YOUR_SUPABASE_ANON_KEY
VITE_WORKER_API_URL=https://YOUR-WORKER.example.workers.dev
```

```bash
cd web
npm ci
npm run dev
npm run build
```

Cloudflare Pagesではbuild commandを `npm run build`、output directoryを `dist` にします。

## 開発と検証

Python:

```bash
python3 -m py_compile *.py
python3 -m unittest discover -s tests -p 'test_*.py'
```

Shell:

```bash
for file in scripts/*.sh; do bash -n "$file"; done
```

Web / Worker:

```bash
(cd web && npm ci && npm run build)
(cd worker && npm ci && npm run typecheck)
```

## ハードウェアと筐体

屋外に置く筐体は 3D プリンタで自作しています。設計と検証のコードは [`hardware/enclosure/`](hardware/enclosure/) にあります。

CadQuery で形を書き、多視点レンダと断面図を自動生成し、**13 種類の数値チェック**（壁厚、干渉、クリアランス、オーバーハング、開口、パッキン面圧、視野、レイアウト、多様体性など）を通してから造形します。AI に CAD を書かせるときの最大の弱点は「目が無い」ことなので、**意図的に壊したモデルで各チェックが FAIL することを確かめるネガティブテスト**を必須にしてあります。

実物に当たって設計が変わった例:

- PIR はアクリルや PC の窓を透過しない → フレネルレンズを露出させ、フランジを O リングで壁に押し付ける
- IR 投光器とレンズを同室にすると内面反射で映像が白く曇る → 隔壁を入れる
- 完全密閉は結露する → 防水通気膜と乾燥剤が前提
- 蓋の締結は四隅 4 点では長辺の中央が浮く → 捕捉式の 6 点へ変更

材料は ASA（屋外 UV 耐性）。実際に刷って取得した公差補正値は 壁 ±0 / 穴 +0.30 / 突起 +0.25 です。
## Repository map

```text
main.py / runtime.py       standalone/role dispatch and runtime loop
arm_monitor.py             non-blocking armed state monitor
field_limits.py            LTE upload budget and optional capture limits
video_storage.py           bounded SD queue, retry, quarantine
camera.py / sensor.py      Camera Module 3 and PIR
illuminator.py             GPIO18 IR control
watchdog.py                systemd watchdog heartbeat
scripts/                   deploy, diagnosis, survey, recovery tools
worker/                    Cloudflare Worker API
web/                       React dashboard
supabase/                  PostgreSQL schema and RLS
hardware/enclosure/        3D-printed weatherproof enclosure (CadQuery + automated checks)
docs/                      field operation and design notes
tests/                     Python regression tests
```

## Troubleshooting

| 症状 | 確認・対処 |
|---|---|
| まず状態を知りたい | `./scripts/field-status.sh` を実行 |
| IPはあるが名前解決できない | `./scripts/net-status.sh` でIPv4 DNSを確認し、`sudo ./scripts/setup-network.sh` を再適用 |
| LTE/Wi-Fiが復帰しない | net-statusのnetwatch履歴を確認。2〜3分待って段階復旧させる |
| `GPIO busy` | 手動起動との二重実行を避け、`./scripts/camera-restart.sh` を実行 |
| camera serviceが停止中 | `./scripts/camera-restart.sh`。再停止する場合は `journalctl -u wildlife-cam.service -n 100` |
| `Device or resource busy` | camera processの残存を確認し、serviceを再起動 |
| 動画がSDに残る | 通信断、LTE予算到達、upload失敗のいずれか。field-statusの「送信保留」を確認 |
| 動画がすぐWebへ出ない | LTE予算とbacklogを確認。Wi-Fi接続時は上限なしでdrainする |
| 時刻が未同期 | network復帰後にNTP同期を待つ。同期前のfilenameは連番で衝突を回避 |
| SD空きが少ない | field-statusで保留容量を確認。自動整理のlogを確認し、必要なら動画を回収 |
| Web login後に一覧が出ない | Supabase schema、profile、RLS、Web environmentを確認 |
| Webで再生できない | Worker origin設定、署名URL、R2 bindingを確認 |

## Roadmap

γ (0.3.x) 以降で、camera実演から実際のwildlife monitoring/controlへ進めます。

- **透明送信ゲート** (v0.3.0・実装済み/検証中): 動物が写った動画のみLTE送信。
  判定は決定論ルール+版管理閾値で全数追跡可能 (docs/transparent-gate.md)
- **種の同定 (第2段)**: homelabのバッチで送信済み動画へ事後ラベル (選別には関与しない)
- 動画から対象動物の **頭数を計数** し、誤検知と複数個体を区別する
- 判定結果に基づく **落とし扉制御** を統合する
- 制御系は **通信断・推論不達では保留（作動させない）** を既定にする
- **電源喪失時は扉開放** となるmechanical/electrical fail-safeを維持する
- device heartbeat/event APIを追加し、Web UIへ実測phaseを表示する

安全側の既定を変える機能は、現地試験と独立したfail-safe確認なしに有効化しません。

## License

MIT License. 全文は [`LICENSE`](LICENSE) を参照してください。

ソフトウェアと `hardware/` 以下の設計データの両方に適用します。第三者製品に由来する測定・複製データは公開範囲に含めていません。
