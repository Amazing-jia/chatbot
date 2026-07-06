from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(base_dir: Path) -> logging.Logger:
    """Return the app logger, writing to logs/app.log."""
    key = str(base_dir.resolve())
    if key in _LOGGERS:
        return _LOGGERS[key]

    logs_dir = base_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger(f"bot_buddy.{key}")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        handler = RotatingFileHandler(
            logs_dir / "app.log",
            maxBytes=1_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        logger.addHandler(handler)

    _LOGGERS[key] = logger
    return logger
