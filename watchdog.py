"""systemd watchdog backed by explicit main-loop progress."""

import logging
import os
import socket
import threading
import time


_last_progress = time.monotonic()
_lock = threading.Lock()


def mark_progress() -> None:
    global _last_progress
    with _lock:
        _last_progress = time.monotonic()


def _notify(message: str) -> bool:
    address = os.getenv("NOTIFY_SOCKET", "")
    if not address:
        return False
    if address.startswith("@"):
        address = "\0" + address[1:]
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.connect(address)
            sock.sendall(message.encode())
        return True
    except OSError:
        return False


def start_progress_watchdog(log=None) -> threading.Thread | None:
    """Notify systemd only while the application is making useful progress.

    The worker thread makes ``kill -STOP`` detectable.  The progress deadline
    also catches a native camera/ffmpeg call that hangs while Python threads
    remain runnable.
    """
    watchdog_usec = int(os.getenv("WATCHDOG_USEC", "0") or 0)
    if watchdog_usec <= 0 or not os.getenv("NOTIFY_SOCKET"):
        return None

    logger = log or logging.getLogger("wildlife_cam")
    progress_timeout = float(os.getenv("WILDLIFE_PROGRESS_TIMEOUT", "240"))
    interval = max(1.0, min(30.0, watchdog_usec / 3_000_000))
    mark_progress()

    def run() -> None:
        warned = False
        while True:
            with _lock:
                age = time.monotonic() - _last_progress
            if age <= progress_timeout:
                _notify(f"WATCHDOG=1\nSTATUS=正常動作中 (最終進捗 {age:.0f} 秒前)")
                warned = False
            elif not warned:
                logger.error(
                    "No application progress for %.0f seconds; stopping watchdog heartbeats",
                    age,
                )
                warned = True
            time.sleep(interval)

    thread = threading.Thread(target=run, name="systemd-watchdog", daemon=True)
    thread.start()
    logger.info(
        "Systemd watchdog enabled (heartbeat %.0fs, progress timeout %.0fs)",
        interval,
        progress_timeout,
    )
    return thread
