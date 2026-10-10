"""Logging setup: call `configure_logging` once, at application startup."""

import logging

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(level: str = "INFO") -> None:
    """Configure the root logger with a single, consistent format.

    Args:
        level: Minimum level name to emit (e.g. ``"INFO"``).
    """
    logging.basicConfig(level=level, format=LOG_FORMAT, force=True)
