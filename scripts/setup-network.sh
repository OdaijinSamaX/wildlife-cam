#!/usr/bin/env bash
# setup-network.sh -- wildlife-zero のネットワーク恒久対策を冪等に適用する。
#
# 何度実行しても同じ状態になる。新しい Pi に入れ直しても同じ構成を再現できる。
# root で実行すること（sudo bash scripts/setup-network.sh）。
#
# やること:
#  1. lte-his が単独でも名前解決できるよう DNS を修復（8/6 障害の根治）
#  1b. getaddrinfo を IPv4 優先化（8/8 の v6-over-LTE ブラックホール恒久対策）
#  2. journald を永続化（障害後にログを追えるように）
#  3. wildlife-net.log の logrotate 設定
#  4. wildlife-netwatch.service / .timer を導入して有効化（60秒監視）
#  5. 状態ディレクトリ作成
#
# WiFi 側 (wifi-iot) の DNS はいじらない。自宅 DHCP が primary=192.168.68.50,
# secondary=1.1.1.1 を配っており実害が小さいため（dispatch の方針どおり）。

set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "root で実行してください:  sudo bash $0" >&2
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

LTE_CON="lte-his"
WATCH_SCRIPT="$SCRIPT_DIR/wildlife-netwatch.sh"

GAI_CONF="/etc/gai.conf"
GAI_MARK_BEGIN="# >>> wildlife-cam ipv4-preference >>>"
GAI_MARK_END="# <<< wildlife-cam ipv4-preference <<<"

log() { echo "[setup-network] $*"; }

# 冪等な atomic 書き込み。内容が同じなら触らない。
write_if_changed() {
  local path="$1" content="$2"
  if [ -f "$path" ] && [ "$(cat "$path")" = "$content" ]; then
    log "変更なし: $path"
    return 0
  fi
  local tmp; tmp="$(mktemp "${path}.XXXXXX")"
  printf '%s\n' "$content" >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$path"   # 電源断でも 0 バイトにならないよう temp+mv
  log "更新: $path"
}

# /etc/gai.conf に「IPv4 優先」を冪等に投入する。
# getaddrinfo は drop-in ディレクトリを読まず /etc/gai.conf のみを見るため、
# 既存内容(既定は全てコメント)を保ったままマーカーで囲んだ管理ブロックを差し替える。
ensure_gai_ipv4_precedence() {
  local block existing stripped desired tmp
  block="$GAI_MARK_BEGIN
# LTE が IPv4 のみで上がると、Cloudflare 等の AAAA へ向けた v6 SYN が povo 上で
# ブラックホール化し、connect timeout ぶん(AAAA 2 件 x 15s ≒ 30s)だけ毎回ブロックする
# (2026-08-08 障害)。getaddrinfo を IPv4 優先にして v4 を先に返し、v6 の無駄待ちを避ける。
# この 1 行があっても glibc の残りの既定 precedence 表はそのまま使われる(gai.conf 推奨手順)。
precedence ::ffff:0:0/96  100
$GAI_MARK_END"

  existing=""
  [ -f "$GAI_CONF" ] && existing="$(cat "$GAI_CONF")"

  # 既存の管理ブロック(マーカー間)を除去してから付け直す=何度実行しても同じ結果。
  stripped="$(printf '%s\n' "$existing" | awk -v b="$GAI_MARK_BEGIN" -v e="$GAI_MARK_END" '
    $0==b {skip=1; next}
    $0==e {skip=0; next}
    !skip {print}
  ')"

  if [ -n "$stripped" ]; then
    desired="$stripped
$block"
  else
    desired="$block"
  fi

  if [ -f "$GAI_CONF" ] && [ "$(cat "$GAI_CONF")" = "$desired" ]; then
    log "   変更なし: $GAI_CONF (IPv4 優先は適用済み)"
    return 0
  fi
  tmp="$(mktemp "${GAI_CONF}.XXXXXX")"
  printf '%s\n' "$desired" >"$tmp"
  chmod 0644 "$tmp"
  mv -f "$tmp" "$GAI_CONF"   # temp+mv で電源断時の破損を避ける
  log "   更新: $GAI_CONF に IPv4 優先 (precedence ::ffff:0:0/96 100) を適用"
}

# ---------------------------------------------------------------------------
log "1) LTE (lte-his) の DNS を修復 + v4 を先頭3件に固定"
if nmcli -t -f NAME con show | grep -qx "$LTE_CON"; then
  # glibc リゾルバは resolv.conf の先頭 3 件しか使わない。NM は dns-priority が
  # 同値だと IPv6 を IPv4 より前に並べるため、素の設定では先頭 3 件が全部 v6 に
  # なり得る。屋久島で LTE が v4 のみで上がると（v6 ベアラ無し/3G 落ち）その 3 件が
  # 全滅し 8/6 と同じ「名前が引けない」に戻る。
  # 対策: ipv4.dns-priority を ipv6 より小さく（＝優先）して v4 を必ず先頭に出す。
  #   - 正の値のみ使う。負値は NM ではそのコネクションの DNS が排他になり、
  #     自宅の 192.168.68.50 が完全に消えるため採らない（非排他で下位に残す）。
  #   - v6 は静的 1 件のみ + キャリア v6 は捨てて（ignore-auto-dns yes）数を絞り、
  #     万一 NM が v6 を前に並べても先頭 3 件に生きた v4 が確実に入るようにする。
  nmcli con mod "$LTE_CON" \
    ipv4.ignore-auto-dns no \
    ipv4.dns "1.1.1.1 8.8.8.8" \
    ipv4.dns-priority 10 \
    ipv4.route-metric 900 \
    ipv6.ignore-auto-dns yes \
    ipv6.dns "2606:4700:4700::1111" \
    ipv6.dns-priority 200 \
    ipv6.route-metric 900
  log "   lte-his: v4 を dns-priority=10 で先頭に固定, v6 は 1 件に集約, metric=900 維持"
  # 変更を即反映（resolv.conf 更新のため）。失敗しても致命ではない。
  if nmcli -t -f NAME,DEVICE con show --active | grep -q "^${LTE_CON}:"; then
    nmcli con up "$LTE_CON" >/dev/null 2>&1 && log "   lte-his 再アクティベート OK" \
      || log "   lte-his 再アクティベートは後続に委ねる（次の接続時に反映）"
  fi
