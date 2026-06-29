"""Structured logging configuration.

Logs go to a rotating file under the PDO logs directory (never to stdout, which
is reserved for the interactive session). Only the ``pdo`` logger namespace is
configured so we don't interfere with a host application's logging.
"""
from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import get_logs_dir

_LOG_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def configure_logging(level: int = logging.INFO) -> Path:
    """Configure file logging for the ``pdo`` namespace and return the log path."""
    log_path = get_logs_dir() / "pdo.log"

    handler = RotatingFileHandler(
        log_path, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(_LOG_FORMAT))

    pdo_logger = logging.getLogger("pdo")
    pdo_logger.setLevel(level)
    pdo_logger.handlers.clear()
    pdo_logger.addHandler(handler)
    # Don't propagate to the root logger; we own this namespace's output.
    pdo_logger.propagate = False

    return log_path
