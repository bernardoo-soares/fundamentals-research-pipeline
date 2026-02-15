"""Shared infrastructure exports used across pipeline layers.

The `core` package holds low-level utilities (settings, logging, exceptions)
that are intentionally reusable by connectors, steps, and workflows.
"""

from .exceptions import (
    ConfigurationError,
    DataSourceError,
    SecRateLimitError,
    SecRequestError,
    TradingBotError,
)
from .logging import configure_logging, get_logger, utc_now_iso
from .settings import AppSettings, get_settings

# Re-export core primitives to keep import sites concise and consistent.
__all__ = [
    "AppSettings",
    "ConfigurationError",
    "DataSourceError",
    "SecRateLimitError",
    "SecRequestError",
    "TradingBotError",
    "configure_logging",
    "get_logger",
    "get_settings",
    "utc_now_iso",
]
