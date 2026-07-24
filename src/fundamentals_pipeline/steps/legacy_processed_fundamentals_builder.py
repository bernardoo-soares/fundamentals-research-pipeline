"""Legacy fundamentals canonicalization and Stage 1 publishing.

This module reads local `Processed-Fundamentals` CSV files, normalizes the raw
accounting fields into a canonical quarterly schema, and can publish raw-only
Stage 1 yearly outputs plus QA artifacts.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from pathlib import Path

import pandas as pd

from ..contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    EXTENDED_RAW_FIELDS,
    STAGE1_RAW_COLUMNS,
    SUPPORT_RAW_FIELDS,
    validate_stage1_frame_columns,
)
from ..core.logging import get_logger
from ..core.settings import get_settings

LOG = get_logger(__name__)

LEGACY_STAGE1_FIELDS: tuple[str, ...] = (
    *CORE_RAW_FIELDS,
    *SUPPORT_RAW_FIELDS,
    *EXTENDED_RAW_FIELDS,
)

# Canonical field -> legacy source column, declared where the two differ.
# This is a source selection, never a fallback: if the named source column is
# absent or null, the canonical field is null.
LEGACY_SOURCE_COLUMN_OVERRIDES: dict[str, str] = {
    # Compustat `req` is ADJUSTED retained earnings: the identity
    # `req = reunaq + acomincq` holds within 0.1% for 98.4% of 19,982
    # legacy ticker-years. SimFin publishes the as-reported line and has no
    # AOCI column at all, so the only way the two eras can mean the same
    # thing is to take Compustat's UNADJUSTED column here. Measured on the
    # FY2023 overlap: `req` agreed 23.3%, `reunaq` agrees 95.8% (median
    # relative difference 0.0000). See contracts/field_era_semantics.py.
    "req": "reunaq",
}

# Canonical field -> legacy source columns summed, where no single Compustat
# column carries the concept the other provider publishes. Summed, never
# fallback-chained: a null part is treated as absent-and-zero only where that
# is validated by measurement (see below).
LEGACY_SOURCE_COLUMN_SUMS: dict[str, tuple[str, ...]] = {
    # SimFin publishes one equity line, "Total Equity", which includes
    # noncontrolling interests. Compustat `ceqq` is Common/Ordinary Equity and
    # excludes them. Measured on the FY2023 overlap: ceqq agrees 64.7%, teqq
    # 86.3%, seqq+mibtq 94.0%. `mibtq` is null for 5.1% of rows and exactly
    # zero for 45.6% of those present; treating null as zero holds agreement at
    # 94.0% while recovering those rows, which is the measurement that
    # justifies it -- a company that reports no noncontrolling-interest line
    # has none.
    "ceqq": ("seqq", "mibtq"),
}
LEGACY_TICKER_ALIASES: dict[str, tuple[str, ...]] = {
    "GOOG": ("GOOG", "GOOGL"),
    "GOOGL": ("GOOGL", "GOOG"),
    "FOX": ("FOX", "FOXA"),
    "FOXA": ("FOXA", "FOX"),
    "NWS": ("NWS", "NWSA"),
    "NWSA": ("NWSA", "NWS"),
}
LEGACY_CONFLICT_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "quarter",
    "source_file",
    "period_end",
    "row_count",
    "conflict_reason",
)
LEGACY_MISSING_COLUMNS: tuple[str, ...] = ("ticker", "reason")


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
    """Load and normalize ticker set from the universe artifact."""
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
        "tstkq",
        *LEGACY_STAGE1_FIELDS,
        *LEGACY_SOURCE_COLUMN_OVERRIDES.values(),
        *(c for parts in LEGACY_SOURCE_COLUMN_SUMS.values() for c in parts),
    }


def _legacy_ticker_candidates(ticker: str) -> tuple[str, ...]:
    """Return current-ticker-first raw filename candidates for one symbol."""
    normalized = _normalize_ticker(ticker)
    if normalized is None:
        return ()
    return LEGACY_TICKER_ALIASES.get(normalized, (normalized,))


def _coerce_numeric_columns(
    df: pd.DataFrame,
    columns: Iterable[str],
) -> pd.DataFrame:
    """Coerce selected DataFrame columns to numeric in-place."""
    for column in columns:
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    return df


def _ensure_stage1_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure all Stage 1 raw/support fields exist in the frame."""
    for field in LEGACY_STAGE1_FIELDS:
        if field not in df.columns:
            df[field] = pd.NA
    return df


