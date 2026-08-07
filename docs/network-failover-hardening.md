# ネットワーク恒久対策（屋久島・WiFi の無い現地運用）

`wildlife-zero`（Pi Zero 2 W / Raspberry Pi OS trixie / NetworkManager + ModemManager）を
WiFi の無い場所へ持ち込んでも、**電源を入れるだけで確実にオンラインになり、途中で落ちても
自力で復帰する**ための構成をまとめる。実装は次の 4 点。

1. LTE 単独時の DNS 修復（8/6 障害の根治）
2. ネットワーク自己復旧 watchdog（`wildlife-netwatch`、60 秒間隔）
3. 永続ジャーナル（障害後にログを追える）
4. 状態確認スクリプト（`net-status.sh`、日本語 OK/NG 表示）

すべて `scripts/setup-network.sh` で冪等に適用でき、`deploy.sh` からも自動適用される。

---

## 2026-08-06 の障害記録（再発時の照合用）

外出先でのプレゼン中に「Pi が一向にネットにつながらない」状態になり実演できなかった。

- 症状: IP は通る（`ping 8.8.8.8` OK）のに、Web UI・アップロード・ブラウザが全滅。
- 真因: **LTE 単独時に DNS サーバが 1 つも設定されていなかった。**
  `lte-his` プロファイルが `ipv4.ignore-auto-dns=true` / `ipv6.ignore-auto-dns=true` で
  キャリア DNS を捨てており、代わりの `dns=` も無かった。自宅では WiFi 側 DHCP が DNS を
  配るため気づけないが、WiFi が無い場所では `/etc/resolv.conf` の nameserver がゼロになる。
- 結果: 名前解決が一切できず（`getent hosts` 失敗、`curl: (6) Could not resolve host`）、
  IP は通るのに全通信が死ぬ。ユーザ体感の「つながらない」と一致。
- 悪化要因: ジャーナルが揮発設定（`/run` のみ）で、事後にログを追えなかった。

---

## 1. DNS 修復（最優先）

`lte-his` が単独でも名前解決できるようにした。

- `ipv4.ignore-auto-dns` / `ipv6.ignore-auto-dns` を `no` に戻し、キャリア DNS を使う。
- 併せて保険として公開 DNS を明示: v4 = `1.1.1.1, 8.8.8.8` / v6 = `2606:4700:4700::1111, 2001:4860:4860::8888`。
- `ipv4.route-metric=900` は維持（WiFi=600 が使えるときは WiFi を優先、が正しい設計）。
- **WiFi 側 (`wifi-iot`) の DNS はいじっていない。** 自宅 DHCP が primary に母艦
  `192.168.68.50`、secondary に `1.1.1.1` を配っており実害が小さいため。

> 補足（実機調査で判明）: 自宅 WiFi は IPv6 を配らず、この機体の **IPv6 default route は
> 常に LTE(wwan0) 側**。そのため v6 対応の宛先（Cloudflare Worker など）は WiFi が死んでいても
> LTE 経由で到達できる。恒久対策で守るのは主に IPv4 の経路。

### 1-b. DNS 先頭 3 件を必ず IPv4 にする（3 件上限による再発リスクの封じ）

**問題**: glibc のリゾルバは `/etc/resolv.conf` の**先頭 3 件の nameserver しか使わない**
（NM 自身がその注記を書き込む）。NM は `dns-priority` が同値だと **IPv6 を IPv4 より前に
並べる**ため、素の設定では LTE 単独時に先頭 3 件が全部 IPv6 になり得た。屋久島で LTE が
**IPv4 のみ**で上がった場合（v6 ベアラが張れない・電波が悪く 3G 落ち等）、その 3 件が全滅して
8/6 と同じ「IP は通るが名前が引けない」に逆戻りする。

**対策**（`setup-network.sh` に実装、冪等）:
- `lte-his` の `ipv4.dns-priority=10` を `ipv6.dns-priority=200` より小さく（＝優先）し、
  **IPv4 リゾルバを必ず先頭に出す**。
- v6 は静的 1 件（`2606:4700:4700::1111`）に集約し、キャリア v6 DNS は捨てる
  （`ipv6.ignore-auto-dns=yes`）。万一 NM が v6 を前に並べても、先頭 3 件に生きた v4 が確実に入る
  よう二重に担保する。
