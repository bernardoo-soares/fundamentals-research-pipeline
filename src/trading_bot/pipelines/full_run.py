from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from trading_bot.config import get_settings
from trading_bot.pipelines.legacy_fundamentals import build_legacy_fundamentals
from trading_bot.pipelines.sp500_universe import build_sp500_current_universe


def _summary_years(df: pd.DataFrame) -> list[int]:
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
    settings = get_settings()
    root = Path(data_root) if data_root else settings.data_root
    root.mkdir(parents=True, exist_ok=True)

    universe_df = build_sp500_current_universe(
        output_dir=root,
        as_of_date=as_of_date,
        filename=settings.universe_filename,
    )

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
