# Development Notes

このファイルは、今回のMVP実装で実際に躓いた点と、今後の開発で守るべき運用ルールをまとめたメモです。

## 今回の結論

- ローカルMVPの主要経路は確認済み
- Raspberry Pi -> Worker -> R2 -> Supabase -> Web UI -> 動画再生、まで通った
- ローカル検証では `wrangler dev -- --tunnel` を前提に進める方が安定する

## 実際に躓いた点

### 1. `localhost` を Pi からそのまま使えない

- `web/.env` の `VITE_WORKER_API_URL=http://localhost:8787` は PC 上のブラウザ用
- Raspberry Pi から `http://localhost:8787` を叩くと、Pi 自身を見に行く
- LAN内IPで `wrangler dev -- --ip 0.0.0.0` を試しても、応答が安定しなかった
- 結果として `wrangler dev -- --tunnel` を使うのが最短だった

今後の原則:

- Pi からのローカル検証は `--tunnel` を優先する
- `trycloudflare.com` のURLは一時的なので、セッションごとに更新される前提で扱う

### 2. Supabase URL に `/rest/v1/` を付けてはいけない

- `VITE_SUPABASE_URL` はプロジェクトのベースURLを使う
- 正: `https://<project-ref>.supabase.co`
- 誤: `https://<project-ref>.supabase.co/rest/v1/`

今後の原則:

- `createClient()` に渡す URL は常にベースURL

### 3. Pi のユーザー名を `pi` と決め打ちしない

- 実機ユーザーは `odaijinsamax`
- `/home/pi/...` 前提の手順はそのまま使えなかった

今後の原則:

- ドキュメントとコマンド例では `~/wildlife-cam` を優先する
- ユーザー固有パスを固定しない

### 4. Vite のポートは固定ではない

- `5173` が使用中だと `5174`, `5175`, `5176` にずれる
- Worker 側 CORS が `5173` 固定だと再生系が壊れる

今後の原則:

- ローカル開発中の CORS は `localhost` の実際の `Origin` を返す
- README や運用メモでも「ポートがずれる」前提を明記する

### 5. 動画再生は一覧表示より難しい

- 一覧表示できても、再生は別問題
- 今回は `Content-Range` の計算が壊れていて、ブラウザが再生できなかった
- MP4 の中身自体は正常だった

今後の原則:

- 再生不具合ではまず以下を確認する
- `play-url` が 200 を返しているか
- `play/:token` が 206 を返しているか
- `Content-Type`, `Content-Range`, `Content-Length` が正しいか
- 元動画の codec がブラウザ再生可能か

## ユーザーからの重要な指示

### 1. まずはMVPを完成させる

優先順位:

- 動画のクラウド保存
- DB へのメタデータ登録
- 小規模 Web UI での閲覧

後回し:

- AI判定
- ポイント
- 決済
- ランキング
- 本番向け消費者UI
- LTE

### 2. 推奨構成は維持する

- Frontend: Vite + React
- Hosting: Cloudflare Pages
- API: Cloudflare Workers
- Object Storage: Cloudflare R2
- Database: Supabase / PostgreSQL
- Auth: Supabase Auth

### 3. ローカルでまず通す

- デプロイは後回し
- まずローカルでアップロード、一覧、再生まで通す

### 4. 手順説明は具体的に

- 抽象的な説明ではなく、実行コマンド単位で案内する
- 実機のユーザー名やパスに合わせて説明する
- 必要なら PC 側のIPやURLもこちらで確定する

### 5. 可能な範囲は自律して実行する

- Web / Worker / Pi に対して、こちらで実行可能なデプロイや再起動や反映確認は止まらず進める
- 止まるのは認証情報不足や外部サービス権限不足の時だけ
- ユーザーへの説明は「今どの層を確認しているか」が分かる形で出す

## 次回以降の開始手順

