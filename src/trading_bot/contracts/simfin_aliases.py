"""Validated universe-to-SimFin ticker aliases for raw fundamentals ingestion."""

from __future__ import annotations


SIMFIN_TICKER_ALIASES: dict[str, str] = {
    "BRK.B": "BRK-A",
    "CPAY": "FLT",
    "FISV": "FI",
    "FOXA": "FOX",
    "GOOGL": "GOOG",
    "Q": "QRVO",
    "RVTY": "PKI",
    "XYZ": "SQ",
}
