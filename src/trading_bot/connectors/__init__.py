"""Connector exports for external data sources.

Connectors are thin adapters around third-party sources (Wikipedia and SEC).
They avoid business rules and only normalize transport-level payloads.
"""

from .sec import (
    SecClient,
    build_ticker_reference_lookup,
    build_ticker_to_cik_index,
    fetch_sec_ticker_reference,
    iter_companyfacts_rows,
    normalize_ticker,
)
from .sp500 import SP500Constituents

# Re-export adapter entry points for simple imports in steps/workflows.
__all__ = [
    "SP500Constituents",
    "SecClient",
    "build_ticker_reference_lookup",
    "build_ticker_to_cik_index",
    "fetch_sec_ticker_reference",
    "iter_companyfacts_rows",
    "normalize_ticker",
]
