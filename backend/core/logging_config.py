"""Structured logging with PII redaction hooks.

Supports two modes:
  - ENV=prod → JSON structured logging (machine-parseable, supports tracing)
  - ENV!=prod → Human-readable plaintext (developer friendly)

Every log line includes session_id when available for request correlation.
"""
import json
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


class JSONFormatter(logging.Formatter):
    """JSON structured formatter for production — machine-parseable."""

    def format(self, record: logging.LogRecord) -> str:
        settings = get_settings()
        log_entry = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Add session_id if present in the log message (convention: session=xxx)
        msg = record.getMessage()
        if "session=" in msg:
            import re
            m = re.search(r'session=(\S+)', msg)
            if m:
                log_entry["session_id"] = m.group(1)

        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = self.formatException(record.exc_info)

        raw = json.dumps(log_entry, default=str)
        if settings.LOG_REDACTION_ENABLED:
            return redact(raw)
        return raw


def setup_logging(level: Optional[str] = None) -> None:
    """Configure root logger — JSON in prod, plaintext in dev."""
    settings = get_settings()
    log_level = level or settings.LOG_LEVEL

    if settings.ENV == "prod":
        formatter = JSONFormatter()
    else:
        formatter = RedactingFormatter(
            fmt="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    root.handlers.clear()
    root.addHandler(handler)

    # Silence noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("motor").setLevel(logging.WARNING)
