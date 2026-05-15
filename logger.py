import logging
import logging.handlers
import os
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "config", ".env"))

LOG_DIR = "/home/pi/wildlife-cam/logs"


def get_logger(name: str) -> logging.Logger:
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    log_file = os.path.join(LOG_DIR, "wildlife.log")

    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(numeric_level)

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        fh = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=3
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except OSError:
        pass

    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger


logger = get_logger("wildlife_cam")