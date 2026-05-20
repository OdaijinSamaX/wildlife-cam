import os
from pathlib import Path


def get_app_home() -> str:
    configured = os.getenv("WILDLIFE_CAM_HOME", "").strip()
    if configured:
        return configured
    return str(Path.home() / "wildlife-cam")


def get_env_file() -> str:
    configured = os.getenv("WILDLIFE_CAM_ENV_FILE", "").strip()
    if configured:
        return configured
    return os.path.join(get_app_home(), "config", ".env")


def get_videos_dir() -> str:
    return os.path.join(get_app_home(), "videos")


def get_logs_dir() -> str:
    return os.path.join(get_app_home(), "logs")


def get_upload_queue_dir() -> str:
    return os.path.join(get_app_home(), "upload_queue")
