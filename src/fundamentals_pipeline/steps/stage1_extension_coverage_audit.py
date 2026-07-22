"""Coverage audit for the Stage 1 extension fields across published outputs."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..contracts.stage1_fundamentals_schema import EXTENDED_RAW_FIELDS

EXTENSION_COVERAGE_COLUMNS: tuple[str, ...] = (
    "year",
    "field_name",
    "total_rows",
    "non_null_rows",
    "non_null_pct",
    "cogsq_fallback_rows",
)


def _count_cogs_fallback_rows(
    simfin_cache_dir: Path,
    *,
    year: int,
    published_tickers: set[str],
) -> int | None:
    """Count general-income rows where COGS must derive from Revenue - Gross Profit."""
    income_path = simfin_cache_dir / "us-income-quarterly.csv"
    if not income_path.exists():
        return None
    income = pd.read_csv(income_path, sep=";", low_memory=False)
    fiscal_year = pd.to_numeric(income.get("Fiscal Year"), errors="coerce")
    ticker = income.get("Ticker", pd.Series(dtype=str)).astype(str).str.upper()
    cost = pd.to_numeric(income.get("Cost of Revenue"), errors="coerce")
    revenue = pd.to_numeric(income.get("Revenue"), errors="coerce")
    gross_profit = pd.to_numeric(income.get("Gross Profit"), errors="coerce")
    mask = (
        (fiscal_year == year)
        & ticker.isin(published_tickers)
        & cost.isna()
        & revenue.notna()
        & gross_profit.notna()
    )
    return int(mask.sum())


def run_stage1_extension_coverage_audit(
    *,
    processed_dir: str | Path,
    reports_dir: str | Path,
    start_year: int,
    end_year: int,
    simfin_cache_dir: str | Path | None = None,
) -> dict[str, str]:
    """Audit non-null coverage of the extension fields in published yearly CSVs."""
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    resolved_processed_dir = Path(processed_dir)
    resolved_reports_dir = Path(reports_dir)
    resolved_reports_dir.mkdir(parents=True, exist_ok=True)
    resolved_cache_dir = Path(simfin_cache_dir) if simfin_cache_dir else None

    rows: list[dict[str, object]] = []
    for year in range(start_year, end_year + 1):
        year_path = resolved_processed_dir / f"raw_fundamentals_{year}.csv"
        if not year_path.exists():
            raise FileNotFoundError(f"Published Stage 1 file not found: {year_path}")
        year_df = pd.read_csv(year_path)
        published_tickers = set(year_df["ticker"].astype(str).str.upper())

        fallback_rows: int | None = None
        if resolved_cache_dir is not None:
            fallback_rows = _count_cogs_fallback_rows(
                resolved_cache_dir,
                year=year,
                published_tickers=published_tickers,
            )

        for field in EXTENDED_RAW_FIELDS:
            non_null = int(year_df[field].notna().sum()) if field in year_df.columns else 0
            total = int(len(year_df))
            rows.append(
                {
                    "year": year,
                    "field_name": field,
                    "total_rows": total,
                    "non_null_rows": non_null,
                    "non_null_pct": round(100.0 * non_null / total, 2) if total else 0.0,
                    "cogsq_fallback_rows": fallback_rows if field == "cogsq" else pd.NA,
                }
            )

    report = pd.DataFrame(rows, columns=EXTENSION_COVERAGE_COLUMNS)
    output_path = (
        resolved_reports_dir
        / f"stage1_extension_coverage_{start_year}_{end_year}.csv"
    )
    report.to_csv(output_path, index=False)
    return {"extension_coverage_output": str(output_path)}
