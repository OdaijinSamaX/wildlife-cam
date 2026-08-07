"""Bounded local video queue and retry/quarantine helpers."""

import os
import shutil
import time
from pathlib import Path


GIB = 1024**3


def _env_int(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


def quarantine_dir(videos_dir: str) -> Path:
    configured = os.getenv("WILDLIFE_QUARANTINE_DIR", "").strip()
    return Path(configured) if configured else Path(videos_dir) / "quarantine"


def _clips(videos_dir: str) -> list[Path]:
    root = Path(videos_dir)
    quarantine = quarantine_dir(videos_dir)
    paths = list(root.glob("*.mp4")) if root.is_dir() else []
    paths += list(quarantine.glob("*.mp4")) if quarantine.is_dir() else []
    return [path for path in paths if path.is_file()]


def _remove_clip(log, path: Path, reason: str) -> None:
    try:
        size = path.stat().st_size
        path.unlink()
        retry_marker(path).unlink(missing_ok=True)
        log.warning("Retention deleted %s (%d bytes): %s", path, size, reason)
    except OSError as exc:
        log.warning("Retention could not delete %s: %s", path, exc)


def enforce_limits(log, videos_dir: str) -> bool:
    """Delete oldest clips until age/count/bytes/free-space limits are met."""
    root = Path(videos_dir)
    root.mkdir(parents=True, exist_ok=True)
    quarantine_dir(videos_dir).mkdir(parents=True, exist_ok=True)
    max_bytes = _env_int("WILDLIFE_VIDEO_MAX_BYTES", 20 * GIB)
    max_files = _env_int("WILDLIFE_VIDEO_MAX_FILES", 2000)
    max_age_days = _env_int("WILDLIFE_VIDEO_MAX_AGE_DAYS", 14)
    min_free = _env_int("WILDLIFE_MIN_FREE_BYTES", 2 * GIB)
    now = time.time()

    clips = sorted(_clips(videos_dir), key=lambda path: path.stat().st_mtime)
    if max_age_days:
        cutoff = now - max_age_days * 86400
        for path in list(clips):
            try:
                expired = path.stat().st_mtime < cutoff
            except OSError:
                clips.remove(path)
                continue
            if expired:
                _remove_clip(log, path, f"older than {max_age_days} days")
                clips.remove(path)

    while clips:
        try:
            total = sum(path.stat().st_size for path in clips)
            free = shutil.disk_usage(root).free
        except OSError as exc:
            log.error("Could not inspect video storage: %s", exc)
            return False
        over_count = bool(max_files and len(clips) > max_files)
        over_bytes = bool(max_bytes and total > max_bytes)
        low_free = free < min_free
        if not (over_count or over_bytes or low_free):
            break
        reasons = []
        if over_count:
            reasons.append(f"more than {max_files} files")
        if over_bytes:
            reasons.append(f"more than {max_bytes} bytes")
        if low_free:
            reasons.append(f"free space below {min_free} bytes")
        oldest = clips.pop(0)
        _remove_clip(log, oldest, ", ".join(reasons))

    free = shutil.disk_usage(root).free
    if free < min_free:
        log.error(
            "Recording paused: only %d bytes free (minimum %d) and no old clips remain",
            free,
            min_free,
        )
        return False
    return True


def looks_like_mp4(path: str) -> bool:
    """Cheap corruption guard: normal MP4 files contain an ftyp box near the start."""
    try:
        with open(path, "rb") as handle:
            return b"ftyp" in handle.read(64)
    except OSError:
        return False


def retry_marker(path: str | Path) -> Path:
    return Path(f"{path}.retry")


def retry_count(path: str) -> int:
    try:
        return max(0, int(retry_marker(path).read_text(encoding="ascii").strip()))
    except (OSError, ValueError):
        return 0


def record_retry(path: str) -> int:
    marker = retry_marker(path)
    count = retry_count(path) + 1
    temp = marker.with_suffix(marker.suffix + ".tmp")
    temp.write_text(f"{count}\n", encoding="ascii")
    os.replace(temp, marker)
    return count


def clear_retry(path: str) -> None:
    retry_marker(path).unlink(missing_ok=True)


def quarantine(log, path: str, reason: str) -> str:
    source = Path(path)
    target_dir = quarantine_dir(str(source.parent))
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / source.name
    serial = 1
    while target.exists():
        target = target_dir / f"{source.stem}_{serial:02d}{source.suffix}"
        serial += 1
    shutil.move(str(source), str(target))
    clear_retry(path)
    log.error("Quarantined video %s -> %s: %s", source, target, reason)
    return str(target)
