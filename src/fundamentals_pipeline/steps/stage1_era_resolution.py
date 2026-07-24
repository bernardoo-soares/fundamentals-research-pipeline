"""Merge the two providers' Stage 1 frames at the publish boundary.

Each builder writes into its own staging directory; this step decides which
provider serves each ticker-year, stamps `source_era`, and emits the single
canonical published CSV that the warehouse loader reads.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..contracts.era_resolution import SourceEra, resolve_ticker_year_provider
from ..contracts.stage1_fundamentals_schema import (
    STAGE1_OUTPUT_COLUMNS,
    STAGE1_RAW_COLUMNS,
)

DECISION_COLUMNS: tuple[str, ...] = (
    "ticker",
    "year",
    "legacy_quarters",
    "simfin_quarters",
    "chosen_era",
    "reason",
)

_NO_COMPLETE_YEAR = "no complete year in either provider"
_COMPLETE_YEAR = "complete year"


def _quarter_counts(frame: pd.DataFrame, year: int) -> pd.Series:
    """Distinct quarters each ticker has for a fiscal year."""
    if frame.empty or "year" not in frame.columns:
        return pd.Series(dtype="int64")
    subset = frame[frame["year"] == year]
    if subset.empty:
        return pd.Series(dtype="int64")
    return subset.groupby("ticker")["quarter"].nunique()


def resolve_era_frames(
    *,
    legacy_frame: pd.DataFrame,
    simfin_frame: pd.DataFrame,
    year: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Resolve one fiscal year to a single provider per ticker.

    Returns the published rows (with `source_era` stamped) and a per-ticker
    decision log. Pure: no I/O, no clock, no randomness.
    """
    legacy_counts = _quarter_counts(legacy_frame, year)
    simfin_counts = _quarter_counts(simfin_frame, year)
    tickers = sorted(set(legacy_counts.index) | set(simfin_counts.index))

    selected: list[pd.DataFrame] = []
    decisions: list[dict[str, object]] = []
    for ticker in tickers:
        legacy_quarters = int(legacy_counts.get(ticker, 0))
        simfin_quarters = int(simfin_counts.get(ticker, 0))
        chosen = resolve_ticker_year_provider(
            legacy_quarters=legacy_quarters,
            simfin_quarters=simfin_quarters,
        )
        decisions.append(
            {
                "ticker": ticker,
                "year": year,
                "legacy_quarters": legacy_quarters,
                "simfin_quarters": simfin_quarters,
                "chosen_era": chosen,
                "reason": _NO_COMPLETE_YEAR if chosen is None else _COMPLETE_YEAR,
            }
        )
        if chosen is None:
            continue
        source = simfin_frame if chosen is SourceEra.SIMFIN else legacy_frame
        rows = source[
            (source["ticker"] == ticker) & (source["year"] == year)
        ].copy()
        rows["source_era"] = str(chosen)
        selected.append(rows)

    if selected:
        resolved = pd.concat(selected, ignore_index=True)
        resolved = resolved[list(STAGE1_OUTPUT_COLUMNS)]
        resolved = resolved.sort_values(list(STAGE1_RAW_COLUMNS[:3]))
        resolved = resolved.reset_index(drop=True)
    else:
        resolved = pd.DataFrame(columns=list(STAGE1_OUTPUT_COLUMNS))

    return resolved, pd.DataFrame(decisions, columns=list(DECISION_COLUMNS))


def _staged_years(staging_dir: str | Path, start_year: int, end_year: int) -> list[int]:
    """Years for which a provider actually staged a file."""
    directory = Path(staging_dir)
    return [
        year
        for year in range(start_year, end_year + 1)
        if (directory / f"raw_fundamentals_{year}.csv").exists()
    ]


def _read_staged(staging_dir: str | Path, year: int) -> pd.DataFrame:
    """Read one provider's staged CSV, or an empty frame when absent.

    A provider legitimately covers only part of the horizon, so a missing
    staged file is an empty contribution rather than an error.
    """
    path = Path(staging_dir) / f"raw_fundamentals_{year}.csv"
    if not path.exists():
        return pd.DataFrame(columns=list(STAGE1_RAW_COLUMNS))
    return pd.read_csv(path)


def resolve_stage1_era(
    *,
    legacy_dir: str | Path,
    simfin_dir: str | Path,
    output_dir: str | Path,
    reports_dir: str | Path,
    start_year: int,
    end_year: int,
) -> dict[str, object]:
    """Resolve every year in the window and publish the canonical CSVs."""
    if start_year > end_year:
        raise ValueError("start_year must be <= end_year.")

    legacy_staged = _staged_years(legacy_dir, start_year, end_year)
    simfin_staged = _staged_years(simfin_dir, start_year, end_year)
    if not legacy_staged and not simfin_staged:
        # Without this guard an empty resolve overwrites every published year
        # with a header-only CSV and still exits 0, destroying Stage 1.
        raise FileNotFoundError(
            "No staged Stage 1 files found for "
            f"{start_year}-{end_year} in either provider directory "
            f"({legacy_dir}, {simfin_dir}). Run the builders first; they write "
            "into their staging directories, and this step publishes from them."
        )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    reports = Path(reports_dir)
    reports.mkdir(parents=True, exist_ok=True)

    artifacts: dict[str, object] = {}
    per_era_rows: dict[str, int] = {era.value: 0 for era in SourceEra}
    for year in range(start_year, end_year + 1):
        resolved, decisions = resolve_era_frames(
            legacy_frame=_read_staged(legacy_dir, year),
            simfin_frame=_read_staged(simfin_dir, year),
            year=year,
        )
        year_path = output / f"raw_fundamentals_{year}.csv"
        resolved.to_csv(year_path, index=False)
        decision_path = reports / f"stage1_era_resolution_{year}.csv"
        decisions.to_csv(decision_path, index=False)

        artifacts[f"processed_{year}"] = str(year_path)
        artifacts[f"decisions_{year}"] = str(decision_path)
        if not resolved.empty:
            counts = resolved["source_era"].value_counts()
            for era_value, count in counts.items():
                per_era_rows[str(era_value)] = per_era_rows.get(
                    str(era_value), 0
                ) + int(count)

    artifacts["rows_by_era"] = per_era_rows
    return artifacts
