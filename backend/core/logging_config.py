"""Structured logging with PII redaction hooks.

Batch 0 — B16 (minimal observability).
Every log line uses a custom formatter that strips sensitive data.
"""
import logging
import sys
from typing import Optional

from observability.redaction import redact
from config.settings import get_settings


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts PII/secrets from log messages."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        original = super().format(record)
        if settings.LOG_REDACTION_ENABLED:
            return redact(original)
        return original


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logger with redacting formatter."""
    settings = get_settings()
    log_level = level or settings.LOG_LEVEL

    formatter = RedactingFormatter(
        fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    # Remove any existing handlers
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
