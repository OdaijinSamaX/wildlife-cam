# survey-api — 電波調査ページ用ローカル測定エンジン

現地 (屋久島) の設置候補地調べを、スマホの電波調査ページから wildlife-zero (Pi) の
モデム/WiFi で直接測れるようにする常駐 API。Python 標準ライブラリのみ。

- バインドは **127.0.0.1:18085 固定**。LAN/WAN には直接開かない。
- 公開は **tailscale serve** 経由のみ (`/` = 静的ページ、`/api` = この API)。
- ページと同一ホストで動くので、ページからは同一オリジンの `/api/...` を叩くだけ。

## エンドポイント

| メソッド | パス | 用途 |
|---|---|---|
| GET  | `/api/status` | 生存確認 `{ok, host, time, battery_mode?}` |
| POST | `/api/quick` | 無断線クイック測定 (~30-60s)。LTE(RSRP/RSRQ/SNR)・在圏オペレータ・WiFi 上位5件・上りプローブ |
| POST | `/api/fullscan` | `carrier-scan.sh` v2 を `--json` で**非同期**起動 (LTE 数分断)。多重起動はロックで拒否 (409) |
| GET  | `/api/fullscan/status` | `{state: idle\|running\|done\|error, result?, error?}` をポーリング |
| GET  | `/` ほか | `static/` を配信 (本番は tailscale serve が担当。これは開発用フォールバック) |

`/api/quick` 応答例 (抜粋):

```json
{
  "ok": true,
  "lte":    {"operator": "docomo", "rsrp_dbm": -85.0, "rsrq_db": -11.0, "snr_db": 12.0, "access_tech": "lte"},
  "wifi":   [{"ssid": "MyAP", "signal": 72, "in_use": true, "chan": "36"}],
  "upload": {"mbps": 3.4, "http_code": "200", "sent_mb": 2.0}
}
```

依存コマンド (`mmcli` / `nmcli` / `curl`) が無い環境では、その測定だけ
`{"error": "tool-missing", "tool": "mmcli"}` を返す。API 自体は落ちない。

## fullscan と権限 (sudo)

`carrier-scan.sh` は ModemManager 停止と AT ポート占有のため **root が必須**。
API は `odaijinsamax` で動くので、`/api/fullscan` は内部で `sudo -n` 経由で起動する。
次の sudoers を入れておくこと (無いと fullscan が権限エラーで `error` になる):

```
# /etc/sudoers.d/wildlife-survey  (visudo -f で編集)
odaijinsamax ALL=(root) NOPASSWD: /home/odaijinsamax/wildlife-cam/scripts/carrier-scan.sh
```

> `carrier-scan.sh --json` は **v2 (PR #10)** で追加。field-resilience/integration に
> v2 が入った状態でデプロイすること。

## デプロイ

`deploy.sh` はリポジトリ全体を Pi へ rsync するので `services/survey-api/` も一緒に載る。
初回だけ以下を Pi 上で実行 (systemd 常駐化 + serve 公開)。

```bash
# 1) systemd 常駐化
sudo cp /home/odaijinsamax/wildlife-cam/services/survey-api/survey-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now survey-api.service

# 2) sudoers (fullscan 用)
echo 'odaijinsamax ALL=(root) NOPASSWD: /home/odaijinsamax/wildlife-cam/scripts/carrier-scan.sh' \
  | sudo tee /etc/sudoers.d/wildlife-survey
sudo chmod 440 /etc/sudoers.d/wildlife-survey

# 3) tailscale serve (手動 1 回で永続。setup-network.sh には入れない)
#    "/"  → 静的ページ (services/survey-api/static)
#    "/api" → localhost:18085 の API へリバースプロキシ
sudo tailscale serve --bg --set-path / \
     "$(cd /home/odaijinsamax/wildlife-cam/services/survey-api/static && pwd)"
sudo tailscale serve --bg --set-path /api http://127.0.0.1:18085/api
sudo tailscale serve status
```

> tailscale のバージョンで `serve` の引数体系が異なる。上が通らない環境では
> 従来式の `tailscale serve https:443 / <static-dir>` /
> `tailscale serve https:443 /api http://127.0.0.1:18085/api` を使う。
> どちらでも「`/` は静的・`/api` は 18085 へプロキシ」になっていれば良い。

## ローカル動作確認 (母艦・Pi 不在でも可)

```bash
# ポートやスタブを差し替えて起動 (mmcli 等が無くても graceful degrade で動く)
SURVEY_API_PORT=18085 python3 services/survey-api/server.py &
curl -s localhost:18085/api/status | python3 -m json.tool
curl -s -X POST localhost:18085/api/quick | python3 -m json.tool   # 各測定は tool-missing になる
```