- **`dns-priority` は正の値のみ**を使い、負値は使わない。負値は NM ではそのコネクションの DNS が
  **排他**になり、自宅の `192.168.68.50` が完全に消えてしまうため。正の値なら `.50` は下位に
  残る（resolv.conf には載るが glibc の先頭 3 件からは外れる）。

**自宅 DNS への影響（判断と理由）**: この変更により、**自宅にいる間も名前解決は公開 v4
リゾルバ（1.1.1.1 等）が優先**され、母艦 `192.168.68.50` は先頭 3 件から外れて実質使われなく
なる。この機体（罠）が必要とするのは Cloudflare Worker・接続性チェック・apt などの**公開名の
解決だけ**で、ローカル名の解決には依存しないため、機能上の実害は無いと判断した。`.50` は
resolv.conf の下位に残しており（非排他）、完全には消していない。屋久島で v4 のみでも確実に
名前を引けることを、自宅の利便性より優先した設計。

適用後の LTE 単独時 `resolv.conf`（実測、先頭 3 件が v4）:

```
nameserver 1.1.1.1          ← 1番目 (v4)
nameserver 8.8.8.8          ← 2番目 (v4)
nameserver 210.130.0.20     ← 3番目 (v4 キャリア)
# NOTE: the libc resolver may not support more than 3 nameservers.
nameserver 210.130.1.20
nameserver 2606:4700:4700::1111   ← v6 は保険として最後尾
```

---

## 2. watchdog（恒久対策の本体）

`wildlife-netwatch.timer` が 60 秒ごとに `wildlife-netwatch.service`（oneshot, root）を起動し、
`scripts/wildlife-netwatch.sh` が 1 周期分の健全性判定と復旧措置を行う。

### 健全性判定（単一指標に依存しない）

- **L3**: `1.1.1.1` と `8.8.8.8` への ping（どちらか通れば OK）
- **DNS(v4)**: **v4 リゾルバ（1.1.1.1 / 8.8.8.8）に v4 で直接問い合わせて**回答が返るか
  （`busybox nslookup`。終了コードは当てにならないので出力の回答レコードで判定）。
  通常の `getent` は resolv.conf 先頭の v6 経由で成功してしまい「v4 DNS が死んでいる」状態を
  見逃すため、あえて v4 を名指しで見る。屋久島で LTE が v4 のみになる想定への備え。
- **L7**: `connectivitycheck.gstatic.com` / `cp.cloudflare.com` の `generate_204` が 204 を返すか

判定は **「v4 の名前解決が生きている」ことを必須**とし、その上で L7(204) か L3(ping) の
どちらかで実際に外へ出られれば健全とする（L7 サーバ側の一時障害でも L3 が生きていれば誤発動しない）。
実測で、v4 リゾルバ(:53) を遮断すると `l3=OK` でも `dns4=NG` となり watchdog が異常を検出することを確認済み。

### 連続失敗回数によるエスカレーション

状態は `/run/wildlife-netwatch/` に保持。各措置の後で必ず再判定し、**回復したら即座に
カウンタを 0 に戻す**。60 秒間隔なので、段位 ≒ 連続ダウン分数。

| 連続失敗 | 措置 |
|---|---|
| 1 回 | ログのみ（一過性の可能性） |
| 2 回 | `nmcli con up lte-his`（LTE を張り直す） |
| 3 回 | **wlan0 が default を持つのに外に出られない時だけ** wlan0 を一時降格し LTE に載せ替え（10 分ペナルティ） |
| 4 回 | モデム再初期化（`nmcli radio wwan off/on`） |
| 5 回 | `systemctl restart NetworkManager ModemManager` |
| 6 回 | `systemctl restart tailscaled` |
| 7 回〜 | 30 分の reboot 閾値まで、上記を手を変えて反復 |
| 連続 30 分ダウン | **最後の手段として reboot** |

### wlan0 降格の安全装置（誤発動しない）

- 降格は **default route が wlan0 かつ実際に疎通が死んでいて（3 連続失敗）かつ LTE が使える**
  時だけ発動する。自宅で WiFi が正常なら健全判定になりカウンタが増えないので発動しない。
- 降格中は `wifi-iot` の `autoconnect=no` にして NM の自動再接続を止める。ペナルティ（既定 600 秒）
  が切れたら watchdog が自動で `autoconnect=yes` に戻して WiFi を復帰させる。watchdog が
  途中で死んでも、次回起動時の先頭処理で「ペナルティ切れなら WiFi 復帰」を自己修復する。

