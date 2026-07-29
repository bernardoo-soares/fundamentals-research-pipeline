"""Wikipedia-based adapter for current S&P 500 constituents."""

from __future__ import annotations

from io import StringIO

import pandas as pd
import requests

from ..contracts.company_profile_schema import WIKIPEDIA_COLUMN_MAP
from ..core.settings import get_settings


class SP500Constituents:
    """Adapter that fetches and parses the current S&P 500 members table."""

    def _fetch_tables(self) -> list[pd.DataFrame]:
        """Download Wikipedia page HTML and parse all tabular blocks.

        Returns:
            List of DataFrames extracted by `pandas.read_html`.
        """
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
        """Extract ticker symbols from the expected first S&P 500 table.

        Args:
            tables: Parsed tables from Wikipedia page content.

        Returns:
            List of ticker symbols as raw strings.

        Raises:
            RuntimeError: If expected symbol column is not present.
        """
        df = tables[0].copy()
        df.columns = df.columns.str.lower()

        # Wikipedia column names vary slightly, so support both common variants.
        if "symbol" in df.columns:
            symbols = df["symbol"]
        elif "ticker symbol" in df.columns:
            symbols = df["ticker symbol"]
        else:
            raise RuntimeError("S&P 500 table missing symbol column.")

        return [s.strip() for s in symbols.dropna().astype(str).tolist()]

    def get_sp500_current(self) -> list[str]:
        """Fetch and return the current S&P 500 ticker list."""
        tables = self._fetch_tables()
        return self._get_current_members(tables)

    @staticmethod
    def _get_profile(tables: list[pd.DataFrame]) -> pd.DataFrame:
        """Extract name and GICS classification from the constituents table.

        The same table `_get_current_members` reads. Every column but the
        symbol used to be discarded one line after parsing, which is why the
        warehouse held no company name or sector until 2026-07-29.

        Columns are selected by declared name, never by position: the table's
        column order has changed before, and a positional read would silently
        put headquarters into the sector field.
        """
        df = tables[0].copy()
        missing = [c for c in WIKIPEDIA_COLUMN_MAP if c not in df.columns]
        if missing:
            raise RuntimeError(
                f"S&P 500 table is missing expected column(s): {missing}. "
                "The page layout changed; update WIKIPEDIA_COLUMN_MAP."
            )
        out = df[list(WIKIPEDIA_COLUMN_MAP)].rename(columns=WIKIPEDIA_COLUMN_MAP)
        for column in ("ticker", "company_name", "sector", "sub_industry"):
            out[column] = out[column].astype(str).str.strip()
        return out

    def get_sp500_profile(self) -> pd.DataFrame:
        """Fetch current constituents with name, sector and sub-industry.

        Current membership and current classification -- not point-in-time.
        See `contracts/company_profile_schema.py` for what this may and may not
        be used for.
        """
        return self._get_profile(self._fetch_tables())
