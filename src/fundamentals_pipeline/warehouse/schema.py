"""DDL for the warehouse tables. Column order is contract-driven."""

from __future__ import annotations

import duckdb

from ..contracts.fundamentals_annual_schema import ANNUAL_VALUE_COLUMNS
from ..contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    SUPPORT_RAW_FIELDS,
)

WAREHOUSE_PIPELINE_VERSION = "warehouse-1.0"

QUARTERLY_RAW_FIELDS: tuple[str, ...] = (
    *CORE_RAW_FIELDS,
    *SUPPORT_RAW_FIELDS,
    *EXTENDED_RAW_FIELDS,
)


def _fundamentals_quarterly_ddl() -> str:
    field_cols = ",\n  ".join(f"{field} DOUBLE" for field in QUARTERLY_RAW_FIELDS)
    return (
        "CREATE TABLE fundamentals_quarterly (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  year INTEGER NOT NULL,\n"
        "  quarter INTEGER NOT NULL,\n"
        f"  {field_cols},\n"
        "  source_era VARCHAR,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, year, quarter)\n"
        ")"
    )


def _fundamentals_annual_ddl() -> str:
    value_cols = ",\n  ".join(f"{col} DOUBLE" for col in ANNUAL_VALUE_COLUMNS)
    return (
        "CREATE TABLE fundamentals_annual (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  fiscal_year INTEGER NOT NULL,\n"
        f"  {value_cols},\n"
        "  quarters_present INTEGER,\n"
        "  has_q4 BOOLEAN,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker, fiscal_year)\n"
        ")"
    )


def _build_log_ddl() -> str:
    return (
        "CREATE TABLE build_log (\n"
        "  run_id VARCHAR,\n"
        "  started_at TIMESTAMP,\n"
        "  finished_at TIMESTAMP,\n"
        "  start_year INTEGER,\n"
        "  end_year INTEGER,\n"
        "  quarterly_rows INTEGER,\n"
        "  annual_rows INTEGER,\n"
        "  gate_status VARCHAR,\n"
        "  health_report_path VARCHAR,\n"
        "  pipeline_version VARCHAR\n"
        ")"
    )


def create_all_tables(conn: duckdb.DuckDBPyConnection) -> None:
    """Create the three warehouse tables on an open connection."""
    conn.execute(_fundamentals_quarterly_ddl())
    conn.execute(_fundamentals_annual_ddl())
    conn.execute(_build_log_ddl())
