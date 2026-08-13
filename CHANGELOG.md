# Changelog

バージョン規約 (2026-08-13 制定):
**世代 = マイナー番号** で管理する。全体を 0.x に留めるのは研究開発版であることの明示
(v1.0.0 は将来、複数台の実運用移管を果たした日のために取っておく)。

| 世代 | 版系列 | 意味 |
|---|---|---|
| α | 0.1.x | プロトタイプ期 (屋久島設計以前・親子機/クラウドMVP) |
| β | 0.2.x | 屋久島設置版 (単機フィールド投入と現地で得た耐障害化) |
| γ | 0.3.x | 回収後の進化 (透明送信ゲート・エージェント化以降) |

タグは「フィールドの機体に配備した状態」に注釈付きで打ち、GitHub Release に変更概要を残す。

---

## v0.3.0 (γ開幕) - unreleased

- **透明送信ゲート**: 野生動物が写った可能性のある動画のみ LTE 送信し、それ以外は
  `videos/held/` に保管する。判定は学習モデルを使わず決定論ルール
  (フレーム差分+ブロブ特徴+版管理閾値 `config/screen_rules_v1.json`) のみで行い、
  全クリップに judgment.json (特徴量生値・各ルール評価・判定) を記録する。
  保管動画は削除しないため偽陰性率を回収後に実測できる。設計文書 `docs/transparent-gate.md`。
- **SD 容量ガード**: 使用率 80% で Telegram に回収要請を通知、95% で録画を停止して
  データを保全する (`storage_guard.py`)。罠カードに SD 使用率を常時表示
  (heartbeat 同乗 + `traps.storage_pct` 列 = `supabase/traps_storage.sql`)。
- **エージェントチャット** (#18): Web に読み取り専用の「カメラに聞く」窓口。
  質問は Supabase RLS 経由、Pi 上のブリッジ (`pi/agent_chat_bridge.py`) が
  ZeroClaw 受付エージェント (ツール無し) で回答を生成する。操作系は Telegram のみ。
- ZeroClaw (v0.8.4 armv7) を Pi に導入し、OpenAI Codex OAuth (ChatGPT サブスク)
  直結で gpt-5.6-sol を頭脳として使えることを実証 (デーモン常駐 RSS 実測 1.7MB)。

## v0.2.0 (β最終・屋久島設置版) - 2026-08-12

屋久島展開 (2026-08-09〜12) で実戦投入・現地デバッグした版のまとめ。

### 遠隔設定チェーン (#15, #17)
- 録画時間・撮影間隔・PIR持続判定 (`motion_sustain_seconds`) を Web UI から遠隔変更
  可能にした (R2 `trap-config/<id>.json` → GET /traps/:id → Pi が毎周適用)。
  優先順位 = サーバ設定 > .env > 既定。通信断時は直近取得値を維持。
- **PIR 3秒持続ゲート**により誤検知パルス (実測幅1.9s・約1回/6分) を遮断。
  誤検知→25MB送信→そのTXがPIRを再誤発報させる自己増殖ループ (RF干渉・実測で証明)
  を断ち切った。
- 動画一覧をフィールド投入 (8/11 15:30) 以降の全件表示に変更。スマホ表示の崩れを修正 (#16)。

### 現地で確定した運用値
- 1080p / **2Mbps** / 30秒 (1本約4.5MB・従来25MBの1/6)・撮影間隔300秒
- `CAMERA_BUFFER_COUNT=2` (CMA枯渇による録画開始失敗の緩和・cma拡張はユーザー判断で見送り)
- PIR: 感度=12時+2/8 (対話較正・3mで最長連続9.5s)・Tx最小・Hジャンパ

### 耐障害化 (屋久島前後の現地知見)
- camera-fixed-focus (8/9): AfMode=Manual + `WILDLIFE_LENS_POSITION` で焦点固定
- lte-ipv6-armfix (8/8): v6ブラックホール対策 (gai.conf v4優先) + arm確認の
  背景スレッド化 (`arm_monitor.py`) で PIR サンプリング周期を保護
- field-resilience (8/7): LTE送信予算 (250MB/h ローリング窓・超過時はSD保留→自動再開)、
  バックログ過多時の新しい順送信
- network-failover-hardening (8/7): LTE単独時DNS全滅の修復、自己復旧watchdog
  (`wildlife-netwatch`)、journald永続化
- `rpi-connect` 一式停止 (journal洪水=毎時10.7万行・swap漸増の主因)、
  `wildlife-cam.service` の再起動レート制限撤廃、リセット要因記録 (`get_rsts`) の常時監視

## v0.1.x (α・プロトタイプ期) - 2026-05

番号は当時のまま保存 (この期の実タグは無し):

### v0.0.3 - 2026-05-22
- 親子機モード (`WILDLIFE_NODE_ROLE`: standalone/parent/child)、Bluetooth RFCOMM リレー、
  役割別 entrypoint (`parent_main.py`/`child_main.py`)
- 子機が Worker API から armed 状態を直接取得する設計

### v0.0.2 - 2026-05-20
- Cloudflare Worker + R2 + Supabase + Vite/React の クラウドMVP (アップロード・一覧・再生)
- `public.traps` による armed 制御 (disarmed 時は検知・録画・送信を停止)
- Web UI の罠制御パネル (admin限定トグル)
