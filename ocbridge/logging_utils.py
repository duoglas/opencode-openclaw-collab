from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


def default_log_path() -> str:
    return os.getenv(
        "OCBRIDGE_LOG_PATH",
        os.path.expanduser("~/.local/share/ocbridge/logs/ocbridge.log"),
    )


def setup_rotating_logger(name: str = "ocbridge") -> tuple[logging.Logger, str]:
    log_path = default_log_path()
    Path(log_path).parent.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    # avoid duplicate handlers on repeated setup
    for h in list(logger.handlers):
        logger.removeHandler(h)

    handler = RotatingFileHandler(
        log_path,
        maxBytes=int(os.getenv("OCBRIDGE_LOG_MAX_BYTES", str(2 * 1024 * 1024))),
        backupCount=int(os.getenv("OCBRIDGE_LOG_BACKUP_COUNT", "5")),
        encoding="utf-8",
    )
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(fmt)
    logger.addHandler(handler)

    return logger, log_path