def _apply_source_column_overrides(
    df: pd.DataFrame,
    *,
    source_file: str | None = None,
) -> pd.DataFrame:
    """Point canonical fields at their declared legacy source column.

    Applied before `_ensure_stage1_fields` so the canonical name is populated
    from the declared source rather than from a same-named column that means
    something else. When the source column is absent, the canonical field is
    set null -- it never falls back to the same-named column.

    A missing source column nulls the canonical field for every row of that
    file, which is indistinguishable downstream from genuinely absent data, so
    it is logged rather than applied silently.
    """
    for canonical, parts in LEGACY_SOURCE_COLUMN_SUMS.items():
        if parts[0] not in df.columns:
            LOG.warning(
                "Legacy source column %r for canonical %r is absent from %s; "
                "%r will be null for all %d rows of this file.",
                parts[0], canonical, source_file or "<unknown file>",
                canonical, len(df),
            )
            df[canonical] = pd.NA
            continue
        total = pd.to_numeric(df[parts[0]], errors="coerce")
        for extra in parts[1:]:
            addend = (
                pd.to_numeric(df[extra], errors="coerce")
                if extra in df.columns
                else pd.Series(0.0, index=df.index)
            )
            total = total + addend.fillna(0.0)
        df[canonical] = total

    for canonical, source in LEGACY_SOURCE_COLUMN_OVERRIDES.items():
        if source in df.columns:
            df[canonical] = pd.to_numeric(df[source], errors="coerce")
            continue
        LOG.warning(
            "Legacy source column %r for canonical %r is absent from %s; "
            "%r will be null for all %d rows of this file.",
            source,
            canonical,
            source_file or "<unknown file>",
            canonical,
            len(df),
        )
        df[canonical] = pd.NA
    return df


def _prepare_legacy_frame(
    df: pd.DataFrame,
    *,
    source_file: str | None = None,
) -> pd.DataFrame:
    """Ensure every Stage 1 field exists and is numeric.

    Deliberately performs NO substitution. Fields absent from the legacy
    extract stay null:

    - `prstkcq` has no Compustat quarterly column at all; it was previously
      filled from `cshopq` ("Total Shares Repurchased - Quarter"), putting a
      share count into a currency field, and then from `prstkcy / 4`, which
      is flat imputation.
    - `cshfdq` ("Com Shares for Diluted EPS") must never be back-filled from
      `cshoq` ("Common Shares Outstanding") -- a different quantity.
    - A former `tstkq <- tstkcq` branch was removed as dead code: `tstkcq` is
      absent from every file in this Compustat extract (verified across 300
      files), and the branch was gated on `tstkq` being absent, which it never
      is.

    See AGENTS.md S4.2 (no imputation, ever) and
    contracts/field_era_semantics.py for the declared per-era semantics.
    """
    df = _apply_source_column_overrides(df, source_file=source_file)
    df = _ensure_stage1_fields(df)
    return _coerce_numeric_columns(df, LEGACY_STAGE1_FIELDS)


def _load_legacy_file(path: Path, ticker_fallback: str) -> pd.DataFrame:
    """Load and normalize one legacy ticker CSV file."""
    df = pd.read_csv(path, usecols=lambda column: column in _legacy_input_columns())
    if df.empty:
        return pd.DataFrame()

    if "tic" in df.columns:
        df["ticker"] = df["tic"].map(_normalize_ticker).fillna(ticker_fallback)
    else:
        df["ticker"] = ticker_fallback

    df["source_file"] = path.name
    df = _prepare_legacy_frame(df, source_file=path.name)

    if "datadate" in df.columns:
        df["period_end"] = pd.to_datetime(df["datadate"], errors="coerce")
    else:
        df["period_end"] = pd.NaT

    df = _coerce_numeric_columns(df, ["fyearq", "fqtr"])

    if "fyearq" not in df.columns:
        df["fyearq"] = pd.NA
    if "fqtr" not in df.columns:
        df["fqtr"] = pd.NA

    df = df.dropna(subset=["ticker", "fyearq", "fqtr"])
    if df.empty:
        return pd.DataFrame()

    df["fyearq"] = df["fyearq"].astype("int64")
    df["fqtr"] = df["fqtr"].astype("int64")
    df = df[df["fqtr"].between(1, 4)]
    if df.empty:
        return pd.DataFrame()

    df["source_system"] = "legacy_processed_fundamentals"
    df["source_tag_map_version"] = "legacy-v1"
    df["filed_date"] = pd.NaT
    df["form_type"] = pd.NA

    keep_columns = [
        "ticker",
        "fyearq",
        "fqtr",
        "period_end",
        "filed_date",
        "form_type",
        "source_system",
        "source_tag_map_version",
        "source_file",
        *LEGACY_STAGE1_FIELDS,
    ]
    return df[keep_columns]


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


