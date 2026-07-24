"""Derive fundamentals_annual from fundamentals_quarterly (spec section 6.1)."""

from __future__ import annotations

import duckdb

from ..contracts.fundamentals_annual_schema import (
    ANNUAL_VALUE_COLUMNS,
    FLOW_FIELDS,
    STOCK_FIELDS,
    YTD_ANNUAL_FIELDS,
)


def _value_select_sql() -> str:
    parts: list[str] = []
    for field in FLOW_FIELDS:
        parts.append(
            f"CASE WHEN COUNT(*) = 4 AND COUNT({field}) = 4 "
            f"THEN SUM({field}) END AS {field}_annual"
        )
    for field in YTD_ANNUAL_FIELDS:
        parts.append(f"MAX(CASE WHEN quarter = 4 THEN {field} END) AS {field}_annual")
    for field in STOCK_FIELDS:
        parts.append(f"MAX(CASE WHEN quarter = 4 THEN {field} END) AS {field}_q4")
    return ",\n  ".join(parts)


def build_fundamentals_annual(
    conn: duckdb.DuckDBPyConnection,
    *,
    pipeline_version: str,
) -> int:
    """Aggregate quarterly rows into the annual table; returns row count."""
    value_columns = ", ".join(ANNUAL_VALUE_COLUMNS)
    sql = (
        "INSERT INTO fundamentals_annual "
        f"(ticker, fiscal_year, {value_columns}, "
        "quarters_present, has_q4, source_era, computed_at, pipeline_version)\n"
        "SELECT\n"
        "  ticker,\n"
        "  year AS fiscal_year,\n"
        f"  {_value_select_sql()},\n"
        "  COUNT(*) AS quarters_present,\n"
        "  BOOL_OR(quarter = 4) AS has_q4,\n"
        # Era resolution is whole-ticker-year, so this collapses to one value.
        # A mixed year yields null rather than an arbitrary pick, so the
        # metrics layer can refuse to compute on it. COUNT(DISTINCT) ignores
        # NULLs, so the second condition is required: a year with some
        # unprovenanced quarters must not be stamped as pure.
        "  CASE WHEN COUNT(DISTINCT source_era) = 1\n"
        "         AND COUNT(source_era) = COUNT(*)\n"
        "       THEN MAX(source_era) END AS source_era,\n"
        "  CAST(now() AS TIMESTAMP) AS computed_at,\n"
        "  ? AS pipeline_version\n"
        "FROM fundamentals_quarterly\n"
        "GROUP BY ticker, year"
    )
    conn.execute(sql, [pipeline_version])
    return int(
        conn.execute("SELECT COUNT(*) FROM fundamentals_annual").fetchone()[0]
    )
