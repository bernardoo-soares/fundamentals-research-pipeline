"""Legacy fundamentals canonicalization step.

This step filters local legacy per-ticker CSV files to the current universe and
normalizes them into a canonical quarterly schema used by downstream workflows.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ..core.settings import get_settings

# Canonical raw fields that must exist in the emitted legacy quarterly table.
CANONICAL_RAW_FIELDS = [
    "saleq",
    "niq",
    "oiadpq",
    "xintq",
    "txtq",
    "epspxq",
    "actq",
    "lctq",
    "ppentq",
    "gdwlq",
    "ivltq",
    "atq",
    "ceqq",
    "dlcq",
    "dlttq",
    "req",
    "tstkq",
    "oancfq",
    "prstkcq",
    "capxq",
    "cheq",
    "dvpq",
    "cshfdq",
]


def _normalize_ticker(value: object) -> str | None:
    """Normalize ticker values to uppercase or return `None` when empty."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return text


def _coerce_date(value: date | str | None) -> date | None:
    """Coerce optional date-like input into `date` objects."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def _load_universe_tickers(universe_path: str | Path) -> set[str]:
    """Load and normalize ticker set from the universe artifact.

    Raises:
        ValueError: If the universe file does not include `ticker` column.
    """
    df = pd.read_csv(universe_path, dtype=str)
    if "ticker" not in df.columns:
        raise ValueError(f"Universe file '{universe_path}' is missing 'ticker' column.")
    return {
        ticker
        for ticker in (_normalize_ticker(value) for value in df["ticker"].tolist())
        if ticker is not None
    }


def _legacy_input_columns() -> set[str]:
    """Return the subset of legacy columns required for canonicalization."""
    return {
        "tic",
        "datadate",
        "fyearq",
        "fqtr",
        "tstkcq",
        "tstkq",
        "cshopq",
        "cshoq",
        "prstkcy",
        *CANONICAL_RAW_FIELDS,
    }


def _coerce_numeric_columns(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Coerce selected DataFrame columns to numeric in-place."""
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _load_legacy_file(path: Path, ticker_fallback: str) -> pd.DataFrame:
    """Load and normalize one legacy ticker CSV file.

    Args:
        path: Input legacy CSV path.
        ticker_fallback: Ticker inferred from filename when source value is missing.

    Returns:
        Canonicalized per-file DataFrame keyed by `ticker,fyearq,fqtr`.
    """
    df = pd.read_csv(path, usecols=lambda column: column in _legacy_input_columns())
    if df.empty:
        return pd.DataFrame()

    # Prefer explicit `tic` values from source rows, fallback to filename ticker.
    if "tic" in df.columns:
        df["ticker"] = df["tic"].map(_normalize_ticker).fillna(ticker_fallback)
    else:
        df["ticker"] = ticker_fallback

    # Backfill known legacy column name variants.
    if "tstkq" not in df.columns and "tstkcq" in df.columns:
        df["tstkq"] = df["tstkcq"]

    if "prstkcq" not in df.columns:
        if "cshopq" in df.columns:
            df["prstkcq"] = df["cshopq"]
        elif "prstkcy" in df.columns:
            # Annual buybacks are approximated as quarterly average when needed.
            df["prstkcq"] = pd.to_numeric(df["prstkcy"], errors="coerce") / 4.0
        else:
            df["prstkcq"] = pd.NA

    if "cshoq" in df.columns:
        cshoq_numeric = pd.to_numeric(df["cshoq"], errors="coerce")
        if "cshfdq" in df.columns:
            df["cshfdq"] = pd.to_numeric(df["cshfdq"], errors="coerce").fillna(
                cshoq_numeric
            )
        else:
            df["cshfdq"] = cshoq_numeric

    if "datadate" in df.columns:
        df["period_end"] = pd.to_datetime(df["datadate"], errors="coerce")
    else:
        df["period_end"] = pd.NaT

    df = _coerce_numeric_columns(df, ["fyearq", "fqtr", *CANONICAL_RAW_FIELDS])

    if "fyearq" not in df.columns:
        df["fyearq"] = pd.NA
    if "fqtr" not in df.columns:
        df["fqtr"] = pd.NA

    # Derive missing fiscal year/quarter from period end date when possible.
    has_period_end = df["period_end"].notna()
    df.loc[has_period_end & df["fyearq"].isna(), "fyearq"] = df.loc[
        has_period_end & df["fyearq"].isna(), "period_end"
    ].dt.year
    df.loc[has_period_end & df["fqtr"].isna(), "fqtr"] = df.loc[
        has_period_end & df["fqtr"].isna(), "period_end"
    ].dt.quarter

    df = df.dropna(subset=["ticker", "fyearq", "fqtr"])
    if df.empty:
        return pd.DataFrame()

    df["fyearq"] = df["fyearq"].astype("int64")
    df["fqtr"] = df["fqtr"].astype("int64")
    df["source_system"] = "legacy_processed_fundamentals"
    df["source_tag_map_version"] = "legacy-v1"
    df["filed_date"] = pd.NaT
    df["form_type"] = pd.NA

    for field in CANONICAL_RAW_FIELDS:
        if field not in df.columns:
            df[field] = pd.NA

    keep_columns = [
        "ticker",
        "fyearq",
        "fqtr",
        "period_end",
        "filed_date",
        "form_type",
        "source_system",
        "source_tag_map_version",
        *CANONICAL_RAW_FIELDS,
    ]
    df = df[keep_columns]

    # Keep latest row per deterministic quarterly key within this file.
    df = df.sort_values(["period_end", "fyearq", "fqtr"])
    df = df.drop_duplicates(subset=["ticker", "fyearq", "fqtr"], keep="last")
    return df


