# Changelog

## network-failover-hardening - 2026-08-07

- LTE 単独時に DNS が 1 つも設定されず名前解決が全滅していた 2026-08-06 の障害を修復した（`lte-his` の `ipv4/ipv6.ignore-auto-dns` を `no` に戻し、保険として公開 DNS を併記）。
- ネットワーク自己復旧 watchdog `wildlife-netwatch`（60 秒間隔・L3/DNS/L7 の複合判定・段階的エスカレーション・録画中は待つレート制限付き最終手段 reboot）を追加した。
- journald を永続化した（RPi の `Storage=volatile` 強制を `99-` drop-in で上書き）。再起動をまたいでログを追える。
- 非プログラマ向けの日本語状態確認スクリプト `scripts/net-status.sh` を追加した。
- 上記を冪等な `scripts/setup-network.sh` に集約し、`deploy.sh` から自動適用されるようにした。
- 運用ドキュメント `docs/network-failover-hardening.md` を追加した。

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
