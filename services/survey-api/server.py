#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""survey-api -- 電波調査ページ用のローカル測定エンジン (Python 標準ライブラリのみ)。

wildlife-zero の Pi 上で動かし、同ホストの電波調査ページ (静的 HTML) から
localhost の HTTP API として叩く。公開は tailscale serve 経由のみを想定し、
バインドは 127.0.0.1:18085 に固定する (LAN/WAN には直接開かない)。

エンドポイント:
  GET  /api/status          → {ok, host, time, battery_mode?}
  POST /api/quick           → 無断線クイック測定 (~30-60s)。LTE(RSRP/RSRQ/SNR)、
                              在圏オペレータ、WiFi 上位5件、上りプローブをまとめて返す。
  POST /api/fullscan        → carrier-scan.sh v2 を --json で非同期起動 (LTE 数分断)。
  GET  /api/fullscan/status → {state: idle|running|done|error, result?, error?}
  GET  /                    → static/index.html (tailscale serve が別マウントする
                              場合の開発用フォールバック。本番の "/" 静的配信は serve 側)

依存コマンドが無い環境 (母艦など) では各測定が {error:"tool-missing", tool:...}
を返し、サーバ自体は落ちない (graceful degrade)。carrier-scan.sh は root 権限が
要るため、systemd 上では sudo -n 経由で起動する (sudoers 設定は README 参照)。
"""

import json
import os
import re
import shutil
import socket
import subprocess
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---- 設定 (公開は tailscale serve 経由のみ。バインドは 127.0.0.1 固定) --------
HOST = os.environ.get("SURVEY_API_HOST", "127.0.0.1")
PORT = int(os.environ.get("SURVEY_API_PORT", "18085"))

SERVICE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(SERVICE_DIR, "static")
# services/survey-api/ の 2 つ上がリポジトリ (wildlife-cam) ルート。
APP_HOME = os.environ.get("WILDLIFE_CAM_HOME") or os.path.dirname(os.path.dirname(SERVICE_DIR))

# carrier-scan.sh は v2 (PR #10) が --json に対応。テスト時はスタブへ差し替え可。
CARRIER_SCAN = os.environ.get("SURVEY_CARRIER_SCAN", os.path.join(APP_HOME, "scripts", "carrier-scan.sh"))
# fullscan の多重起動を弾くロックファイル (別プロセスからの手動起動も一応ガード)。
LOCK_FILE = os.environ.get("SURVEY_FULLSCAN_LOCK", os.path.join(tempfile.gettempdir(), "wildlife-fullscan.lock"))
# carrier-scan は root が要る。sudo を挟むか (既定 1)。テストでは 0 にして直接起動。
USE_SUDO = os.environ.get("SURVEY_FULLSCAN_SUDO", "1") == "1"

# クイック測定の上りプローブ (site-survey.sh 相当。無断線で短時間に収める)。
UPLOAD_MB = float(os.environ.get("SURVEY_UPLOAD_MB", "2"))
UPLOAD_URL = os.environ.get("SURVEY_UPLOAD_URL", "https://speed.cloudflare.com/__up")
UPLOAD_TIMEOUT = int(os.environ.get("SURVEY_UPLOAD_TIMEOUT", "20"))

FULLSCAN_MAX_S = int(os.environ.get("SURVEY_FULLSCAN_MAX_S", "600"))

FULLSCAN_NOTE = (
    "全キャリアスキャン中は LTE がおおむね 3〜5 分切れます。"
    "テザリングや別 WiFi 経由で接続していれば tailscale は生きたままです。"
    "スキャン終了時に自動で網登録を復帰します。"
)

# ---- 非同期 fullscan ジョブの状態 ------------------------------------------
_job_lock = threading.Lock()
_job = {
    "state": "idle",      # idle | running | done | error
    "site": None,
    "started_at": None,   # epoch
    "finished_at": None,
    "result": None,       # JSON (dict) on done
    "error": None,        # str on error
}


def _now_iso():
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def _run(cmd, timeout, input_bytes=None):
    """コマンド実行。戻り値 (rc, stdout, stderr)。存在しない/失敗しても例外を投げない。"""
    try:
        p = subprocess.run(
            cmd,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
        )
        return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")
    except FileNotFoundError:
        return 127, "", "command not found"
    except subprocess.TimeoutExpired:
        return 124, "", "timeout"
    except Exception as e:  # noqa: BLE001  (測定は落とさない)
        return 1, "", str(e)


# ===========================================================================
# 測定関数 (いずれもツール不在なら {error:"tool-missing"} を返す)
# ===========================================================================

def _mmcli_modem_index():
    rc, out, _ = _run(["mmcli", "-L"], timeout=8)
    if rc != 0:
        return None
    m = re.search(r"/Modem/(\d+)", out)
    return m.group(1) if m else None


def measure_lte():
    """mmcli --signal-setup=5 + --signal-get で RSRP/RSRQ/SNR、-m で在圏/オペレータ。"""
    if not shutil.which("mmcli"):
        return {"error": "tool-missing", "tool": "mmcli"}
    idx = _mmcli_modem_index()
    if idx is None:
        return {"error": "no-modem"}

    info = {"modem": idx}
    # 在圏情報 (state / operator / access-tech / signal quality)
    rc, out, _ = _run(["mmcli", "-m", idx], timeout=8)
    if rc == 0:
        for key, pat in (
            ("state", r"state:\s*([^\n]+)"),
            ("operator", r"operator name:\s*([^\n]+)"),
            ("operator_code", r"operator id:\s*([^\n]+)"),
            ("access_tech", r"access tech:\s*([^\n]+)"),
            ("registration", r"registration:\s*([^\n]+)"),
        ):
            m = re.search(pat, out)
            if m:
                info[key] = _strip_ansi(m.group(1)).strip()
        m = re.search(r"signal quality:\s*(\d+)\s*%", out)
        if m:
            info["signal_quality_pct"] = int(m.group(1))

    # 詳細な RSRP/RSRQ/SNR は --signal-get。--signal-setup=5 で更新を有効化。
    _run(["mmcli", "-m", idx, "--signal-setup=5"], timeout=8)
    time.sleep(3)  # 1 サンプル貯める (~30-60s の予算内)
    rc, out, _ = _run(["mmcli", "-m", idx, "--signal-get"], timeout=8)
    if rc == 0:
        for key, pat in (
            ("rsrp_dbm", r"rsrp:\s*(-?\d+(?:\.\d+)?)\s*dBm"),
            ("rsrq_db", r"rsrq:\s*(-?\d+(?:\.\d+)?)\s*dB"),
            ("snr_db", r"s(?:nr|inr):\s*(-?\d+(?:\.\d+)?)\s*dB"),
            ("rssi_dbm", r"rssi:\s*(-?\d+(?:\.\d+)?)\s*dBm"),
        ):
            m = re.search(pat, out)
            if m:
                info[key] = float(m.group(1))
    return info


def _strip_ansi(s):
    return re.sub(r"\x1b\[[0-9;]*m", "", s)


def measure_wifi(top=5):
    """nmcli dev wifi list --rescan で上位 top 件 (SIGNAL 降順)。"""
    if not shutil.which("nmcli"):
        return {"error": "tool-missing", "tool": "nmcli"}
    rc, out, err = _run(
        ["nmcli", "--terse", "--fields", "IN-USE,SIGNAL,SSID,BARS,CHAN",
         "dev", "wifi", "list", "--rescan", "yes"],
        timeout=25,
    )
    if rc != 0:
        return {"error": "nmcli-failed", "detail": (err or "").strip()[:200]}
    rows = []
    for line in out.splitlines():
        if not line.strip():
            continue
        # nmcli --terse は ':' 区切り (値中の ':' は '\:' でエスケープ)。site-survey.sh と同じ簡易分割。
        parts = re.split(r"(?<!\\):", line)
        if len(parts) < 5:
            continue
        inuse, signal, ssid, bars, chan = parts[0], parts[1], parts[2], parts[3], parts[4]
        try:
            sig = int(signal)
        except ValueError:
            continue
        rows.append({
            "in_use": inuse.strip() == "*",
            "signal": sig,
            "ssid": ssid.replace("\\:", ":") or "(非公開/不明)",
            "bars": bars,
            "chan": chan,
        })
    rows.sort(key=lambda r: r["signal"], reverse=True)
    return rows[:top]


def measure_upload():
    """site-survey.sh 相当の上りプローブ。curl で小サイズ POST し速度を測る。"""
    if not shutil.which("curl"):
        return {"error": "tool-missing", "tool": "curl"}
    nbytes = int(UPLOAD_MB * 1024 * 1024)
    fd, path = tempfile.mkstemp(prefix="survey-up.")
    try:
        with open(fd, "wb") as f:
            # 圧縮で速度が水増しされないよう乱数で埋める (実クリップに近い非圧縮)。
            f.write(os.urandom(nbytes))
        rc, out, err = _run(
            ["curl", "-s", "-o", "/dev/null", "--max-time", str(UPLOAD_TIMEOUT),
             "-w", "%{http_code} %{size_upload} %{speed_upload} %{time_total}",
             "-X", "POST", "--data-binary", "@" + path, UPLOAD_URL],
            timeout=UPLOAD_TIMEOUT + 5,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
    fields = out.split()
    if rc != 0 or len(fields) < 4:
        return {"error": "upload-failed", "detail": (err or "timeout").strip()[:200]}
    http_code, size_up, speed_up, time_total = fields[:4]
    try:
        mbps = round(float(speed_up) * 8 / 1_000_000, 2)
    except ValueError:
        return {"error": "upload-failed", "detail": "unparseable metrics"}
    return {
        "mbps": mbps,
        "http_code": http_code,
        "sent_mb": round(float(size_up or 0) / 1048576, 1),
        "time_total_s": float(time_total or 0),
    }


def battery_mode():
    """バッテリ/電源状態が読めれば返す (Pi では通常無いので None のことが多い)。"""
    base = "/sys/class/power_supply"
    try:
        for name in os.listdir(base):
            sf = os.path.join(base, name, "status")
            if os.path.isfile(sf):
                with open(sf) as f:
                    return f.read().strip()
    except OSError:
        pass
    return None


# ===========================================================================
# fullscan (carrier-scan.sh v2 --json を非同期起動)
# ===========================================================================

def _fullscan_worker(site):
    cmd = []
    if USE_SUDO:
        cmd += ["sudo", "-n"]
    cmd += [CARRIER_SCAN, "--json", "--yes"]
    if site:
        cmd.append(site)
    rc, out, err = _run(cmd, timeout=FULLSCAN_MAX_S)
    with _job_lock:
        _job["finished_at"] = int(time.time())
        if rc == 0 and out.strip():
            try:
                _job["result"] = json.loads(out)
                _job["state"] = "done"
                _job["error"] = None
            except json.JSONDecodeError:
                _job["state"] = "error"
                _job["error"] = "carrier-scan の出力を JSON として解釈できません: " + out.strip()[:300]
        else:
            _job["state"] = "error"
            detail = (err or out or "").strip()[:400]
            _job["error"] = "carrier-scan 失敗 (rc=%d): %s" % (rc, detail)
    try:
        os.unlink(LOCK_FILE)
    except OSError:
        pass


def start_fullscan(site):
    """起動できたら {started:True}, 多重なら {error:"busy"} を返す。"""
    with _job_lock:
        if _job["state"] == "running":
            return False, {"error": "busy", "message": "既に全キャリアスキャンが実行中です",
                           "started_at": _job["started_at"]}
        # OS レベルのロック (別プロセスからの手動起動もガード)
        try:
            fd = os.open(LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            os.write(fd, ("%d %s\n" % (int(time.time()), site or "")).encode())
            os.close(fd)
        except FileExistsError:
            return False, {"error": "busy", "message": "ロックファイルが存在します (別プロセスがスキャン中)",
                           "lock": LOCK_FILE}
        _job.update({
            "state": "running", "site": site, "started_at": int(time.time()),
            "finished_at": None, "result": None, "error": None,
        })
    t = threading.Thread(target=_fullscan_worker, args=(site,), daemon=True)
    t.start()
    return True, {"started": True, "site": site, "note": FULLSCAN_NOTE}


def fullscan_status():
    with _job_lock:
        return {
            "state": _job["state"],
            "site": _job["site"],
            "started_at": _job["started_at"],
            "finished_at": _job["finished_at"],
            "result": _job["result"],
            "error": _job["error"],
            "note": FULLSCAN_NOTE if _job["state"] == "running" else None,
        }


# ===========================================================================
# HTTP ハンドラ
# ===========================================================================

_CTYPES = {
    ".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml", ".ico": "image/x-icon", ".png": "image/png",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "survey-api/1.0"

    # ログは 1 行に抑えて stderr へ (systemd journal 向け)
    def log_message(self, fmt, *args):  # noqa: A003
        import sys
        sys.stderr.write("[survey-api] %s - %s\n" % (self.address_string(), fmt % args))

    def _send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _read_json_body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}

    # ---- GET ----
    def do_GET(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self._send_json({
                "ok": True,
                "host": socket.gethostname(),
                "time": _now_iso(),
                "battery_mode": battery_mode(),
            })
        if path == "/api/fullscan/status":
            return self._send_json(fullscan_status())
        # 静的フォールバック (本番は tailscale serve が "/" を静的配信)
        return self._serve_static(path)

    def do_HEAD(self):  # noqa: N802
        return self.do_GET()

    # ---- POST ----
    def do_POST(self):  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/api/quick":
            self._read_json_body()  # site 等は任意 (今は未使用)
            t0 = time.time()
            result = {
                "ok": True,
                "time": _now_iso(),
                "lte": measure_lte(),
                "wifi": measure_wifi(),
                "upload": measure_upload(),
            }
            result["elapsed_s"] = round(time.time() - t0, 1)
            return self._send_json(result)
        if path == "/api/fullscan":
            body = self._read_json_body()
            site = (body.get("site") or "").strip() or None
            ok, payload = start_fullscan(site)
            return self._send_json(payload, code=200 if ok else 409)
        return self._send_json({"error": "not-found", "path": path}, code=404)

    # ---- 静的配信 ----
    def _serve_static(self, path):
        rel = path.lstrip("/") or "index.html"
        full = os.path.normpath(os.path.join(STATIC_DIR, rel))
        # ディレクトリトラバーサル防止
        if not full.startswith(os.path.realpath(STATIC_DIR) + os.sep) and full != os.path.realpath(STATIC_DIR):
            if not os.path.abspath(full).startswith(os.path.abspath(STATIC_DIR)):
                return self._send_json({"error": "forbidden"}, code=403)
        if os.path.isdir(full):
            full = os.path.join(full, "index.html")
        if not os.path.isfile(full):
            return self._send_json({"error": "not-found", "path": path}, code=404)
        ext = os.path.splitext(full)[1].lower()
        ctype = _CTYPES.get(ext, "application/octet-stream")
        try:
            with open(full, "rb") as f:
                body = f.read()
        except OSError:
            return self._send_json({"error": "read-failed"}, code=500)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)


def main():
    # 起動時に古いロックが残っていて、かつジョブ未実行なら掃除 (再起動後の取り残し対策)
    if os.path.exists(LOCK_FILE):
        try:
            os.unlink(LOCK_FILE)
        except OSError:
            pass
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print("[survey-api] listening on http://%s:%d  (APP_HOME=%s)" % (HOST, PORT, APP_HOME), flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
