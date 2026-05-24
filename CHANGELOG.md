# Changelog

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
