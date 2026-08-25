# firmware — γ版 箱間リンク（ESP32 / Pi / 母艦）

**13 日無人運転（2026-08-26 〜 09-08）で実際に動いていた実体**をここに置く。
半年後の自分が読んで、**同じ運転をゼロから組み直せる**粒度で書く。

このリンクは 1 台では成立しない。**ESP32・Pi・母艦の 3 台に部品が分かれていて、
3 つ揃って初めて 1 つの系**になる。だから `hardware/enclosure/` と同じく、
**自己完結した 1 サブプロジェクト**としてこのディレクトリにまとめてある。

```
Pi (wildlife-zero)            ESP32 (箱B)                母艦
  ble_advertiser.py  ──BLE──►  wildlife_box_b   ──USB──►  esp32_logger.py
  100ms ごとに CMD 広告        受理判定・PUMP 駆動        シリアルを全部記録
                               beaconA/B を「シリアルにだけ」出す
```

---

## 1. どのファイルが、どのマシンの、どこに置かれるか

| repo 上のファイル | 置くマシン | 置き場所 | 備考 |
|---|---|---|---|
| `esp32-box-b/wildlife_box_b/` | ESP32 | Arduino IDE でスケッチとして開いて書き込む | `wildlife_box_b.ino` + `config.h` の 2 枚で 1 スケッチ |
| `esp32-box-b/diag/`, `esp32-box-b/pump_live/` | ESP32 | 同上（診断用。常用しない） | 回路を疑ったときだけ焼く |
| `pi-advertiser/ble_advertiser.py` | Pi | `~/phase1/ble_advertiser.py` | |
| `pi-advertiser/run_ble.sh` | Pi | `~/phase1/run_ble.sh` | bluetoothd 停止 → rfkill 解除 → 終了時に原状復帰 |
| `pi-advertiser/gamma-run.sh` | Pi | `~/phase1/gamma-run.sh` | 起動のたび epoch を +1 するラッパ |
| `pi-advertiser/wildlife-ble-advertiser.service` | Pi | `/etc/systemd/system/` | `systemctl enable --now` |
| `host-logger/bin/esp32_logger.py` | 母艦 | `~/bin/esp32_logger.py` | |
| `host-logger/bin/gamma-status` | 母艦 | `~/bin/gamma-status` | 健康チェック 1 コマンド |
| `host-logger/systemd/wildlife-esp32-logger.service` | 母艦 | `~/.config/systemd/user/` | `systemctl --user enable --now` |
| `host-logger/udev/99-wildlife-esp32.rules` | 母艦 | `/etc/udev/rules.d/` | root 権限。入れたら `udevadm control --reload && udevadm trigger` |

ログの出先:

| 何 | どこ |
|---|---|
| ESP32 のシリアル全文（母艦） | `~/wildlife-gamma-logs/esp32-YYYYMMDD.log` |
| advertiser の stdout（Pi） | `~/phase1/logs/advertiser.log` |

---

## 2. 鍵の用意（★ここを取り違えると全フレームが `bad_mac`）

**鍵はこのリポジトリに入っていない。** wildlife-cam は public なので、
**鍵の値も、鍵を置いてあるディレクトリも、コミットには含めていない。**
実鍵は Pi・母艦・Windows のローカルに 600 で置いてある（場所は運用者だけが知っている）。

repo に入っているのは **公開テスト鍵の状態**:

- `config.h` の `HMAC_KEY_IS_PLACEHOLDER` は **`1`**（＝ `"phase1-public-test-key"` の ASCII バイト列）。
- この状態はコンパイル時に `#warning` が出て、起動時にも警告行が出る。**無人運用に投入してはいけない。**

### 作り方

```bash
openssl rand -hex 32          # → 64 文字の 16 進文字列。これが「鍵」
```

**★ ESP32 と Pi で「同じバイト列」になる表現に揃えること。ここが唯一かつ最大の落とし穴。**

| 側 | 何を渡すか |
|---|---|
| **ESP32** | 上の 64 文字を **そのまま ASCII 文字列として** 1 文字 = 1 バイトでバイト配列にし、`config.h` の【本番鍵の空欄】に `0x..,` で貼る（64 バイトになる）。貼ったら `HMAC_KEY_IS_PLACEHOLDER` を `0` にする |
| **Pi** | **同じ 64 文字の文字列**を鍵ファイルに 1 行で書き（`chmod 600`）、`gamma-run.sh` 経由で `--key-file` に渡す |

つまり **両側とも「hex を復号したバイナリ 32 バイト」ではなく「hex 文字列そのものの 64 バイト」**を鍵にする。
`ble_advertiser.py` はファイルの中身を `strip()` した**文字列**をそのまま HMAC 鍵にするので、
ESP32 側でうっかり hex を復号して 32 バイトにすると、**両者は一致しない**。

変換の例（ESP32 に貼る配列を作る）:

```bash
python3 -c 'import sys;s=open(sys.argv[1]).read().strip();print(",".join("0x%02X"%ord(c) for c in s))' <鍵ファイル>
```

### 置き場所の渡し方

`gamma-run.sh` は鍵と `epoch` を置くディレクトリを **環境変数 `WILDLIFE_GAMMA_STATE`** から取る。
systemd unit の `Environment=WILDLIFE_GAMMA_STATE=...` を自分の環境に書き換えること
（repo 上は `/REPLACE-ME/state-dir` というプレースホルダになっている）。
そのディレクトリの中身:

| ファイル | 中身 |
|---|---|
| `gamma-hmac.key` | 上の 64 文字。`chmod 600` |
| `epoch` | 数字 1 行。`gamma-run.sh` が起動のたびに +1 して書き戻す（無ければ勝手に作られる） |