def _filter_stage1_year_range(
    df: pd.DataFrame,
    *,
    start_year: int,
    end_year: int,
    year_column: str,
) -> pd.DataFrame:
    """Filter rows by exact fiscal year range."""
    year_values = pd.to_numeric(df[year_column], errors="coerce")
    return df[(year_values >= start_year) & (year_values <= end_year)].copy()


def _collect_quarter_conflicts(
    df: pd.DataFrame,
    *,
    key_columns: list[str],
) -> pd.DataFrame:
    """Collect duplicate quarterly-key conflicts before deterministic dedupe."""
    conflict_columns = [
        *key_columns,
        "source_file",
        "period_end",
        "row_count",
        "conflict_reason",
    ]
    if df.empty:
        return pd.DataFrame(columns=conflict_columns)

    counts = df.groupby(key_columns, dropna=False).size().reset_index(name="row_count")
    conflicts = counts[counts["row_count"] > 1].copy()
    if conflicts.empty:
        return pd.DataFrame(columns=conflict_columns)

    detail = df[key_columns + ["source_file", "period_end"]].copy()
    out = conflicts.merge(detail, on=key_columns, how="left")
    out["conflict_reason"] = "duplicate_quarter_key"
    return out[conflict_columns].sort_values(
        key_columns + ["period_end", "source_file"],
        kind="mergesort",
    ).reset_index(drop=True)


def _dedupe_quarterly_rows(
    df: pd.DataFrame,
    *,
    key_columns: list[str],
) -> pd.DataFrame:
    """Keep the latest row per deterministic quarterly key."""
    if df.empty:
        return df.copy()

    sort_columns = [*key_columns, "period_end", "source_file"]
    present_sort_columns = [column for column in sort_columns if column in df.columns]
    return (
        df.sort_values(present_sort_columns, kind="mergesort")
        .drop_duplicates(subset=key_columns, keep="last")
        .reset_index(drop=True)
    )


def _write_year_partitions(df: pd.DataFrame, output_dir: Path) -> None:
    """Write legacy canonical year-partitioned CSV artifacts."""
    for year, frame in df.groupby("fyearq"):
        year = int(year)
        fundamentals_path = output_dir / f"fundamentals_q_{year}.csv"
        frame.to_csv(fundamentals_path, index=False)


def _collect_legacy_frames(
    *,
    tickers: set[str],
    raw_dir: Path,
) -> tuple[list[pd.DataFrame], set[str]]:
    """Load all legacy files that match the requested universe tickers."""
    frames: list[pd.DataFrame] = []
    matched_tickers: set[str] = set()
    raw_files_by_prefix = {
        _normalize_ticker(path.stem.split("-")[0]): path
        for path in sorted(raw_dir.glob("*.csv"))
    }

    for ticker in sorted(tickers):
        resolved_path: Path | None = None
        for candidate in _legacy_ticker_candidates(ticker):
            resolved_path = raw_files_by_prefix.get(candidate)
            if resolved_path is not None:
                break
        if resolved_path is None:
            continue

        matched_tickers.add(ticker)
        frame = _load_legacy_file(path=resolved_path, ticker_fallback=ticker)
        if not frame.empty:
            frame["ticker"] = ticker
            frames.append(frame)
    return frames, matched_tickers