else
  log "   警告: '$LTE_CON' プロファイルが見つかりません。スキップ"
fi

# ---------------------------------------------------------------------------
log "1b) getaddrinfo を IPv4 優先化 (v6-over-LTE ブラックホール恒久対策 / 8/8)"
# route-metric / dns-priority で v4 を優先しても、getaddrinfo は既定で AAAA を
# 先に返すため、アプリは毎回 v6 を先に試して connect timeout を食う。gai.conf で
# アドレス選択自体を v4 優先にして、この無駄待ちを断つ。
ensure_gai_ipv4_precedence

# ---------------------------------------------------------------------------
log "2) journald を永続化"
mkdir -p /etc/systemd/journald.conf.d
# Raspberry Pi OS は /usr/lib/.../40-rpi-volatile-storage.conf で Storage=volatile を
# 強制している。drop-in はファイル名の辞書順で後勝ちになるため、40 より後ろに
# 並ぶ 99- を使わないと永続化が効かない。古い 10- は掃除する。
rm -f /etc/systemd/journald.conf.d/10-persistent.conf
write_if_changed /etc/systemd/journald.conf.d/99-wildlife-persistent.conf \
"# wildlife-cam: 障害後にログを追えるよう永続化。SD 寿命を考え上限を設ける。
# RPi の 40-rpi-volatile-storage.conf(Storage=volatile) を上書きするため 99- で最後に読ませる。
[Journal]
Storage=persistent
SystemMaxUse=200M
SystemMaxFileSize=20M
SystemMaxFiles=10"
mkdir -p /var/log/journal
systemd-tmpfiles --create --prefix /var/log/journal >/dev/null 2>&1 || true
systemctl restart systemd-journald
log "   /var/log/journal/ を作成し journald を再起動"

# ---------------------------------------------------------------------------
log "3) wildlife-net.log の logrotate を設定"
write_if_changed /etc/logrotate.d/wildlife-net \
"/var/log/wildlife-net.log {
    weekly
    rotate 8
    size 5M
    missingok
    notifempty
    compress
    delaycompress
    copytruncate
}"

# ---------------------------------------------------------------------------
log "4) wildlife-netwatch (60秒監視) を導入・有効化"
if [ ! -x "$WATCH_SCRIPT" ]; then
  chmod +x "$WATCH_SCRIPT" 2>/dev/null || true
fi
# unit は deploy 済みディレクトリのスクリプトを指す（rsync で更新され続ける）。
install -m 0644 "$REPO_DIR/wildlife-netwatch.service" /etc/systemd/system/wildlife-netwatch.service
install -m 0644 "$REPO_DIR/wildlife-netwatch.timer"   /etc/systemd/system/wildlife-netwatch.timer
systemctl daemon-reload
systemctl enable --now wildlife-netwatch.timer >/dev/null 2>&1
log "   wildlife-netwatch.timer を enable + start"

# ---------------------------------------------------------------------------
log "5) 状態ディレクトリを作成"
mkdir -p /var/lib/wildlife-netwatch
touch /var/log/wildlife-net.log

# 実行ビットを確実に
chmod +x "$SCRIPT_DIR/wildlife-netwatch.sh" "$SCRIPT_DIR/net-status.sh" 2>/dev/null || true

log "完了。現在の状態:"
echo "----------------------------------------------------------------------"
nmcli -g ipv4.dns,ipv4.dns-priority,ipv6.dns,ipv6.dns-priority con show "$LTE_CON" 2>/dev/null \
  | sed 's/^/  lte-his dns(v4,prio,v6,prio): /'
echo "  resolv.conf 先頭3件(v4であること):"; grep '^nameserver' /etc/resolv.conf | head -3 | sed 's/^/    /'
if grep -q '^precedence ::ffff:0:0/96' "$GAI_CONF" 2>/dev/null; then
  echo "  gai.conf IPv4優先: 適用済み (precedence ::ffff:0:0/96 100)"
else
  echo "  gai.conf IPv4優先: 未適用(!)"
fi
systemctl is-enabled wildlife-netwatch.timer 2>&1 | sed 's/^/  timer enabled: /'
systemctl is-active  wildlife-netwatch.timer 2>&1 | sed 's/^/  timer active : /'
echo "----------------------------------------------------------------------"
log "確認: ~/wildlife-cam/scripts/net-status.sh"