### 焼く順番と確認

1. ESP32 を焼く → 2. Pi を再起動 → 3. 母艦のログで `[CMD]` の受理を確認。
`bad_mac` が増え続けるなら鍵が食い違っている。**片方だけ元に戻さないこと。**

---

## 3. `epoch` を毎回 +1 する理由

ESP32 の受理規約は「`seq` が厳密に増えたときだけ点灯を延長する」。
Pi のプロセスが再起動すると `seq` は 0 に戻るので、そのままだと ESP32 は
**全部 `seq_regress` として捨てる**（＝ 13 日間ランプが一度も点かない）。

`epoch` が増えていれば ESP32 は BOOTSTRAP をやり直して `seq` を受け入れ直す。
だから `gamma-run.sh` が **起動のたびに `epoch` を +1 して永続化**している
（`Restart=always` で何度落ちても単調増加。65000 を超えたら 1 に巻き戻す = uint16）。

---

## 4. udev ルールが要る理由

`/dev/ttyUSB0` は既定で `root:dialout` の `0660`。
母艦のロガーは **user 単位の systemd サービス**（`--user`）として動くので、
そのままだとデバイスを開けない。ルールがやること:

- CH340（`1a86:7523`）に **`OWNER=` で所有者を与える**
- **`SYMLINK+="wildlife-esp32"`** で固定名を作る
  → 他の USB シリアルを挿して番号がずれても、サービスは `/dev/wildlife-esp32` を見ればよい

```bash
sudo cp host-logger/udev/99-wildlife-esp32.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
ls -l /dev/wildlife-esp32     # → ttyUSB0 への symlink が出れば成功
```

`OWNER=` のユーザ名は自分の環境に合わせて書き換えること。

---

## 5. ★ `beaconA` / `beaconB` は BLE に出ない。USB を抜くと記録がゼロになる

**これが一番忘れやすい。**

`beaconA`（2 秒ごと: 状態・`bad_mac`・`seq_regress`・`orphan`・`sense_open`）と
`beaconB`（10 秒ごと: uptime・`boot_count`・`V_pump`・`lamp_hot`・duty・τ 判定）は、
ファーム内で **`Serial.printf` でしか出力していない**。
ESP32 は復路の BLE 広告を **一度も出していない**（`esp_ble_gap_*` の advertising 系を呼んでいない）。

つまり:

- **USB シリアルが唯一の観測経路。** ケーブルを抜く／母艦のロガーが死ぬ＝13 日間の記録が丸ごとゼロ。
- そして **記録が無いことは、それ自体はどこにも通知されない。**

だから箱B の ESP32 は母艦の USB に挿しっぱなしにしてある。
`gamma-status` の「ログ鮮度」が最初に見るべき数字なのはこのため
（2 分以上更新が無ければロガーか ESP32 が止まっている）。

---

## 6. 立ち上げ手順（まとめ）

```bash
# --- 母艦 ---
sudo cp host-logger/udev/99-wildlife-esp32.rules /etc/udev/rules.d/    # OWNER= を書き換えてから
sudo udevadm control --reload && sudo udevadm trigger
cp host-logger/bin/esp32_logger.py host-logger/bin/gamma-status ~/bin/
cp host-logger/systemd/wildlife-esp32-logger.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now wildlife-esp32-logger.service

# --- ESP32 ---
# config.h に本番鍵を貼り、HMAC_KEY_IS_PLACEHOLDER=0 にしてから Arduino IDE で書き込む

# --- Pi ---
scp pi-advertiser/{ble_advertiser.py,run_ble.sh,gamma-run.sh} wildlife-zero:phase1/
# 鍵ファイルを state ディレクトリに 600 で置く
sudo cp pi-advertiser/wildlife-ble-advertiser.service /etc/systemd/system/   # Environment= を書き換えてから
sudo systemctl daemon-reload && sudo systemctl enable --now wildlife-ble-advertiser.service

# --- 確認 ---
gamma-status
```

---

## 7. 毎日の見かた

```bash
gamma-status
```

`★` が付いた行だけ見ればよい。特に:

| 出た数字 | 意味 |
|---|---|
| ログ鮮度 > 120 秒 | ロガーか ESP32 が止まっている（§5 のとおり記録がゼロになる） |
| `bad_mac` が増え続ける | 鍵が食い違っている（§2） |
| `seq_regress` が増える | `epoch` が上がっていない（§3） |
| `boot_count` が増える | 電源が不安定 |
| `判定=ng` | τ が据付基準 69ms ±40%（41〜96ms）から外れた＝デッドマン回路の異常 |
| `判定=unknown` | 測れなかった。ok でも ng でもない。続くなら §5 の観測経路を疑う |

---

## 8. 今の repo の状態と、実機との差

- **`DECAY_TAU_BASELINE_MS = 69`** — 2026-08-25 に実機で測った据付基準値。**いま焼いてあるのはこの値。**
  C2 を暫定の電解 10µF から X7S に差し替えたら、必ず測り直してここを書き換えること。
- **`HMAC_KEY_IS_PLACEHOLDER = 1`** — repo は公開テスト鍵。**実機に焼いてあるのは本番鍵で `0`。**
- **`gamma-run.sh` / unit の `WILDLIFE_GAMMA_STATE`** — repo 版だけの外出し。
  2026-08-25 時点で **Pi 上で走っている実物は state ディレクトリをハードコードしている**。
  鍵の場所を public repo に書かないための差分なので、再構築時は `Environment=` を埋めれば同じ動きになる。

ファームの変更履歴と設計上の判断は `esp32-box-b/CHANGES-20260825.md` と
`esp32-box-b/FIX-NOTES.md`、書き込み手順は `esp32-box-b/README.md`。
