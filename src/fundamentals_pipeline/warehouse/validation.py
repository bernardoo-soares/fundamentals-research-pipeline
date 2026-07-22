"""Warning-level data-health checks producing a report CSV (never blocks)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

HEALTH_COLUMNS: tuple[str, ...] = (
    "check",
    "ticker",
    "year",
    "quarter",
    "value",
    "note",
)

_MAX_PLAUSIBLE_SALEQ_MILLIONS = 5_000_000.0  # ~$5T quarterly revenue ceiling


def build_health_report(
    conn: duckdb.DuckDBPyConnection,
    *,
    reports_dir: str | Path,
    start_year: int,
    end_year: int,
) -> str:
    """Compute warning checks and write warehouse_health_<start>_<end>.csv."""
    rows: list[dict[str, object]] = []

    recon = conn.execute(
        "SELECT ticker, year, quarter, "
        "abs(atq - (ltq + ceqq)) / atq AS residual "
        "FROM fundamentals_quarterly "
        "WHERE atq IS NOT NULL AND ltq IS NOT NULL AND ceqq IS NOT NULL "
        "AND atq <> 0"
    ).df()
    for record in recon[recon["residual"] > 0.05].itertuples():
        rows.append(
            {
                "check": "balance_reconciliation",
                "ticker": record.ticker,
                "year": int(record.year),
                "quarter": int(record.quarter),
                "value": round(float(record.residual), 4),
                "note": "|atq - (ltq + ceqq)| / atq > 5%",
            }
        )

    magnitude = conn.execute(
        "SELECT ticker, year, quarter, saleq FROM fundamentals_quarterly "
        "WHERE saleq > ?",
        [_MAX_PLAUSIBLE_SALEQ_MILLIONS],
    ).df()
    for record in magnitude.itertuples():
        rows.append(
            {
                "check": "unit_magnitude_saleq",
                "ticker": record.ticker,
                "year": int(record.year),
                "quarter": int(record.quarter),
                "value": float(record.saleq),
                "note": "quarterly saleq exceeds plausible millions ceiling",
            }
        )

    completeness = conn.execute(
        "SELECT fiscal_year, "
        "SUM(CASE WHEN quarters_present = 4 THEN 1 ELSE 0 END) AS complete, "
        "COUNT(*) AS total "
        "FROM fundamentals_annual GROUP BY fiscal_year ORDER BY fiscal_year"
    ).df()
    for record in completeness.itertuples():
        rows.append(
            {
                "check": "completeness",
                "ticker": None,
                "year": int(record.fiscal_year),
                "quarter": None,
                "value": int(record.complete),
                "note": f"{int(record.complete)}/{int(record.total)} ticker-years complete",
            }
        )

    report = pd.DataFrame(rows, columns=list(HEALTH_COLUMNS))
    directory = Path(reports_dir)
    directory.mkdir(parents=True, exist_ok=True)
    output_path = directory / f"warehouse_health_{start_year}_{end_year}.csv"
    report.to_csv(output_path, index=False)
    return str(output_path)
