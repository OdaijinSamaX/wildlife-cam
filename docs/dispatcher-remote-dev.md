# Dispatcher Remote Development

このメモは、母艦上の Claude / Codex が `wildlife-cam` を編集し、SSH 経由で Pi5 親機と Pi Zero 2 W 子機へ配布・確認するための標準フローです。

## 構成

```text
Windows Claude
  -> Linux mothership: /srv/homelab/repos/wildlife-cam
       -> ssh wildlife-parent -> Pi5 parent / wildlife-cam-parent
       -> ssh wildlife-child  -> Pi Zero 2 W child / wildlife-cam-child
```

Pi には Claude / Codex 本体を入れません。特に Pi Zero 2 W は 512MB メモリで、Bluetooth リレー専用ノードと SSH デバッグ対象として扱います。

## SSH alias

母艦の `~/.ssh/config` には次の alias が登録済みです。

- `wildlife-parent`: Pi5 親機。`192.168.68.65`, user `odaijinsamax`, host `OdaiinSamaX`
- `wildlife-child`: Pi Zero 2 W 子機。`192.168.68.56`, user `odaijinsamax`, host `OdaiinSamaX-zero`

ログインは 1Password SSH agent forwarding が使える前提です。鍵の配布や `ssh-copy-id` 相当の作業は、この repo の deploy 手順には含めません。

## sudoers

`scripts/remote-ops.sh status` は sudo なしで実行します。`scripts/remote-ops.sh logs` も、Pi 側の user が `systemd-journal` グループに入っていれば sudo なしで読めます。

`scripts/remote-ops.sh restart` と `deploy` 後の service restart には、Pi 側で NOPASSWD sudoers が必要です。推奨設定例:

```text
odaijinsamax ALL=(ALL) NOPASSWD: /bin/systemctl, /usr/bin/systemctl, /bin/journalctl, /usr/bin/journalctl
```

設定は Pi 側で `sudo visudo` から追加します。Pi5 親機側にはすでに何らかの NOPASSWD 設定が入っている様子で、確認は `sudo -ln` でできます。Pi Zero 2 W 子機側は要設定です。本番運用時に logs だけ読めればよい場合は、`sudo usermod -aG systemd-journal odaijinsamax` でも `journalctl` は読めるようになります。

## 典型ワークフロー

母艦の repo で編集し、対象 Pi へ配布して service を再起動し、journal を確認します。

```bash
cd /srv/homelab/repos/wildlife-cam
scripts/remote-ops.sh deploy parent
scripts/remote-ops.sh restart parent
scripts/remote-ops.sh logs parent -f
```

子機だけを見る場合:

```bash
scripts/remote-ops.sh deploy child
scripts/remote-ops.sh logs child -f
```

両機の SSH と Bluetooth ペアリング数の概況:

```bash
scripts/remote-ops.sh ping
```

本番動作中の Pi Zero 2 W は、基本的に SSH で触らずログ確認や再起動を最小限にします。子機は PIR 検知、録画、Bluetooth file transfer を担当し、余計な常駐プロセスを増やさない方針です。

## v0.0.3.1 実機テスト TODO の消化手順

`docs/development-notes.md` 末尾の `v0.0.3 親子機構成の実機テスト状況` は、次の順に潰します。

1. `scripts/remote-ops.sh ping` で両機の SSH 疎通と Bluetooth paired device 数を確認する。
2. `scripts/remote-ops.sh deploy parent` と `scripts/remote-ops.sh deploy child` で同じ commit を両機へ配布する。
3. 親機で `scripts/remote-ops.sh restart parent` を実行し、`scripts/remote-ops.sh logs parent -f` で `parent_main.py` の待受ログを確認する。
4. 子機で `scripts/remote-ops.sh restart child` を実行し、`scripts/remote-ops.sh logs child -f` で `child_main.py` の起動と armed 状態取得を確認する。
5. Bluetooth RFCOMM channel 4 の接続、PIR検知、録画、子機から親機への file transfer、親機から Worker upload までの end-to-end を確認する。
6. `WILDLIFE_LINK_TRANSPORT=tcp` に切り替えたローカル検証も別途実施し、Bluetooth 切断時のリトライと残置ファイル挙動を確認する。
7. 実測結果を `docs/development-notes.md` の TODO に反映し、確認済み項目をチェックする。

## Pi に置かないもの

- Claude / Codex 本体
- 大きい Node.js / Python 開発ツールチェーン
- 長時間動く検証用プロセス
- 母艦で生成できるログ、スクリーンショット、メモ類

Pi は実行対象、母艦は編集・検証・操作対象として分けます。
