#!/usr/bin/env bash
# ZeroClaw の Telegram チャンネル (操作系の唯一の窓口) をセットアップする。
# 実行方法 (Mac から対話実行):
#   ssh -t homelab-ts "ssh -t wildlife-zero-ts 'bash ~/wildlife-cam/scripts/setup-telegram.sh'"
#
# 事前準備:
#   1. Telegram で @BotFather に /newbot → bot 名を決めて token を控える
#   2. 自分の Telegram ユーザー名 (@から始まるもの) を確認
#
# 設計: Telegram は管理者(あなた)専用の操作系窓口。bind-telegram で
#       あなたのユーザー名だけに紐付け、他人からのメッセージは受けない。
set -euo pipefail
ZC="$HOME/zeroclaw-bin/zeroclaw"
[[ -x "$ZC" ]] || { echo "ERROR: $ZC がありません"; exit 1; }

echo "=== ZeroClaw Telegram セットアップ ==="
read -r -p "BotFather で発行した bot token を貼り付け (画面に表示されません): " -s BOT_TOKEN
echo
[[ -n "$BOT_TOKEN" ]] || { echo "ERROR: token が空です"; exit 1; }
read -r -p "あなたの Telegram ユーザー名 (@は不要): " TG_USER
[[ -n "$TG_USER" ]] || { echo "ERROR: ユーザー名が空です"; exit 1; }

echo
echo "--- チャンネル登録 ---"
"$ZC" channel add telegram "{\"bot_token\":\"$BOT_TOKEN\",\"name\":\"wildlife-telegram\"}"
echo "--- あなたのアカウントに紐付け (これ以外からのメッセージは拒否) ---"
"$ZC" channel bind-telegram "$TG_USER"
echo "--- ヘルスチェック ---"
"$ZC" channel doctor || true

echo
echo "--- デーモンをOSサービス化して常駐開始 ---"
"$ZC" service install
"$ZC" service start
sleep 3
"$ZC" service status || true

echo
echo "=== 完了 ==="
echo "Telegram で bot にメッセージを送ると wildlife エージェント (ツールあり・supervised) が応答します。"
echo "停止したいとき: $ZC service stop"
