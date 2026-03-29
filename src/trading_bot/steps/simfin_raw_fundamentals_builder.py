"""Build raw fundamentals CSVs from SimFin statement datasets."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..connectors.simfin_dataset_loader import SimfinConnector
from ..contracts.stage1_fundamentals_schema import (
    CORE_RAW_FIELDS,
    STAGE1_OUTPUT_COLUMNS,
    SUPPORT_RAW_FIELDS,
    validate_stage1_frame_columns,
)
from ..core.settings import get_settings


SIMFIN_FIELDS: tuple[str, ...] = (*CORE_RAW_FIELDS, *SUPPORT_RAW_FIELDS)
SIMFIN_MISSING_COLUMNS: tuple[str, ...] = ("ticker", "reason")
SIMFIN_MISSING_ROW_COLUMNS: tuple[str, ...] = ("ticker", "year", "quarter", "reason")
SIMFIN_MISSING_FIELD_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "quarter",
    "field_name",
    "reason",
    "source_family",
)
SIMFIN_CONFLICT_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "quarter",
    "source_family",
    "mapped_non_null_count",
)
SIMFIN_FAMILY_PRIORITY: dict[str, int] = {
    "banks": 0,
    "insurance": 1,
    "general": 2,
}
SIMFIN_FAMILY_DATASETS: dict[str, tuple[str, str, str]] = {
    "general": ("income_general", "balance_general", "cashflow_general"),
    "banks": ("income_banks", "balance_banks", "cashflow_banks"),
    "insurance": ("income_insurance", "balance_insurance", "cashflow_insurance"),
}
SIMFIN_ANNUAL_CASHFLOW_FAMILY_DATASETS: dict[str, str] = {
    "general": "cashflow_general_annual",
    "banks": "cashflow_banks_annual",
    "insurance": "cashflow_insurance_annual",
}
SIMFIN_ANNUAL_SUPPORT_COLUMN_MAP: dict[str, str] = {
    "Net Cash from Operating Activities": "Net Cash from Operating Activities__annual",
    "Change in Fixed Assets & Intangibles": "Change in Fixed Assets & Intangibles__annual",
    "Cash from (Repurchase of) Equity": "Cash from (Repurchase of) Equity__annual",
}


def _normalize_ticker(value: object) -> str | None:
    """Normalize ticker strings to uppercase or return `None` when empty."""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return text


def _coerce_quarter(value: object) -> int | None:
    """Convert SimFin fiscal period labels to integer quarter numbers."""
    text = str(value or "").strip().upper()
    if text.startswith("Q") and len(text) >= 2 and text[1].isdigit():
        quarter = int(text[1])
        if 1 <= quarter <= 4:
            return quarter
    return None


def _load_universe_tickers(universe_path: str | Path) -> set[str]:
    """Load and normalize the requested ticker universe."""
    df = pd.read_csv(universe_path, dtype=str)
    if "ticker" not in df.columns:
        raise ValueError(f"Universe file '{universe_path}' is missing 'ticker' column.")
    return {
        ticker
        for ticker in (_normalize_ticker(value) for value in df["ticker"].tolist())
        if ticker is not None
    }


def _normalize_quarterly_frame(
    frame: pd.DataFrame,
    *,
    tickers: set[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Normalize one raw SimFin dataset to the shared quarter key."""
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "year", "quarter"])

    normalized = frame.copy()
    normalized["ticker"] = normalized.get("Ticker", pd.Series(index=normalized.index)).map(
        _normalize_ticker
    )
    normalized["year"] = pd.to_numeric(
        normalized.get("Fiscal Year", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["quarter"] = normalized.get(
        "Fiscal Period",
        pd.Series(index=normalized.index),
    ).map(_coerce_quarter)
    normalized["report_date"] = pd.to_datetime(
        normalized.get("Report Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["publish_date"] = pd.to_datetime(
        normalized.get("Publish Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["restated_date"] = pd.to_datetime(
        normalized.get("Restated Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )

    normalized = normalized[
        normalized["ticker"].isin(tickers)
        & normalized["year"].between(start_year, end_year, inclusive="both")
        & normalized["quarter"].notna()
    ].copy()
    if normalized.empty:
        return pd.DataFrame(columns=["ticker", "year", "quarter"])

    normalized["year"] = normalized["year"].astype("int64")
    normalized["quarter"] = normalized["quarter"].astype("int64")
    normalized = normalized.sort_values(
        ["ticker", "year", "quarter", "restated_date", "publish_date", "report_date"],
        kind="mergesort",
    )
    normalized = normalized.drop_duplicates(
        subset=["ticker", "year", "quarter"],
        keep="last",
    )
    return normalized.reset_index(drop=True)


def _normalize_annual_frame(
    frame: pd.DataFrame,
    *,
    tickers: set[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Normalize one raw SimFin annual dataset to the shared ticker-year key."""
    if frame.empty:
        return pd.DataFrame(columns=["ticker", "year"])

    normalized = frame.copy()
    normalized["ticker"] = normalized.get("Ticker", pd.Series(index=normalized.index)).map(
        _normalize_ticker
    )
    normalized["year"] = pd.to_numeric(
        normalized.get("Fiscal Year", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["report_date"] = pd.to_datetime(
        normalized.get("Report Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["publish_date"] = pd.to_datetime(
        normalized.get("Publish Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )
    normalized["restated_date"] = pd.to_datetime(
        normalized.get("Restated Date", pd.Series(index=normalized.index)),
        errors="coerce",
    )

    normalized = normalized[
        normalized["ticker"].isin(tickers)
        & normalized["year"].between(start_year, end_year, inclusive="both")
    ].copy()
    if normalized.empty:
        return pd.DataFrame(columns=["ticker", "year"])

    normalized["year"] = normalized["year"].astype("int64")
    normalized = normalized.sort_values(
        ["ticker", "year", "restated_date", "publish_date", "report_date"],
        kind="mergesort",
    )
    normalized = normalized.drop_duplicates(
        subset=["ticker", "year"],
        keep="last",
    )
    return normalized.reset_index(drop=True)


def _merge_statement_frames(
    left: pd.DataFrame,
    right: pd.DataFrame,
) -> pd.DataFrame:
    """Outer merge two normalized statement frames and coalesce shared columns."""
    key = ["ticker", "year", "quarter"]
    if left.empty:
        return right.copy()
    if right.empty:
        return left.copy()

    merged = left.merge(
        right,
        on=key,
        how="outer",
        suffixes=("", "__dup"),
    )
    duplicate_columns = [column for column in merged.columns if column.endswith("__dup")]
    for duplicate in duplicate_columns:
        original = duplicate[:-5]
        if original in merged.columns:
            merged[original] = merged[original].combine_first(merged[duplicate])
        else:
            merged = merged.rename(columns={duplicate: original})
        merged = merged.drop(columns=duplicate)
    return merged


def _merge_annual_support_frame(
    quarterly_frame: pd.DataFrame,
    annual_frame: pd.DataFrame,
) -> pd.DataFrame:
    """Attach annual support columns to quarterly rows by ticker and year."""
    if quarterly_frame.empty or annual_frame.empty:
        return quarterly_frame.copy()

    annual_columns = [
        source_name
        for source_name in SIMFIN_ANNUAL_SUPPORT_COLUMN_MAP
        if source_name in annual_frame.columns
    ]
    if not annual_columns:
        return quarterly_frame.copy()

    annual_subset = annual_frame[["ticker", "year", *annual_columns]].rename(
        columns=SIMFIN_ANNUAL_SUPPORT_COLUMN_MAP
    )
    return quarterly_frame.merge(
        annual_subset,
        on=["ticker", "year"],
        how="left",
    )


def _empty_numeric_series(frame: pd.DataFrame) -> pd.Series:
    """Create an all-null float series aligned to the provided frame."""
    return pd.Series([float("nan")] * len(frame), index=frame.index, dtype="float64")


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    """Return a numeric series for a column, or nulls when the column is absent."""
    if column not in frame.columns:
        return _empty_numeric_series(frame)
    return pd.to_numeric(frame[column], errors="coerce")


def _positive_outflow(frame: pd.DataFrame, column: str) -> pd.Series:
    """Convert SimFin negative cash outflows into positive spend values."""
    raw = _numeric_series(frame, column)
    return -raw


def _derive_eps(frame: pd.DataFrame) -> pd.Series:
    """Derive quarterly EPS from common net income and basic share count."""
    numerator = _numeric_series(frame, "Net Income (Common)")
    denominator = _numeric_series(frame, "Shares (Basic)")
    return numerator.where(denominator != 0) / denominator.where(denominator != 0)


def _build_family_canonical(frame: pd.DataFrame, *, family: str) -> pd.DataFrame:
    """Map one SimFin family frame into the raw fundamentals contract."""
    if frame.empty:
        return pd.DataFrame(columns=[*STAGE1_OUTPUT_COLUMNS, "source_family", "mapped_non_null_count"])

    out = pd.DataFrame(
        {
            "ticker": frame["ticker"],
            "year": frame["year"].astype("int64"),
            "quarter": frame["quarter"].astype("int64"),
        }
    )

    out["saleq"] = _numeric_series(frame, "Revenue")
    out["niq"] = _numeric_series(frame, "Net Income")
    out["oiadpq"] = _numeric_series(frame, "Operating Income (Loss)")
    out["txtq"] = _numeric_series(frame, "Income Tax (Expense) Benefit, Net")
    out["epspxq"] = _derive_eps(frame)
    out["atq"] = _numeric_series(frame, "Total Assets")
    out["ceqq"] = _numeric_series(frame, "Total Equity")
    out["dlcq"] = _numeric_series(frame, "Short Term Debt")
    out["dlttq"] = _numeric_series(frame, "Long Term Debt")
    out["req"] = _numeric_series(frame, "Retained Earnings")
    out["tstkq"] = _numeric_series(frame, "Treasury Stock")
    out["oancfq"] = _numeric_series(frame, "Net Cash from Operating Activities")
    out["prstkcq"] = _positive_outflow(frame, "Cash from (Repurchase of) Equity")
    out["capxq"] = _positive_outflow(frame, "Change in Fixed Assets & Intangibles")
    out["cheq"] = _numeric_series(frame, "Cash, Cash Equivalents & Short Term Investments")
    out["dvpq"] = _positive_outflow(frame, "Dividends Paid")
    out["cshfdq"] = _numeric_series(frame, "Shares (Diluted)")
    out["cshoq"] = _numeric_series(frame, "Shares (Basic)")

    if family == "general":
        out["xintq"] = _numeric_series(frame, "Interest Expense, Net")
        out["actq"] = _numeric_series(frame, "Total Current Assets")
        out["lctq"] = _numeric_series(frame, "Total Current Liabilities")
        out["ppentq"] = _numeric_series(frame, "Property, Plant & Equipment, Net")
        out["gdwlq"] = _numeric_series(frame, "Goodwill")
        out["ivltq"] = _numeric_series(frame, "Long Term Investments & Receivables")
    elif family == "banks":
        out["xintq"] = _empty_numeric_series(frame)
        out["actq"] = _empty_numeric_series(frame)
        out["lctq"] = _empty_numeric_series(frame)
        out["ppentq"] = _numeric_series(frame, "Net Fixed Assets")
        out["gdwlq"] = _empty_numeric_series(frame)
        out["ivltq"] = _numeric_series(frame, "Short & Long Term Investments")
    elif family == "insurance":
        out["xintq"] = _empty_numeric_series(frame)
        out["actq"] = _empty_numeric_series(frame)
        out["lctq"] = _empty_numeric_series(frame)
        out["ppentq"] = _numeric_series(frame, "Property, Plant & Equipment, Net")
        out["gdwlq"] = _empty_numeric_series(frame)
        out["ivltq"] = _numeric_series(frame, "Total Investments")
    else:
        raise ValueError(f"Unsupported SimFin family: {family}")

    out["oancfy"] = _numeric_series(frame, "Net Cash from Operating Activities__annual")
    out["capxy"] = _positive_outflow(frame, "Change in Fixed Assets & Intangibles__annual")
    out["prstkcy"] = _positive_outflow(frame, "Cash from (Repurchase of) Equity__annual")
    out["cshopq"] = _empty_numeric_series(frame)
    out["source_family"] = family
    out["mapped_non_null_count"] = out[list(SIMFIN_FIELDS)].notna().sum(axis=1)
    return out[[*STAGE1_OUTPUT_COLUMNS, "source_family", "mapped_non_null_count"]]


def _select_best_family_rows(
    candidates: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Select the strongest family candidate per ticker-year-quarter."""
    if candidates.empty:
        empty = pd.DataFrame(columns=[*STAGE1_OUTPUT_COLUMNS, "source_family"])
        return empty, pd.DataFrame(columns=SIMFIN_CONFLICT_COLUMNS)

    ranked = candidates.copy()
    ranked["source_priority"] = ranked["source_family"].map(SIMFIN_FAMILY_PRIORITY).fillna(99)
    ranked = ranked.sort_values(
        ["ticker", "year", "quarter", "mapped_non_null_count", "source_priority"],
        ascending=[True, True, True, False, True],
        kind="mergesort",
    )

    key = ["ticker", "year", "quarter"]
    conflicts = ranked[ranked.duplicated(subset=key, keep=False)].copy()
    if conflicts.empty:
        conflicts = pd.DataFrame(columns=SIMFIN_CONFLICT_COLUMNS)
    else:
        conflicts = conflicts[
            ["ticker", "year", "quarter", "source_family", "mapped_non_null_count"]
        ].reset_index(drop=True)

    selected = ranked.drop_duplicates(subset=key, keep="first").reset_index(drop=True)
    return selected[[*STAGE1_OUTPUT_COLUMNS, "source_family"]], conflicts


def _write_year_partitions(
    frame: pd.DataFrame,
    *,
    output_dir: Path,
    start_year: int,
    end_year: int,
) -> dict[str, str]:
    """Write one raw fundamentals CSV per requested year."""
    artifacts: dict[str, str] = {}
    for year in range(start_year, end_year + 1):
        year_path = output_dir / f"raw_fundamentals_{year}.csv"
        year_df = frame[frame["year"] == year].copy() if not frame.empty else pd.DataFrame(
            columns=STAGE1_OUTPUT_COLUMNS
        )
        if year_df.empty:
            year_df = pd.DataFrame(columns=STAGE1_OUTPUT_COLUMNS)
        year_df.to_csv(year_path, index=False)
        artifacts[f"processed_{year}"] = str(year_path)
    return artifacts


def _build_coverage(
    frame: pd.DataFrame,
    *,
    universe_tickers: set[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Build yearly coverage metrics for the raw fundamentals outputs."""
    rows: list[dict[str, int]] = []
    for year in range(start_year, end_year + 1):
        year_df = frame[frame["year"] == year].copy() if not frame.empty else pd.DataFrame(
            columns=STAGE1_OUTPUT_COLUMNS
        )
        quarter_counts = (
            year_df.groupby("ticker")["quarter"].nunique()
            if not year_df.empty
            else pd.Series(dtype="int64")
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
        for field in SIMFIN_FIELDS:
            row[f"non_null_{field}"] = int(year_df[field].notna().sum()) if field in year_df.columns else 0
        rows.append(row)
    return pd.DataFrame(rows)


def _build_missing_universe_report(
    frame: pd.DataFrame,
    *,
    universe_tickers: set[str],
) -> pd.DataFrame:
    """List universe tickers with no emitted rows in the requested window."""
    emitted_tickers = set(frame["ticker"].astype(str).str.upper()) if not frame.empty else set()
    rows = [
        {"ticker": ticker, "reason": "no_rows_in_year_window"}
        for ticker in sorted(universe_tickers)
        if ticker not in emitted_tickers
    ]
    return pd.DataFrame(rows, columns=SIMFIN_MISSING_COLUMNS)


def _build_missing_rows_report(
    frame: pd.DataFrame,
    *,
    universe_tickers: set[str],
    start_year: int,
    end_year: int,
) -> pd.DataFrame:
    """Build a quarter-level missing-row report against the requested universe."""
    expected_rows = [
        {"ticker": ticker, "year": year, "quarter": quarter}
        for ticker in sorted(universe_tickers)
        for year in range(start_year, end_year + 1)
        for quarter in range(1, 5)
    ]
    expected = pd.DataFrame(expected_rows)
    observed = frame[["ticker", "year", "quarter"]].drop_duplicates() if not frame.empty else pd.DataFrame(
        columns=["ticker", "year", "quarter"]
    )
    missing = expected.merge(
        observed,
        on=["ticker", "year", "quarter"],
        how="left",
        indicator=True,
    )
    missing = missing[missing["_merge"] == "left_only"].copy()
    missing["reason"] = "missing_simfin_quarter"
    return missing[["ticker", "year", "quarter", "reason"]]


def _build_missing_fields_report(frame: pd.DataFrame) -> pd.DataFrame:
    """Build a row-level null field report for emitted raw fundamentals rows."""
    if frame.empty:
        return pd.DataFrame(columns=SIMFIN_MISSING_FIELD_COLUMNS)

    rows: list[dict[str, object]] = []
    for field in SIMFIN_FIELDS:
        subset = frame[frame[field].isna()][["ticker", "year", "quarter", "source_family"]]
        for _, row in subset.iterrows():
            rows.append(
                {
                    "ticker": row["ticker"],
                    "year": int(row["year"]),
                    "quarter": int(row["quarter"]),
                    "field_name": field,
                    "reason": "null_simfin_field",
                    "source_family": row["source_family"],
                }
            )
    return pd.DataFrame(rows, columns=SIMFIN_MISSING_FIELD_COLUMNS)


def build_simfin_raw_fundamentals(
    *,
    universe_path: str | Path = "data/universe_current.csv",
    output_dir: str | Path | None = None,
    reports_dir: str | Path | None = None,
    start_year: int = 2023,
    end_year: int = 2025,
    connector: SimfinConnector | None = None,
) -> dict[str, str]:
    """Build yearly raw fundamentals CSVs for a universe using SimFin data."""
    if start_year > end_year:
        raise ValueError("start_year must be less than or equal to end_year.")

    settings = get_settings()
    universe_tickers = _load_universe_tickers(universe_path)
    resolved_output_dir = Path(output_dir) if output_dir else settings.processed_data_dir
    resolved_reports_dir = Path(reports_dir) if reports_dir else settings.reports_data_dir
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    resolved_reports_dir.mkdir(parents=True, exist_ok=True)

    if connector is None:
        connector = SimfinConnector()

    bundle = connector.load_raw_fundamentals_datasets()

    family_candidates: list[pd.DataFrame] = []
    for family, dataset_names in SIMFIN_FAMILY_DATASETS.items():
        normalized_frames = [
            _normalize_quarterly_frame(
                bundle[dataset_name],
                tickers=universe_tickers,
                start_year=start_year,
                end_year=end_year,
            )
            for dataset_name in dataset_names
        ]
        annual_frame = _normalize_annual_frame(
            bundle[SIMFIN_ANNUAL_CASHFLOW_FAMILY_DATASETS[family]],
            tickers=universe_tickers,
            start_year=start_year,
            end_year=end_year,
        )
        merged = normalized_frames[0]
        for candidate in normalized_frames[1:]:
            merged = _merge_statement_frames(merged, candidate)
        merged = _merge_annual_support_frame(merged, annual_frame)
        family_candidates.append(_build_family_canonical(merged, family=family))

    nonempty_candidates = [frame for frame in family_candidates if not frame.empty]
    if nonempty_candidates:
        candidates = pd.concat(nonempty_candidates, ignore_index=True)
    else:
        candidates = pd.DataFrame(columns=[*STAGE1_OUTPUT_COLUMNS, "source_family", "mapped_non_null_count"])
    selected, conflicts = _select_best_family_rows(candidates)
    selected = selected.sort_values(["ticker", "year", "quarter"], kind="mergesort").reset_index(drop=True)
    validate_stage1_frame_columns(selected.columns[: len(STAGE1_OUTPUT_COLUMNS)].tolist())

    year_outputs = _write_year_partitions(
        selected[list(STAGE1_OUTPUT_COLUMNS)],
        output_dir=resolved_output_dir,
        start_year=start_year,
        end_year=end_year,
    )

    coverage = _build_coverage(
        selected,
        universe_tickers=universe_tickers,
        start_year=start_year,
        end_year=end_year,
    )
    coverage_output = resolved_reports_dir / f"simfin_raw_coverage_{start_year}_{end_year}.csv"
    coverage.to_csv(coverage_output, index=False)

    missing_universe = _build_missing_universe_report(
        selected,
        universe_tickers=universe_tickers,
    )
    missing_universe_output = (
        resolved_reports_dir / f"simfin_raw_missing_universe_{start_year}_{end_year}.csv"
    )
    missing_universe.to_csv(missing_universe_output, index=False)

    missing_rows = _build_missing_rows_report(
        selected,
        universe_tickers=universe_tickers,
        start_year=start_year,
        end_year=end_year,
    )
    missing_rows_output = (
        resolved_reports_dir / f"simfin_raw_missing_rows_{start_year}_{end_year}.csv"
    )
    missing_rows.to_csv(missing_rows_output, index=False)

    missing_fields = _build_missing_fields_report(selected)
    missing_fields_output = (
        resolved_reports_dir / f"simfin_raw_missing_fields_{start_year}_{end_year}.csv"
    )
    missing_fields.to_csv(missing_fields_output, index=False)

    conflicts_output = (
        resolved_reports_dir / f"simfin_raw_family_conflicts_{start_year}_{end_year}.csv"
    )
    conflicts.to_csv(conflicts_output, index=False)

    artifacts = {
        "coverage_output": str(coverage_output),
        "missing_universe_output": str(missing_universe_output),
        "missing_rows_output": str(missing_rows_output),
        "missing_fields_output": str(missing_fields_output),
        "family_conflicts_output": str(conflicts_output),
    }
    artifacts.update(year_outputs)
    return artifacts
