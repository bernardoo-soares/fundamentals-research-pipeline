from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from trading_bot.config import get_settings


class SP500Constituents:
    def _fetch_tables(self) -> list[pd.DataFrame]:
        settings = get_settings()
        headers = {
            "User-Agent": settings.user_agent,
        }
        response = requests.get(
            settings.wiki_url,
            headers=headers,
            timeout=settings.request_timeout_seconds,
        )
        response.raise_for_status()
        return pd.read_html(StringIO(response.text))

    @staticmethod
    def _get_current_members(tables: list[pd.DataFrame]) -> list[str]:
        df = tables[0].copy()
        df.columns = df.columns.str.lower()
        if "symbol" in df.columns:
            symbols = df["symbol"]
        elif "ticker symbol" in df.columns:
            symbols = df["ticker symbol"]
        else:
            raise RuntimeError("S&P 500 table missing symbol column.")
        return [s.strip() for s in symbols.dropna().astype(str).tolist()]

    def get_sp500_current(self) -> list[str]:
        tables = self._fetch_tables()
        return self._get_current_members(tables)
