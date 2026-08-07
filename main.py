import os
from dotenv import load_dotenv

from app_paths import get_env_file

load_dotenv(get_env_file())

from logger import get_logger
from runtime import get_node_role, run_role
from watchdog import start_progress_watchdog


def main():
    log = get_logger("wildlife_cam")
    start_progress_watchdog(log)
    role = get_node_role()
    run_role(role, log)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log = get_logger("wildlife_cam")
        log.info("Shutting down...")