def _prepare_stage1_publish_frame(
    df: pd.DataFrame,
    *,
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Rename and trim canonical legacy rows into raw-only Stage 1 shape."""
    stage1 = df.rename(columns={"fyearq": "year", "fqtr": "quarter"}).copy()
    stage1 = _filter_stage1_year_range(
        stage1,
        start_year=start_year,
        end_year=end_year,
        year_column="year",
    )
    if stage1.empty:
        return pd.DataFrame(columns=STAGE1_RAW_COLUMNS)

    stage1 = stage1[list(STAGE1_RAW_COLUMNS)].sort_values(
        ["ticker", "year", "quarter"],
        kind="mergesort",
    )
    stage1 = stage1.reset_index(drop=True)
    validate_stage1_frame_columns(stage1.columns.tolist())
    return stage1


def build_legacy_raw_stage1_compare_frame(
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path | None = None,
    start_year: int = 2006,
    end_year: int = 2023,
) -> pd.DataFrame:
    """Build expected Stage 1 rows with `source_file` retained for auditing."""
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    settings = get_settings()
    universe_tickers = _load_universe_tickers(universe_path)
    resolved_raw_dir = Path(raw_dir) if raw_dir else settings.legacy_fundamentals_dir

    if not resolved_raw_dir.exists():
        raise FileNotFoundError(f"Legacy fundamentals directory not found: {resolved_raw_dir}")

    frames, _matched_tickers = _collect_legacy_frames(
        tickers=universe_tickers,
        raw_dir=resolved_raw_dir,
    )
    if not frames:
        return pd.DataFrame(columns=[*STAGE1_RAW_COLUMNS, "source_file"])

    canonical = pd.concat(frames, ignore_index=True)
    stage1_base = canonical.rename(columns={"fyearq": "year", "fqtr": "quarter"})
    stage1_base = _filter_stage1_year_range(
        stage1_base,
        start_year=start_year,
        end_year=end_year,
        year_column="year",
    )
    stage1_deduped = _dedupe_quarterly_rows(
        stage1_base,
        key_columns=["ticker", "year", "quarter"],
    )

    for field in STAGE1_RAW_COLUMNS:
        if field not in stage1_deduped.columns:
            stage1_deduped[field] = pd.NA
    if "source_file" not in stage1_deduped.columns:
        stage1_deduped["source_file"] = pd.NA

    compare_frame = stage1_deduped[[*STAGE1_RAW_COLUMNS, "source_file"]].sort_values(
        ["ticker", "year", "quarter"],
        kind="mergesort",
    )
    compare_frame = compare_frame.reset_index(drop=True)
    validate_stage1_frame_columns(compare_frame[list(STAGE1_RAW_COLUMNS)].columns.tolist())
    return compare_frame


def _write_stage1_year_partitions(
    df: pd.DataFrame,
    *,
    output_dir: Path,
    start_year: int,
    end_year: int,
) -> dict[str, str]:
    """Write one raw-only Stage 1 CSV per year in the requested window."""
    artifacts: dict[str, str] = {}
    for year in range(start_year, end_year + 1):
        year_path = output_dir / f"raw_fundamentals_{year}.csv"
        year_df = df[df["year"] == year].copy() if not df.empty else pd.DataFrame(
            columns=STAGE1_RAW_COLUMNS
        )
        if year_df.empty:
            year_df = pd.DataFrame(columns=STAGE1_RAW_COLUMNS)
        year_df.to_csv(year_path, index=False)
        artifacts[f"processed_{year}"] = str(year_path)
    return artifacts


def _build_stage1_coverage(
    df: pd.DataFrame,
    *,
    universe_tickers: set[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Build yearly coverage metrics for the Stage 1 raw outputs."""
    rows: list[dict[str, int]] = []
    for year in range(start_year, end_year + 1):
        year_df = df[df["year"] == year].copy() if not df.empty else pd.DataFrame(
            columns=STAGE1_RAW_COLUMNS
        )
        quarter_counts = (
            year_df.groupby("ticker")["quarter"].nunique() if not year_df.empty else pd.Series(dtype="int64")
        )
        full_tickers = set(quarter_counts[quarter_counts == 4].index.tolist())
        row: dict[str, int] = {
            "year": year,
            "expected_universe_tickers": len(universe_tickers),
            "rows_emitted": int(len(year_df)),
            "unique_tickers_emitted": int(year_df["ticker"].nunique()) if not year_df.empty else 0,
            "complete_quarter_rows": int(len(year_df[year_df["ticker"].isin(full_tickers)]))
            if full_tickers
            else 0,
        }
        for field in LEGACY_STAGE1_FIELDS:
            row[f"non_null_{field}"] = int(year_df[field].notna().sum()) if field in year_df.columns else 0
        rows.append(row)
    return pd.DataFrame(rows)


def _build_missing_universe_report(
    df: pd.DataFrame,
    *,
    universe_tickers: set[str],
    matched_tickers: set[str],
) -> pd.DataFrame:
    """Build a report for current-universe tickers missing from Stage 1 output."""
    emitted_tickers = set(df["ticker"].astype(str).str.upper()) if not df.empty else set()
    rows: list[dict[str, str]] = []
    for ticker in sorted(universe_tickers):
        if ticker not in matched_tickers:
            rows.append({"ticker": ticker, "reason": "missing_raw_file"})
            continue
        if ticker not in emitted_tickers:
            rows.append({"ticker": ticker, "reason": "no_rows_in_year_window"})
    return pd.DataFrame(rows, columns=LEGACY_MISSING_COLUMNS)


def build_legacy_fundamentals(
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    canonical_filename: str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> pd.DataFrame:
    """Build canonical quarterly legacy fundamentals for current universe."""
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

    frames, _matched_tickers = _collect_legacy_frames(
        tickers=tickers,
        raw_dir=resolved_raw_dir,
    )
    if not frames:
        raise RuntimeError("No legacy fundamentals matched the provided universe tickers.")

    canonical = pd.concat(frames, ignore_index=True)
    canonical = _apply_date_filter(canonical, start_date=start_date, end_date=end_date)
    canonical = canonical.sort_values(["ticker", "fyearq", "fqtr"], kind="mergesort")
    canonical = _dedupe_quarterly_rows(
        canonical,
        key_columns=["ticker", "fyearq", "fqtr"],
    )

    published = canonical.drop(columns=["source_file"], errors="ignore")
    published.to_csv(resolved_output_dir / canonical_filename, index=False)
    _write_year_partitions(published, resolved_output_dir)
    return published


def build_legacy_raw_stage1(
    universe_path: str | Path = "data/universe_current.csv",
    raw_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    reports_dir: str | Path | None = None,
    start_year: int = 2006,
    end_year: int = 2023,
) -> dict[str, str]:
    """Build raw-only Stage 1 yearly CSVs from local legacy source files."""
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    settings = get_settings()
    universe_tickers = _load_universe_tickers(universe_path)
    resolved_raw_dir = Path(raw_dir) if raw_dir else settings.legacy_fundamentals_dir
    resolved_output_dir = Path(output_dir) if output_dir else settings.processed_data_dir
    resolved_reports_dir = Path(reports_dir) if reports_dir else settings.reports_data_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_reports_dir.mkdir(parents=True, exist_ok=True)

    if not resolved_raw_dir.exists():
        raise FileNotFoundError(f"Legacy fundamentals directory not found: {resolved_raw_dir}")

    frames, matched_tickers = _collect_legacy_frames(
        tickers=universe_tickers,
        raw_dir=resolved_raw_dir,
    )
    if not frames:
        raise RuntimeError("No legacy fundamentals matched the provided universe tickers.")

    canonical = pd.concat(frames, ignore_index=True)
    stage1_base = canonical.rename(columns={"fyearq": "year", "fqtr": "quarter"})
    stage1_base = _filter_stage1_year_range(
        stage1_base,
        start_year=start_year,
        end_year=end_year,
        year_column="year",
    )

    conflicts = _collect_quarter_conflicts(
        stage1_base,
        key_columns=["ticker", "year", "quarter"],
    )
    conflicts_output = (
        resolved_reports_dir / f"legacy_raw_conflicts_{start_year}_{end_year}.csv"
    )
    conflicts.to_csv(conflicts_output, index=False)

    stage1_deduped = _dedupe_quarterly_rows(
        stage1_base,
        key_columns=["ticker", "year", "quarter"],
    )
    stage1 = _prepare_stage1_publish_frame(
        stage1_deduped,
        start_year=start_year,
        end_year=end_year,
    )

    year_outputs = _write_stage1_year_partitions(
        stage1,
        output_dir=resolved_output_dir,
        start_year=start_year,
        end_year=end_year,
    )

    coverage = _build_stage1_coverage(
        stage1,
        universe_tickers=universe_tickers,
        start_year=start_year,
        end_year=end_year,
    )
    coverage_output = (
        resolved_reports_dir / f"legacy_raw_coverage_{start_year}_{end_year}.csv"
    )
    coverage.to_csv(coverage_output, index=False)

    missing = _build_missing_universe_report(
        stage1,
        universe_tickers=universe_tickers,
        matched_tickers=matched_tickers,
    )
    missing_output = (
        resolved_reports_dir
        / f"legacy_raw_missing_universe_{start_year}_{end_year}.csv"
    )
    missing.to_csv(missing_output, index=False)

    artifacts = {
        "coverage_output": str(coverage_output),
        "missing_output": str(missing_output),
        "conflicts_output": str(conflicts_output),
    }
    artifacts.update(year_outputs)
    return artifacts
