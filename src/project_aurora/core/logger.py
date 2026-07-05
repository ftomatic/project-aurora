"""Logging helpers for Project Aurora core components."""

from __future__ import annotations

import logging

from project_aurora.core.constants import DEFAULT_LOGGER_NAME


def get_logger(name: str = DEFAULT_LOGGER_NAME) -> logging.Logger:
    """Return a configured logger for Project Aurora."""
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger
