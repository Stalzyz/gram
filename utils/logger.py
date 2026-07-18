"""Centralized logging setup for the pipeline and dashboard."""
import logging
import os
from logging.handlers import RotatingFileHandler

_LOGGERS = {}


def get_logger(name: str = "ig_lead_pipeline", log_dir: str = "logs") -> logging.Logger:
    """Return a configured logger, creating it once per name (idempotent)."""
    if name in _LOGGERS:
        return _LOGGERS[name]

    os.makedirs(log_dir, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if not logger.handlers:
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        )

        file_handler = RotatingFileHandler(
            os.path.join(log_dir, f"{name}.log"),
            maxBytes=5 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(fmt)
        logger.addHandler(console_handler)

    _LOGGERS[name] = logger
    return logger


def tail_log(log_dir: str, name: str = "ig_lead_pipeline", n_lines: int = 100) -> list:
    """Return the last n_lines of the log file, for dashboard display."""
    path = os.path.join(log_dir, f"{name}.log")
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()
    return [line.rstrip("\n") for line in lines[-n_lines:]]
