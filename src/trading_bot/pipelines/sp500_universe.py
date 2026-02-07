from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from trading_bot.services import SP500Constituents


def _normalize_ticker(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text:
        return None
    return text


def _coerce_date(value: date | str | None) -> date:
    if value is None:
        return date.today()
    if isinstance(value, date):
        return value
    return pd.to_datetime(value).date()


def build_sp500_current_universe(
    output_dir: str | Path = "data",
    as_of_date: date | str | None = None,
    filename: str = "universe_current.csv",
) -> pd.DataFrame:
    as_of_date = _coerce_date(as_of_date)

    scraper = SP500Constituents()
    members = scraper.get_sp500_current()

    normalized = sorted(
        {
            ticker
            for ticker in (_normalize_ticker(member) for member in members)
            if ticker is not None
        }
    )

    df_out = pd.DataFrame({"ticker": normalized})
    df_out.insert(0, "as_of_date", as_of_date.isoformat())
    df_out.insert(1, "year", as_of_date.year)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    df_out.to_csv(output_path / filename, index=False)
    return df_out