### reboot の安全装置

- **1 時間に 1 回まで**（`/var/lib/wildlife-netwatch/last_reboot_epoch` に記録。再起動ループを作らない）
- **録画・アップロード中は reboot しない**（`~/wildlife-cam/videos/` が直近 180 秒以内に
  更新されていれば「作業中」とみなし次周期へ持ち越す）
- 通信断時の罠の挙動については下記「罠は通信断で保留か」を参照。reboot による撮り逃しは原理上起きない。

### ログ

- journal（`journalctl -u wildlife-netwatch`）に加えて `/var/log/wildlife-net.log` に
  **イベント（UNHEALTHY / RECOVERED / ACTION / reboot）を 1 行ずつ**追記する。
  健全なだけの周期は書かない（＝ログが静かなら順調）。`logrotate`（週次・5M）で肥大を防ぐ。
- 「今」の状態は `/run/wildlife-netwatch/status` に毎周期スナップショットされ、`net-status.sh` が読む。

---

## 3. 永続ジャーナル

`/etc/systemd/journald.conf.d/99-wildlife-persistent.conf` で `Storage=persistent` /
`SystemMaxUse=200M`。**Raspberry Pi OS は `/usr/lib/.../40-rpi-volatile-storage.conf` で
`Storage=volatile` を強制している**ため、drop-in はファイル名の辞書順で後勝ちになる仕様上、
`40-` より後ろに並ぶ `99-` を使わないと効かない（ここで一度ハマった）。

これで `/var/log/journal/<machine-id>/` にログが残り、**再起動をまたいで**
`journalctl -b -1` で前回ブートのログを読める。

---

## 罠は通信断で本当に「保留（作動しない）」か（`runtime.py` 確認結果）

reboot 措置が撮り逃しを生まないかの確認。`runtime.py` を読んだ結論は **「通信断時は保留」で正しい**。

- `run_standalone` は起動時に uploader が `WorkerUploader` でなければ（＝ arm ゲートが無いなら）
  既定で例外を投げて停止する（`WILDLIFE_REQUIRE_ARM_GATE`）。arm ゲートが無いまま無条件撮影に
  なる事故を防いでいる。
- ループ先頭で `uploader.is_armed()` を問い合わせ、**LTE 断で例外が出ると `continue`（5 秒待って
  やり直し）**。録画には進まない。
- モーション待機中も `should_continue=_armed_or_pause` が例外時 `False` を返すため、待機は中断され
  録画に入らない。
- したがって **通信が切れている間は録画も送信も行われない**。その最中に watchdog が reboot しても
  失うクリップは無い。録画/送信が実際に走るのは通信が生きているときで、その状況は videos/ の
  更新として現れ、reboot 側がそれを見て保留する。二重に安全。

---

## 現地でユーザ本人が打てるコマンド（非プログラマ向け）

母艦から Tailscale 経由で入るのが基本（`ssh wildlife-zero-ts`）。まず状態を見る:

```bash
# ① 今つながっているか、日本語で一目で確認する（これだけ覚えれば十分）
ssh wildlife-zero-ts '~/wildlife-cam/scripts/net-status.sh'
```

うまくいかないときの「困ったら順に試す」3 つ:

```bash
# ② LTE を張り直す
ssh wildlife-zero-ts 'sudo nmcli con up lte-his'

# ③ それでも駄目なら Pi を再起動する（1〜2 分待ってからもう一度 ① を見る）
ssh wildlife-zero-ts 'sudo reboot'

# ④ 直近のできごと（障害の経緯）を読む
ssh wildlife-zero-ts 'tail -n 30 /var/log/wildlife-net.log'
```

> 何もしなくても watchdog が 60 秒ごとに自動で ②→③ 相当を段階的に試すので、
> 基本は「① で確認して、数分待つ」だけでよい。

---

## 再現性（deploy.sh）

新しい Pi に入れ直しても同じ状態になる。

```bash
cd /srv/homelab/repos/wildlife-cam
./deploy.sh wildlife-zero-ts            # rsync 配布 + 依存導入 + setup-network.sh 自動適用
# 単体で再適用したいとき:
ssh wildlife-zero-ts 'sudo bash ~/wildlife-cam/scripts/setup-network.sh'
```

`setup-network.sh` は何度実行しても同じ結果になる（冪等）。`lte-his` プロファイルが無いノードでは
DNS 修復を安全にスキップする。
