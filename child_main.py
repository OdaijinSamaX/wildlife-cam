from dotenv import load_dotenv

from app_paths import get_env_file

load_dotenv(get_env_file())

from logger import get_logger
from runtime import run_child


def main():
    log = get_logger("wildlife_cam")
    run_child(log)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        log = get_logger("wildlife_cam")
        log.info("Shutting down child node...")
