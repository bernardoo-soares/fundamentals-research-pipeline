"""Build the `companies` table: name and GICS classification per ticker.

Callable core (AGENTS.md S2.5): a plain function returning a structured result,
which the CLI dispatches to. Network access is confined to the connector passed
in, so the builder itself is testable with a fake.

What this table may and may not be used for is declared in
`contracts/company_profile_schema.py`. In short: display and filtering only.
It is current classification, not point-in-time, and it cannot name a company
that has left the index.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd

from ..connectors.wikipedia_sp500_client import SP500Constituents
from ..contracts.company_profile_schema import (
    COMPANIES_COLUMNS,
    COMPANY_PROFILE_PIPELINE_VERSION,
    COMPANY_SOURCE_WIKIPEDIA,
    create_companies_ddl,
    validate_sectors,
)
from ..core.logging import get_logger

LOG = get_logger(__name__)

COMPANIES_TABLE = "companies"

# NO SYMBOL REWRITING.
#
# A first draft normalised "." to "-" in class-share tickers, on the assumption
# that Wikipedia and the warehouse spelled them differently. Measured: both
# write BRK.B and BF.B, so the rewrite invented a mismatch and then caused it,
# leaving Berkshire and Brown-Forman unnamed -- the exact failure it was meant
# to prevent. Symbols are joined exactly as both sides publish them; whitespace
# and case are the only things touched.
def _canonical_ticker(ticker: str) -> str:
    """Return the ticker as the warehouse keys it."""
    return ticker.strip().upper()


def build_companies(
    *,
    warehouse_path: str | Path,
    connector: SP500Constituents | None = None,
    as_of: date | None = None,
    pipeline_version: str = COMPANY_PROFILE_PIPELINE_VERSION,
) -> dict[str, object]:
    """Fetch the constituents table and (re)build `companies`.

    Returns a summary including how many warehouse tickers the table covers,
    and the tickers it does not -- because that gap is the honest answer to
    "why does this row show no name", not something to paper over.
    """
    path = Path(warehouse_path)
    if not path.exists():
        raise FileNotFoundError(f"Warehouse database not found: {path}")

    source = connector or SP500Constituents()
    frame = source.get_sp500_profile()
    if frame.empty:
        raise RuntimeError("Constituents table is empty; refusing to publish.")

    validate_sectors(set(frame["sector"].dropna()))

    frame = frame.assign(
        ticker=frame["ticker"].map(_canonical_ticker),
        index_added_date=pd.to_datetime(
            frame["index_added_date"], errors="coerce"
        ).dt.date,
        cik=frame["cik"].astype("string"),
        source=COMPANY_SOURCE_WIKIPEDIA,
        as_of_date=as_of or datetime.now(UTC).date(),
        computed_at=datetime.now(UTC).replace(tzinfo=None),
        pipeline_version=pipeline_version,
    )

    duplicates = sorted(frame.loc[frame["ticker"].duplicated(), "ticker"])
    if duplicates:
        raise RuntimeError(
            f"Duplicate tickers in the constituents table: {duplicates}. "
            "One row would silently overwrite the other."
        )

    frame = frame[list(COMPANIES_COLUMNS)].sort_values("ticker")

    from .connection import open_warehouse

    with open_warehouse(path, read_only=False) as conn:
        conn.execute(f"DROP TABLE IF EXISTS {COMPANIES_TABLE}")
        conn.execute(create_companies_ddl())
        conn.register("companies_frame", frame)
        conn.execute(
            f"INSERT INTO {COMPANIES_TABLE} SELECT * FROM companies_frame"
        )
        conn.unregister("companies_frame")

        known = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT ticker FROM scores"
            ).fetchall()
        }

    named = set(frame["ticker"])
    unnamed = sorted(known - named)
    if unnamed:
        # Expected, not a defect: these have left the index, and a
        # current-membership list cannot name a former member. Logged so the
        # count is visible rather than discovered on screen.
        LOG.info(
            "%d scored ticker(s) have no current-membership row and will show "
            "as ticker only: %s",
            len(unnamed),
            ", ".join(unnamed),
        )

    return {
        "companies_rows": len(frame),
        "sectors": frame["sector"].nunique(),
        "scored_tickers": len(known),
        "scored_tickers_named": len(known & named),
        "scored_tickers_unnamed": len(unnamed),
        "unnamed_tickers": unnamed,
    }
