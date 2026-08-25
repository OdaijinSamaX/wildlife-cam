#!/usr/bin/env python3
"""wildlife-cam γ版 箱B ESP32 のシリアルを 13 日間取り続ける。

- 1 行ごとに ISO8601 のタイムスタンプを付ける
- 日付が変わったらファイルを分ける（esp32-YYYYMMDD.log）
- USB が抜けても待って再接続する（黙って死なない）
"""
import datetime as dt
import os
import pathlib
import sys
import time

import serial

DEV = os.environ.get("ESP32_DEV", "/dev/ttyUSB0")
BAUD = int(os.environ.get("ESP32_BAUD", "115200"))
LOGDIR = pathlib.Path(os.environ.get("ESP32_LOGDIR",
                                     os.path.expanduser("~/wildlife-gamma-logs")))
LOGDIR.mkdir(parents=True, exist_ok=True)


def now():
    return dt.datetime.now().astimezone()


def logfile_for(t):
    return LOGDIR / ("esp32-%s.log" % t.strftime("%Y%m%d"))


def emit(fh, text):
    fh.write("%s %s\n" % (now().isoformat(timespec="seconds"), text))
    fh.flush()


def main():
    cur_day = None
    fh = None
    while True:
        try:
            ser = serial.Serial(DEV, BAUD, timeout=5)
            # 閉じたときに ESP32 をリセットしないようにする
            try:
                ser.dtr = False
                ser.rts = False
            except Exception:
                pass
            t = now()
            if fh is None or cur_day != t.date():
                if fh:
                    fh.close()
                cur_day = t.date()
                fh = open(logfile_for(t), "a", encoding="utf-8", errors="replace")
            emit(fh, "[logger] %s を開きました (%d baud)" % (DEV, BAUD))
        except Exception as exc:
            if fh:
                emit(fh, "[logger] 開けません: %r — 5 秒後に再試行" % (exc,))
            time.sleep(5)
            continue

        try:
            while True:
                raw = ser.readline()
                if not raw:
                    continue
                t = now()
                if cur_day != t.date():
                    emit(fh, "[logger] 日付が変わりました")
                    fh.close()
                    cur_day = t.date()
                    fh = open(logfile_for(t), "a", encoding="utf-8", errors="replace")
                emit(fh, raw.decode("utf-8", errors="replace").rstrip("\r\n"))
        except Exception as exc:
            emit(fh, "[logger] 切断: %r — 再接続します" % (exc,))
            try:
                ser.close()
            except Exception:
                pass
            time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