1. `worker/.dev.vars` を確認
2. `web/.env` を確認
3. `npm run dev -- --tunnel` で Worker 起動
4. 出てきた tunnel URL を `web/.env` に入れる
5. `npm run dev` で Web 起動
6. `http://localhost:<vite-port>` でログイン確認
7. Pi から `upload_video.py` を実行
8. 一覧表示と再生を確認

## 将来の改善候補

- `trycloudflare.com` 依存をやめて正式デプロイへ進む
- Pi 側にリトライジョブを追加する
- Web UI に admin 用のメモ編集・ステータス更新を追加する
- `traps` テーブルを本格運用し、名称・設置位置・最終電波強度なども管理する
- ローカル起動スクリプトを用意して tunnel URL 更新を楽にする

## 2026-05-19 追加メモ: armed 制御

- `public.traps` テーブルを追加し、`trap_id` ごとの `is_armed` を持つようにした
- Web UI から `admin` が armed ON/OFF を切り替えられる
- Pi は Worker の `GET /traps/:trap_id` を定期取得して armed 状態を確認する
- Worker 側でも disarmed trap の upload 系を拒否するため、Pi の状態反映が少し遅れてもクラウド登録は止まる

今後の原則:

- Pi の常時起動と検知有効化は分けて考える
- 「通電中」と「armed」は別状態として扱う
- trap 制御の設定値は Pi ローカルではなくサーバ側を正とする

## 2026-05-20 追加メモ: 本番反映と運用

### 1. Pages の確認URLに注意

- `https://3d996045.wildlife-cam-web.pages.dev` のような URL はデプロイ固有URL
- 最新版確認は `https://wildlife-cam-web.pages.dev` を使う
- 固定の古いデプロイURLを見続けると、コードは直っていても古い画面に見える

### 2. `traps` は Web から直接 Supabase を読まない方が安定する

- 当初は Web が `traps` を Supabase から直接取得していた
- 実データはあるのに UI で 0 件になる切り分けが煩雑だった
- そのため Web の trap 一覧取得と armed 更新は Worker API に寄せた

今後の原則:

- `videos` の閲覧は Supabase 直でもよい
- 制御系の状態 (`traps`) は Worker 経由に寄せる

### 3. Pi はコード更新済みでも service 再起動しないと古いまま

- Pi 上の `main.py` / `uploader.py` / `sensor.py` を更新しただけでは反映されない
- `sudo systemctl restart wildlife-cam` までやって初めて新ロジックが動く

今後の原則:

- Pi へファイルを送ったら、その場で `python3 -m py_compile` と service 再起動まで行う
- 再起動後は `journalctl -u wildlife-cam -n 20 --no-pager` で初期ログを確認する

### 4. `GPIO busy` は二重起動のサイン

- `wildlife-cam.service` が動作中に `python3 main.py` を手で叩くと `GPIO busy` になる
- これはセンサー故障ではなく、同じ GPIO を別プロセスが掴んでいるだけ

今後の原則:

- systemd 常駐中は手動起動しない
- 手動確認時は `sudo systemctl stop wildlife-cam` を先に行う

### 5. `OFF -> ON` は即録画ではなく待機復帰

- `停止中` から `監視中` に戻しても、その瞬間に録画は始まらない
- 正しい挙動は「動体検知待機に戻る」
- 見えづらかったため Pi ログに `Trap <id> is armed -- resuming motion detection` を追加した

今後の原則:

- ON 復帰の確認は録画開始ではなくログで見る
- 録画確認はその後に PIR を反応させて行う

### 6. 今回こちらで実施した本番作業

- Supabase に `public.traps` を前提とした運用へ揃えた
- Worker を本番デプロイした
- Web を複数回本番デプロイした
- Pi (`odaijinsamax@192.168.68.65`) に SSH し、`main.py` / `uploader.py` / `sensor.py` を更新した
- `wildlife-cam.service` を再起動し、armed 制御のログまで確認した
