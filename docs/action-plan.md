# 今後のアクションプラン (2026-06-10 時点)

このドキュメントは、リポジトリ全体 (Pi 側 Python、Cloudflare Worker、Web UI、Supabase スキーマ、各種ドキュメント) をレビューした上で、今後の開発の優先順位と具体的なタスクを整理したものです。

## 現状の整理

### できていること

- v0.0.2 で Standalone 構成の主要経路はローカル・本番ともに確認済み
  - Pi → Worker → R2 → Supabase → Web UI (一覧・再生・armed 制御)
  - Worker / Pages は本番デプロイ済み
- v0.0.3 で親機子機構成 (Pi 5 親機 + Pi Zero 2 W 子機、Bluetooth RFCOMM / TCP リレー) を実装済み
- `supabase/schema.sql` には AI 判定向けカラム (`species`, `confidence`, `points`, `analysis_status` など) が先行して用意済み

### できていないこと・リスク

1. **v0.0.3 親子機構成は実機未テスト** (`docs/development-notes.md` のチェックリスト全項目が未消化)
2. **アップロード失敗時のリトライ機構がない**
   - standalone / child とも失敗ファイルは「残置」止まりで、再送ジョブが存在しない
   - `pi/upload_video.py` の `upload_queue/` も再試行する仕組みがない
3. **テスト・CI が一切ない** (`.github/` なし、ユニットテストなし、lint なし)
4. **親機リレーサーバの堅牢性が弱い**
   - ソケットにタイムアウトがなく、子機が固まると親機が永久にブロックする
   - 1 接続ずつの逐次処理 (子機 1 台の MVP では許容範囲)
5. **セキュリティ面の宿題**
   - 全 trap 共通の単一 `DEVICE_API_KEY` (端末紛失時に全体のキーローテーションが必要)
   - `config/.env` がリポジトリにコミットされる運用 (現状は秘密情報なしだが事故りやすい)
6. **細かい既知問題**
   - Worker の `upsertTrapHeartbeat` が `is_armed` を直前読み値で上書きするため、admin の PATCH と競合すると armed 切替が巻き戻る可能性がある
   - `runtime.py` が `camera._camera.close()` と内部属性へ直接アクセスしている
   - README の「ハードウェア配料」は「配線」の誤記

## フェーズ別アクションプラン

### フェーズ 1: v0.0.3.1 — 親子機構成の実機疎通 (最優先)

development-notes の未消化チェックリストをそのまま実行する。

1. ローカル PC 2 プロセスで `WILDLIFE_LINK_TRANSPORT=tcp` の疎通確認 (実機より先にプロトコル自体を検証)
2. Pi 5 で `parent_main.py`、Pi Zero 2 W で `child_main.py` の起動確認
3. Bluetooth ペアリングと RFCOMM channel 4 での接続確立
4. PIR 検知 → 録画 → 子機→親機転送 → Worker upload の end-to-end 疎通
5. link 切断時のリトライ・残置ファイル挙動の確認と記録
6. 結果を `docs/development-notes.md` に追記し、必要なら v0.0.3.1 としてタグ付け

完了条件: チェックリスト 6 項目すべてにチェックが付き、実機での運用手順が README / docs に反映されている。

### フェーズ 2: v0.0.4 — 信頼性向上 (実機テストで見つかる問題と並行)

1. **再送キューの実装**
   - 失敗ファイルを `upload_queue/` に統一して退避し、メタデータ (trap_id, captured_at) を JSON で併置
   - 起動時および定期 (systemd timer) にキューを再送するジョブを追加
   - standalone / child / parent の 3 経路すべてで同じキューを使う
2. **リンク層の堅牢化**
   - `link.py` の全ソケットに `settimeout()` を設定 (受信・接続とも)
   - 親機側で受信失敗時の一時ファイル掃除を確実にする
3. **運用ガード**
   - ディスク残量チェック (録画前に空き容量を確認し、閾値以下なら古い残置ファイルから削除)
   - `logs/wildlife.log` のローテーション (logging.handlers.RotatingFileHandler か logrotate)
4. **Worker の競合修正**
   - `upsertTrapHeartbeat` は `last_seen_at` のみ更新し、`is_armed` を触らないようにする

### フェーズ 3: テスト・CI 基盤

コストが低く効果が高い順に:

1. **GitHub Actions の追加**
   - Python: `python3 -m py_compile` + `ruff check`
   - Worker: `tsc --noEmit` + `wrangler deploy --dry-run`
   - Web: `tsc --noEmit` + `npm run build`
2. **ユニットテストの導入 (純粋関数から)**
   - `link.py` の send/receive プロトコル (TCP ループバックでテスト可能)
   - Worker の `signToken`/`verifyToken`、`parseHttpRange`/`contentRangeBounds`、`buildR2Key` (vitest)
   - 過去に実際に壊れた `Content-Range` 計算は回帰テストの価値が特に高い
3. **デプロイの再現性**
   - `deploy.sh` を親子機構成に対応させ、転送後に `py_compile` + service 再起動 + journalctl 確認まで自動化 (development-notes の運用原則のコード化)

### フェーズ 4: 運用・セキュリティ整備

1. **監視**
   - `traps.last_seen_at` を使った「一定時間ハートビートなし = オフライン」表示を Web UI に追加
   - 将来的にはオフライン時の通知 (メール等) を Worker cron で
2. **認証の強化**
   - trap ごとの device token (`traps` テーブルに token hash カラムを追加し、Worker で照合)
   - 紛失・盗難時に該当 trap だけ無効化できるようにする
3. **シークレット運用の整理**
   - `config/.env` はリポジトリから外し、`.env.example` 系のみコミットする方針へ移行
4. **trycloudflare 依存の解消**
   - ローカル開発手順は維持しつつ、Pi の常設設定は本番 Worker URL に固定する

### フェーズ 5: 機能拡張 (MVP 後)

development-notes で「後回し」とされていた項目。スキーマは先行準備済みなので順に着手できる。

1. Web UI: admin 用のメモ編集・ステータス更新 (`videos.status` / `hunter_note` は既存)
2. `traps` の本格運用 (名称・設置位置・電波強度などのメタデータ管理)
3. AI 判定パイプライン (`species` / `confidence` / `analysis_status` カラムを使用)
4. ポイント・ランキング・決済・消費者向け UI
5. LTE 対応

## 直近 2 週間の推奨タスク (具体)

| 優先 | タスク | 規模 |
|------|--------|------|
| 1 | TCP transport でのローカル親子疎通テスト | 小 |
| 2 | Pi 実機での v0.0.3 end-to-end テスト (チェックリスト消化) | 中 |
| 3 | `link.py` へのソケットタイムアウト追加 | 小 |
| 4 | 再送キュー + systemd timer | 中 |
| 5 | GitHub Actions (compile / tsc / build) | 小 |
| 6 | `upsertTrapHeartbeat` の is_armed 上書き修正 | 小 |
| 7 | Worker トークン・Range 処理のユニットテスト | 中 |

1・3・5・6 はハードウェアなしで今すぐ着手可能。2 と 4 は実機作業が必要。
