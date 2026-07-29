"""Yahoo Finance chart adapter: daily closes for one symbol.

External boundary layer (connectors/AGENTS.override.md). Uses `requests`,
already a dependency, rather than adding a vendor SDK: the endpoint is one
GET returning JSON, so an SDK would add churn and a supply-chain surface
without removing any complexity.

POLITENESS AND REPRODUCIBILITY
------------------------------
This is a public endpoint and nothing here circumvents an access control --
unlike the Stooq proof-of-work challenge, which this project deliberately
declined to solve. It is still someone else's service, so requests are
serialised, throttled to a declared rate, retried with backoff on transient
failures only, and **cached to disk**.

The cache is not just courtesy. A rebuild must produce the same numbers from
the same inputs (AGENTS.md S3.1), and a live refetch cannot promise that:
Yahoo restates and backfills. Cached raw JSON makes the build reproducible and
auditable, and `refresh=True` is the explicit opt-in to go back to the network.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path

import pandas as pd
import requests

from ..contracts.yahoo_market_schema import (
    CHART_INTERVAL,
    CHART_URL,
    DEFAULT_MAX_RETRIES,
    DEFAULT_REQUESTS_PER_SECOND,
    REQUEST_TIMEOUT_SECONDS,
    USER_AGENT,
)
from ..core.logging import get_logger

LOG = get_logger(__name__)

# Retried: the service is momentarily unavailable or rate-limiting us.
# NOT retried: 404, which means the symbol does not exist -- retrying an
# honest "no such symbol" just wastes someone else's capacity.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
SYMBOL_NOT_FOUND_STATUS = 404
RATE_LIMITED_STATUS = 429

# Backoff. A 5xx is usually momentary, but a 429 means we asked for too
# much and a short retry simply asks again -- so rate limiting gets its own
# much longer schedule, and `Retry-After` wins over both when the server
# bothers to send it.
BACKOFF_BASE_SECONDS = 1.5
RATE_LIMIT_BACKOFF_SECONDS = 20.0
MAX_BACKOFF_SECONDS = 120.0


class SymbolNotFound(LookupError):
    """Yahoo has no series for this symbol."""


class YahooUnavailable(RuntimeError):
    """The endpoint could not be reached after retrying."""


class YahooPriceClient:
    """Fetch daily closes for one symbol, cache-first."""

    def __init__(
        self,
        *,
        cache_dir: str | Path,
        session: requests.Session | None = None,
        requests_per_second: float = DEFAULT_REQUESTS_PER_SECOND,
        max_retries: int = DEFAULT_MAX_RETRIES,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = Path(cache_dir)
        self.session = session or requests.Session()
        # ASSIGN, never setdefault. `requests.Session().headers` already
        # carries "User-Agent: python-requests/x.y.z", so setdefault is a
        # silent no-op -- and Yahoo's edge answers that agent with 429.
        # Every apparent rate limit while building this connector was
        # actually this line.
        self.session.headers["User-Agent"] = USER_AGENT
        self.min_interval = 1.0 / requests_per_second if requests_per_second else 0.0
        self.max_retries = max_retries
        self._sleep = sleep
        self._last_request = 0.0

    def cache_path(self, symbol: str) -> Path:
        """Where one symbol's raw response is cached.

        `^GSPC` and `BRK-B` are not filesystem-safe as-is, so the caret and
        separator are encoded rather than stripped: stripping would collide
        `BRK-B` with `BRKB`.
        """
        safe = symbol.replace("^", "_index_").replace("/", "_slash_")
        return self.cache_dir / f"{safe}.json"

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()

    def _fetch(self, symbol: str, *, start: date, end: date) -> dict:
        params = {
            "interval": CHART_INTERVAL,
            "period1": int(
                datetime(start.year, start.month, start.day, tzinfo=UTC)
                .timestamp()
            ),
            "period2": int(
                datetime(end.year, end.month, end.day, tzinfo=UTC)
                .timestamp()
            ),
        }
        last_error = ""
        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            wait = BACKOFF_BASE_SECONDS * attempt
            try:
                response = self.session.get(
                    CHART_URL.format(symbol=symbol),
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except requests.RequestException as error:
                last_error = str(error)
            else:
                if response.status_code == SYMBOL_NOT_FOUND_STATUS:
                    raise SymbolNotFound(symbol)
                if response.status_code == 200:
                    return response.json()
                if response.status_code not in RETRYABLE_STATUS:
                    raise YahooUnavailable(
                        f"{symbol}: HTTP {response.status_code}"
                    )
                last_error = f"HTTP {response.status_code}"
                wait = self._backoff_for(response, attempt)
            if attempt < self.max_retries:
                LOG.info(
                    "Retrying %s in %.0fs (%s, attempt %d/%d)",
                    symbol,
                    wait,
                    last_error,
                    attempt,
                    self.max_retries,
                )
                self._sleep(wait)
        raise YahooUnavailable(f"{symbol}: {last_error}")

    @staticmethod
    def _backoff_for(response: requests.Response, attempt: int) -> float:
        """How long to wait before retrying this response.

        `Retry-After` is the server telling us exactly what it wants, so it
        wins. Otherwise a 429 backs off on its own much longer schedule: it
        means we asked for too much, and a 1.5-second retry just asks
        again.
        """
        header = response.headers.get("Retry-After")
        if header:
            try:
                return min(float(header), MAX_BACKOFF_SECONDS)
            except ValueError:
                pass
        if response.status_code == RATE_LIMITED_STATUS:
            return min(
                RATE_LIMIT_BACKOFF_SECONDS * (2 ** (attempt - 1)),
                MAX_BACKOFF_SECONDS,
            )
        return min(BACKOFF_BASE_SECONDS * attempt, MAX_BACKOFF_SECONDS)

    def load(
        self,
        symbol: str,
        *,
        start: date,
        end: date,
        refresh: bool = False,
    ) -> pd.DataFrame:
        """Return `(date, close)` for one symbol, reading the cache first.

        Raises `SymbolNotFound` when Yahoo has no such symbol, so a caller can
        record that as a stated exclusion rather than an empty series that
        looks like a company with no price movement.

        Rows whose close is null are dropped: Yahoo emits a null for a
        non-trading timestamp, and carrying it forward would invent a price.
        """
        path = self.cache_path(symbol)
        if path.exists() and not refresh:
            payload = json.loads(path.read_text(encoding="utf-8"))
        else:
            payload = self._fetch(symbol, start=start, end=end)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")

        return self._to_frame(symbol, payload)

    @staticmethod
    def _to_frame(symbol: str, payload: dict) -> pd.DataFrame:
        """Shape one chart response into `(date, close)`.

        `close` and not `adjclose`, deliberately: measured 2026-07-29, `close`
        is split-adjusted but not dividend-adjusted, which is the right basis
        for a price-return comparison. See `contracts/yahoo_market_schema.py`.
        """
        chart = payload.get("chart") or {}
        if chart.get("error"):
            raise SymbolNotFound(f"{symbol}: {chart['error']}")
        results = chart.get("result") or []
        if not results:
            raise SymbolNotFound(symbol)

        block = results[0]
        stamps = block.get("timestamp") or []
        quote = (block.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []
        if not stamps or not closes:
            return pd.DataFrame(columns=["date", "close"])

        frame = pd.DataFrame(
            {
                "date": [
                    datetime.fromtimestamp(s, tz=UTC).date() for s in stamps
                ],
                "close": closes,
            }
        )
        frame = frame[frame["close"].notna()]
        # Yahoo can emit two rows for one calendar day around a session
        # boundary; the later one is the settled close.
        return (
            frame.sort_values("date")
            .drop_duplicates(subset="date", keep="last")
            .reset_index(drop=True)
        )
