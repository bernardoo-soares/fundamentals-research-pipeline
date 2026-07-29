"""Contract for company identity: name and GICS classification.

Compute-free. Declares what the `companies` table holds and, more importantly,
what it does NOT claim.

WHY THIS EXISTS
---------------
Until 2026-07-29 the warehouse held no company name and no sector, so the
console showed bare tickers and the platform spec's sector filter was
unbuildable. That was recorded as "no source provides it", which was wrong:
`connectors/wikipedia_sp500_client.py` already downloaded the full S&P 500
constituents table and discarded every column but the symbol, one line after
parsing it. The source was there; the pipeline threw it away.

TWO CLAIMS THIS TABLE DOES NOT MAKE
-----------------------------------
1. **It is not point-in-time.** The Wikipedia table lists *current* membership
   and *current* GICS classification. A sector shown against FY2015 is today's
   label, not the label the company carried then, and GICS reclassifies:
   the 2023 reshuffle moved payment processors out of Information Technology
   into Financials, and the 2018 one created Communication Services out of
   parts of Technology and Consumer Discretionary. So `sector` is display and
   filtering context. Nothing derived may key off it, and no historical
   sector claim may be made from it.
2. **It is not complete, and completeness is not achievable here.** Measured
   2026-07-29: 376 of 384 FY2024 scored tickers match (97.9%), 484 of 494
   across all scored years (98.0%). The misses -- CAG, CPB, EPAM, LW, MOH,
   MTCH, PAYC, POOL, and BK and HOLX in earlier years -- are companies that
   have LEFT the index. A current-membership list cannot name a former member,
   and guessing a name from a ticker is fabrication. Those rows carry a null
   name and are shown by ticker alone.
"""

from __future__ import annotations

COMPANY_PROFILE_PIPELINE_VERSION = "companies-1.0"

# The provider tag stamped on every row, so a future second source (a paid
# reference file, SEC company_tickers.json) is distinguishable rather than
# silently blended.
COMPANY_SOURCE_WIKIPEDIA = "wikipedia_sp500_constituents"

# Wikipedia column -> canonical column. Declared rather than positional: the
# table's column order has changed before and would silently shift the data.
WIKIPEDIA_COLUMN_MAP: dict[str, str] = {
    "Symbol": "ticker",
    "Security": "company_name",
    "GICS Sector": "sector",
    "GICS Sub-Industry": "sub_industry",
    "Headquarters Location": "headquarters",
    "Date added": "index_added_date",
    "CIK": "cik",
}

COMPANIES_COLUMNS: tuple[str, ...] = (
    "ticker",
    "company_name",
    "sector",
    "sub_industry",
    "headquarters",
    "index_added_date",
    "cik",
    "source",
    "as_of_date",
    "computed_at",
    "pipeline_version",
)

# The 11 GICS sectors. Declared so an unexpected value -- a Wikipedia edit, a
# parse that grabbed the wrong table -- is caught rather than published as a
# new sector nobody filters on.
GICS_SECTORS: frozenset[str] = frozenset(
    {
        "Communication Services",
        "Consumer Discretionary",
        "Consumer Staples",
        "Energy",
        "Financials",
        "Health Care",
        "Industrials",
        "Information Technology",
        "Materials",
        "Real Estate",
        "Utilities",
    }
)


def create_companies_ddl() -> str:
    """DDL for the `companies` table.

    `ticker` is the primary key and the join key to every other table. There is
    deliberately no fiscal-year dimension: see the module docstring -- this is
    current classification, and giving it a year column would invite a
    point-in-time reading it cannot support.
    """
    return (
        "CREATE TABLE companies (\n"
        "  ticker VARCHAR NOT NULL,\n"
        "  company_name VARCHAR,\n"
        "  sector VARCHAR,\n"
        "  sub_industry VARCHAR,\n"
        "  headquarters VARCHAR,\n"
        "  index_added_date DATE,\n"
        "  cik VARCHAR,\n"
        "  source VARCHAR,\n"
        "  as_of_date DATE,\n"
        "  computed_at TIMESTAMP,\n"
        "  pipeline_version VARCHAR,\n"
        "  PRIMARY KEY (ticker)\n"
        ")"
    )


def validate_sectors(sectors: set[str]) -> None:
    """Raise if any sector is outside the declared GICS set."""
    unknown = sorted(sectors - GICS_SECTORS)
    if unknown:
        raise ValueError(
            f"Unrecognised GICS sector(s): {unknown}. Either GICS changed and "
            "the contract needs updating, or the wrong table was parsed."
        )