def _apply_date_filter(
    df: pd.DataFrame,
    start_date: date | None,
    end_date: date | None,
) -> pd.DataFrame:
    """Filter rows by period bounds using period_end with fiscal fallback."""
    if start_date is None and end_date is None:
        return df

    filtered = df.copy()
    if "period_end" not in filtered.columns and not {"fyearq", "fqtr"}.issubset(
        filtered.columns
    ):
        return filtered

    if "period_end" in filtered.columns:
        period_dates = pd.to_datetime(filtered["period_end"], errors="coerce")
    else:
        period_dates = pd.Series(pd.NaT, index=filtered.index)

    # Fall back to fiscal year/quarter when period_end is missing.
    if {"fyearq", "fqtr"}.issubset(filtered.columns):
        fq_year = pd.to_numeric(filtered["fyearq"], errors="coerce")
        fq_quarter = pd.to_numeric(filtered["fqtr"], errors="coerce")
        valid_fiscal = fq_year.notna() & fq_quarter.notna()
        if valid_fiscal.any():
            fallback_period = pd.PeriodIndex.from_fields(
                year=fq_year[valid_fiscal].astype("int64"),
                quarter=fq_quarter[valid_fiscal].astype("int64"),
                freq="Q",
            ).to_timestamp(how="end")
            fallback_series = pd.Series(
                fallback_period,
                index=filtered.index[valid_fiscal],
            )
            period_dates.loc[valid_fiscal] = period_dates.loc[valid_fiscal].fillna(
                fallback_series
            )

    if start_date is not None:
        filtered = filtered[period_dates.notna() & (period_dates.dt.date >= start_date)]
        period_dates = period_dates.loc[filtered.index]
    if end_date is not None:
        filtered = filtered[period_dates.notna() & (period_dates.dt.date <= end_date)]

    return filtered


def _write_year_partitions(df: pd.DataFrame, output_dir: Path) -> None:
    """Write year-partitioned fundamentals CSV artifacts."""
    for year, frame in df.groupby("fyearq"):
        year = int(year)
        fundamentals_path = output_dir / f"fundamentals_q_{year}.csv"
        frame.to_csv(fundamentals_path, index=False)


def build_legacy_fundamentals(
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    canonical_filename: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> pd.DataFrame:
    """Build canonical quarterly legacy fundamentals for current universe.

    Args:
        universe_path: Universe CSV containing active tickers.
        raw_dir: Directory with legacy ticker CSV files.
        output_dir: Destination directory for canonical outputs.
        canonical_filename: Name for combined canonical quarterly CSV.
        start_date: Optional lower date filter.
        end_date: Optional upper date filter.

    Returns:
        Canonical quarterly DataFrame for all matched universe tickers.

    Raises:
        FileNotFoundError: If legacy input directory does not exist.
        RuntimeError: If no universe-matching rows are found.
    """
    settings = get_settings()
    tickers = _load_universe_tickers(universe_path)

    resolved_raw_dir = Path(raw_dir) if raw_dir else settings.legacy_fundamentals_dir
    resolved_output_dir = Path(output_dir) if output_dir else settings.processed_data_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    canonical_filename = canonical_filename or settings.canonical_legacy_filename

    if not resolved_raw_dir.exists():
        raise FileNotFoundError(f"Legacy fundamentals directory not found: {resolved_raw_dir}")

    start_date = _coerce_date(start_date)
    end_date = _coerce_date(end_date)

    frames: list[pd.DataFrame] = []
    for path in sorted(resolved_raw_dir.glob("*.csv")):
        ticker = _normalize_ticker(path.stem.split("-")[0])
        if ticker is None or ticker not in tickers:
            continue
        frame = _load_legacy_file(path=path, ticker_fallback=ticker)
        if not frame.empty:
            frames.append(frame)

    if not frames:
        raise RuntimeError(
            "No legacy fundamentals matched the provided universe tickers."
        )

    canonical = pd.concat(frames, ignore_index=True)
    canonical = _apply_date_filter(canonical, start_date=start_date, end_date=end_date)
    canonical = canonical.sort_values(["ticker", "fyearq", "fqtr"]).reset_index(drop=True)
    canonical = canonical.drop_duplicates(subset=["ticker", "fyearq", "fqtr"], keep="last")

    canonical.to_csv(resolved_output_dir / canonical_filename, index=False)
    _write_year_partitions(canonical, resolved_output_dir)
    return canonical
