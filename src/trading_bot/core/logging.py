"""Structured logging helpers for pipeline observability.

The project emits JSON logs so ingestion and normalization runs can be audited
and machine-parsed in downstream tooling.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Serialize log records as single-line JSON payloads."""

    def format(self, record: logging.LogRecord) -> str:
        """Convert a `LogRecord` into a consistent JSON message.

        Args:
            record: Python logging record to format.

        Returns:
            JSON string with timestamp, level, logger name, and message.
        """
        payload = {
            # Use UTC to keep timestamps comparable across environments.
            "ts": utc_now_iso(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            # Include formatted exception details when present.
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging with the project JSON formatter.

    This function is idempotent for handler registration: if handlers already
    exist, it only updates the root level.

    Args:
        level: Logging threshold (for example, `INFO` or `DEBUG`).
    """
    root = logging.getLogger()
    if root.handlers:
        root.setLevel(level)
        return

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger for module-level usage.

    Args:
        name: Logger namespace, typically `__name__`.

    Returns:
        Configured logger instance from the standard logging registry.
    """
    return logging.getLogger(name)


def utc_now_iso() -> str:
    """Generate current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()
