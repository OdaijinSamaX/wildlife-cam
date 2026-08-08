# Changelog

## lte-ipv6-armfix - 2026-08-08

- **LTE の IPv6 ブラックホールを恒久化対策した。** LTE が IPv4 のみで上がると、Cloudflare 等の
  `AAAA` へ向けた v6 SYN が povo 上でブラックホール化し、`is_armed()` の度に connect timeout
  ぶん(AAAA 2 件 × 15s ≒ 30s)ブロックしていた。`scripts/setup-network.sh` に `/etc/gai.conf` の
  IPv4 優先(`precedence ::ffff:0:0/96 100`)を**冪等に**追加し、getaddrinfo が v4 を先に返すようにした。
- **arm 確認を検知ループから分離した(本丸)。** これまで PIR 待機ループ(0.1 秒周期)が毎回
  ブロッキング HTTP で arm 状態を問い合わせており、v6 ブラックホール時は 1 周が最長 30 秒に伸びて
  PIR サンプリング周期が壊れ、「1 秒間の継続動体検知」が数学的に成立しなくなっていた。arm 状態を
  背景スレッド(`arm_monitor.ArmStateMonitor`)で定期取得し、待機ループはメモリ値のみ読むようにした。
  **通信断=保留(作動しない)** の安全思想は monitor 側(初回成功前・応答が古い時は False)で維持する。
- `uploader.WorkerUploader` の `is_armed()` を修正: キャッシュ格納時刻を**レスポンス受領後**に取り直す
  (呼び出しが TTL を超えるとキャッシュが永久失効する不具合)、`requests.Session` を使い回す、
  arm 確認の timeout を `(connect, read) = (3, 10)` タプルに短縮。キャッシュ判定は `time.monotonic()` に変更。
- `sensor.wait_for_sustained_motion()` の継続時間判定を、サンプル回数ではなく `time.monotonic()` の
  **実時間**基準に変更した。
- `scripts/net-status.sh` の「連続オンライン」に時計飛びフォールバックを追加した。RTC 無しの端末が
  圏外起動→NTP 同期で時計が飛ぶと実際より長く出ていた(8/8: 実際 10 分を 20 時間と誤表示)ため、
  端末の uptime を上限に丸めて表示する(`field-status.sh` は本スクリプトを再利用)。
- 検証用に `tests/test_arm_gate_nonblocking.py` を追加(フェイク uploader で「is_armed が 30 秒ブロックしても
  PIR サンプリング周期が保たれる」ことを確認)。運用ドキュメント `docs/network-failover-hardening.md` に
  8/8 の v6-over-LTE ブラックホール障害記録と対処を追記した。

## field-resilience: upload budget - 2026-08-07

- LTE 従量課金対策として **1 時間あたりの送信量に上限**（`WILDLIFE_UPLOAD_BUDGET_MB_PER_HOUR`、既定 250MB、ローリング窓、LTE のときだけ）を設けた。超過時は**送信のみ停止し録画は SD に継続**、予算回復後に自動再開する。カウンタは永続化し再起動をまたいで保持する。
- バックログが閾値（`WILDLIFE_UPLOAD_NEWEST_FIRST_BACKLOG`、既定 10 本）を超えたら**新しい順**に送るようにし、実演で「いま撮れた最新の動画」が古い山に埋もれないようにした。
- 撮影クールダウン（`WILDLIFE_MOTION_COOLDOWN_SEC`、既定 0）と誤検知サーキットブレーカー（`WILDLIFE_BURST_PAUSE_ENABLED`、既定 OFF）は撮り逃し防止のため既定で無効。予備として実装のみ残す。
- 送信待ちの動画が保存上限で黙って消える事故を避けるため、`video_storage.py` のバイト/本数上限を既定無効化し、SD 保護は空き最低 2GiB と保存 14 日で行うように既定値を見直した（削除時は必ずログ）。
- `scripts/field-status.sh` に送信量/上限・送信保留の本数と再開予定・直近1時間の録画本数・SD 残り持続目安を日本語で追加した。運用ドキュメント `docs/upload-budget.md` を追加、現地手順書に「送信保留中」の意味を追記した。

## network-failover-hardening - 2026-08-07

- LTE 単独時に DNS が 1 つも設定されず名前解決が全滅していた 2026-08-06 の障害を修復した（`lte-his` の `ipv4/ipv6.ignore-auto-dns` を `no` に戻し、保険として公開 DNS を併記）。
- ネットワーク自己復旧 watchdog `wildlife-netwatch`（60 秒間隔・L3/DNS/L7 の複合判定・段階的エスカレーション・録画中は待つレート制限付き最終手段 reboot）を追加した。
- journald を永続化した（RPi の `Storage=volatile` 強制を `99-` drop-in で上書き）。再起動をまたいでログを追える。
- 非プログラマ向けの日本語状態確認スクリプト `scripts/net-status.sh` を追加した。
- 上記を冪等な `scripts/setup-network.sh` に集約し、`deploy.sh` から自動適用されるようにした。
- 運用ドキュメント `docs/network-failover-hardening.md` を追加した。
- glibc の resolv.conf 3 件上限による再発リスクを塞いだ: `lte-his` の `ipv4.dns-priority` を
  v6 より優先させ、LTE が IPv4 のみで上がっても**先頭 3 件に必ず生きた v4 リゾルバが入る**ようにした
  （v6 DNS は 1 件に集約）。負値(排他)は使わず自宅 `192.168.68.50` は下位に残す。
- watchdog の健全性判定に **IPv4 名指しの DNS 確認**（`busybox nslookup` で v4 リゾルバへ v4 で直接問い合わせ）を追加し、
  v6 経由で成功して v4 DNS の欠落を見逃す穴を塞いだ。

## v0.0.3 - 2026-05-22

- 親子機モードを追加し、`WILDLIFE_NODE_ROLE` で `standalone` / `parent` / `child` を切り替えられるようにした。
- 役割固定の entrypoint として `parent_main.py` と `child_main.py` を追加し、Pi 5 親機と Pi Zero 2 W 子機を分けて起動できるようにした。
- Bluetooth RFCOMM リレーを追加し、`pybluez2` 経由で子機の録画ファイルを親機へ転送してから既存 Worker API へ upload できるようにした。
- Bluetooth がないローカル開発環境でもリンク部分を検証できるよう、`WILDLIFE_LINK_TRANSPORT=tcp` の検証経路を追加した。
- 子機が Worker API から armed 状態を直接取得できる設計にし、親機は動画受信と Worker upload に集中する構成にした。
- 親子機構成向けの設定例、systemd unit、運用ドキュメントを追加した。
- 依存関係として `pybluez2`, `bluez`, `libbluetooth-dev`, `ffmpeg` を追加した。

## v0.0.2 - 2026-05-20

- Added Cloudflare Worker, R2, Supabase, and Vite + React based MVP architecture for cloud upload, listing, and playback.
- Added `public.traps` based armed control so the Raspberry Pi stays powered on and only detects, records, and uploads while armed.
- Added Worker endpoints for trap polling, trap listing, and trap armed updates, including disarmed upload rejection.
- Added Web UI trap control panel with admin-only armed toggle and Worker-backed trap state loading.
- Updated Pi runtime to poll trap arm state, skip motion detection while disarmed, and log when armed monitoring resumes.
- Documented production deployment flow, Pi operational caveats, Pages URL handling, and troubleshooting findings from end-to-end testing.
