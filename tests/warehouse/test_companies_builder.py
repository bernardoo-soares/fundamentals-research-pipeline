"""Tests for the `companies` table build.

The connector is faked, so these are deterministic and make no network call
(tests/AGENTS.override.md rule 2).
"""

from __future__ import annotations

import duckdb
import pandas as pd
import pytest

from fundamentals_pipeline.contracts.company_profile_schema import (
    GICS_SECTORS,
    validate_sectors,
)
from fundamentals_pipeline.warehouse.companies_builder import build_companies

ROWS = [
    ("MMM", "3M", "Industrials", "Industrial Conglomerates", "Saint Paul", "1957-03-04", "66740"),
    ("BRK.B", "Berkshire Hathaway", "Financials", "Multi-Sector Holdings", "Omaha", "2010-02-16", "1067983"),
    ("KO", "Coca-Cola", "Consumer Staples", "Soft Drinks", "Atlanta", "1957-03-04", "21344"),
]
COLUMNS = [
    "ticker", "company_name", "sector", "sub_industry", "headquarters",
    "index_added_date", "cik",
]


class FakeConnector:
    def __init__(self, rows=None):
        self._rows = ROWS if rows is None else rows

    def get_sp500_profile(self) -> pd.DataFrame:
        return pd.DataFrame(self._rows, columns=COLUMNS)


@pytest.fixture()
def warehouse(tmp_path):
    path = tmp_path / "w.duckdb"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE scores (ticker VARCHAR, as_of_year INTEGER)")
    # GONE has left the index, so the constituents table cannot name it.
    conn.execute(
        "INSERT INTO scores VALUES ('MMM', 2024), ('BRK.B', 2024), "
        "('KO', 2024), ('GONE', 2024)"
    )
    conn.close()
    return path


def _companies(path) -> pd.DataFrame:
    conn = duckdb.connect(str(path), read_only=True)
    try:
        return conn.execute("SELECT * FROM companies ORDER BY ticker").fetchdf()
    finally:
        conn.close()


def test_build_writes_every_row(warehouse):
    result = build_companies(warehouse_path=warehouse, connector=FakeConnector())
    assert result["companies_rows"] == 3
    assert set(_companies(warehouse)["ticker"]) == {"MMM", "BRK.B", "KO"}


def test_class_share_tickers_are_not_rewritten(warehouse):
    """A first draft rewrote "." to "-", inventing a mismatch and then causing
    it: Berkshire and Brown-Forman came out unnamed. Both sides write BRK.B."""
    build_companies(warehouse_path=warehouse, connector=FakeConnector())
    assert "BRK.B" in set(_companies(warehouse)["ticker"])
    assert "BRK-B" not in set(_companies(warehouse)["ticker"])


def test_a_departed_company_is_reported_not_invented(warehouse):
    """A current-membership list cannot name a former member."""
    result = build_companies(warehouse_path=warehouse, connector=FakeConnector())
    assert result["scored_tickers_unnamed"] == 1
    assert result["unnamed_tickers"] == ["GONE"]
    assert result["scored_tickers_named"] == 3


def test_an_unknown_sector_is_rejected(warehouse):
    """A Wikipedia edit or a wrong-table parse must not publish a new sector."""
    bad = [("XYZ", "Test", "Crypto Mining", "sub", "hq", "2020-01-01", "1")]
    with pytest.raises(ValueError, match="Unrecognised GICS sector"):
        build_companies(
            warehouse_path=warehouse, connector=FakeConnector(bad)
        )


def test_duplicate_tickers_are_rejected(warehouse):
    dupe = [*ROWS, ROWS[0]]
    with pytest.raises(RuntimeError, match="Duplicate tickers"):
        build_companies(warehouse_path=warehouse, connector=FakeConnector(dupe))


def test_an_empty_table_is_refused(warehouse):
    """Publishing an empty table would silently blank every name."""
    with pytest.raises(RuntimeError, match="empty"):
        build_companies(warehouse_path=warehouse, connector=FakeConnector([]))


def test_rebuild_is_idempotent(warehouse):
    first = build_companies(warehouse_path=warehouse, connector=FakeConnector())
    second = build_companies(warehouse_path=warehouse, connector=FakeConnector())
    assert first["companies_rows"] == second["companies_rows"]
    assert len(_companies(warehouse)) == 3


def test_missing_warehouse_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_companies(
            warehouse_path=tmp_path / "nope.duckdb", connector=FakeConnector()
        )


def test_the_declared_sector_set_is_the_eleven_gics_sectors():
    assert len(GICS_SECTORS) == 11
    validate_sectors({"Financials", "Utilities"})
    with pytest.raises(ValueError):
        validate_sectors({"Financials", "Not A Sector"})
