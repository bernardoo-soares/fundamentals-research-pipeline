"""Top-level orchestration workflow for the non-SEC baseline pipeline."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ..core.settings import get_settings
from ..steps.legacy_fundamentals import build_legacy_fundamentals
from ..steps.universe import build_sp500_current_universe


def _summary_years(df: pd.DataFrame) -> list[int]:
    """Extract sorted coverage years from a canonical quarterly DataFrame.

    Preference order:
    1. Derive years from `period_end` when available.
    2. Fall back to integer `fyearq` values otherwise.
    """
    if "period_end" in df.columns:
        period_end = pd.to_datetime(df["period_end"], errors="coerce")
        years = sorted(period_end.dropna().dt.year.astype("int64").unique().tolist())
        if years:
            return years
    return sorted(df["fyearq"].dropna().astype("int64").unique().tolist())


def run_full_pipeline(
    data_root: str | Path | None = None,
    as_of_date: date | str | None = None,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
) -> dict[str, object]:
    """Run universe and legacy canonicalization steps end-to-end.

    Args:
        data_root: Optional output root override.
        as_of_date: Universe snapshot date.
        start_date: Optional canonical period lower bound.
        end_date: Optional canonical period upper bound.

    Returns:
        Summary dictionary containing row counts, year coverage, and artifact
        paths for generated outputs.
    """
    settings = get_settings()
    root = Path(data_root) if data_root else settings.data_root
    root.mkdir(parents=True, exist_ok=True)

    # Stage 1: build current S&P 500 universe snapshot.
    universe_df = build_sp500_current_universe(
        output_dir=root,
        as_of_date=as_of_date,
        filename=settings.universe_filename,
    )

    # Stage 2: canonicalize legacy quarterly fundamentals for that universe.
    universe_path = root / settings.universe_filename
    processed_dir = root / "processed"
    canonical_df = build_legacy_fundamentals(
        universe_path=universe_path,
        output_dir=processed_dir,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "universe_rows": int(len(universe_df)),
        "canonical_rows": int(len(canonical_df)),
        "years": _summary_years(canonical_df),
        "universe_path": str(universe_path),
        "canonical_path": str(processed_dir / settings.canonical_legacy_filename),
    }
