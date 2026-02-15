"""SEC adapters for reference mapping and companyfacts ingestion."""

from __future__ import annotations

import random
import time
from collections import defaultdict
from typing import Any, Iterable

import requests

from ..core.exceptions import SecRateLimitError, SecRequestError
from ..core.logging import get_logger


# Status codes that should trigger exponential backoff and retry behavior.
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
LOG = get_logger(__name__)


class SecClient:
    """HTTP client for SEC endpoints with throttling and retry semantics.

    The SEC recommends controlled request rates and descriptive user agents.
    This client centralizes those concerns and tracks request diagnostics for
    ingestion logging.
    """

    def __init__(
        self,
        *,
        base_url: str,
        user_agent: str,
        timeout_seconds: int,
        rate_limit_per_second: float,
        max_retries: int,
        session: requests.Session | None = None,
    ) -> None:
        """Initialize the SEC client and validate retry/rate-limit settings."""
        if rate_limit_per_second <= 0:
            raise ValueError("rate_limit_per_second must be greater than 0.")
        if max_retries < 0:
            raise ValueError("max_retries must be >= 0.")

        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_second = rate_limit_per_second
        self.max_retries = max_retries
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json"}
        )

        # Monotonic timestamp used to enforce minimum spacing between requests.
        self._next_allowed_request_ts = 0.0
        self.last_status_code: int | None = None
        self.last_attempts: int = 0

    def _throttle(self) -> None:
        """Block until the next request is allowed by the configured rate limit."""
        now = time.monotonic()
        if now < self._next_allowed_request_ts:
            time.sleep(self._next_allowed_request_ts - now)
        self._next_allowed_request_ts = time.monotonic() + (
            1.0 / self.rate_limit_per_second
        )

    def _request_json(self, url: str) -> dict[str, Any]:
        """Issue a GET request with retry/backoff and return parsed JSON.

        Args:
            url: Fully-qualified SEC endpoint URL.

        Returns:
            Decoded JSON payload.

        Raises:
            SecRequestError: When request attempts are exhausted.
            SecRateLimitError: When retryable status persists after retries.
        """
        last_error: Exception | None = None

        # `max_retries + 1` includes the initial request attempt.
        for attempt in range(1, self.max_retries + 2):
            self._throttle()
            LOG.debug("SEC request attempt %d/%d: %s", attempt, self.max_retries + 1, url)
            try:
                response = self.session.get(url, timeout=self.timeout_seconds)
                self.last_status_code = response.status_code
                LOG.debug(
                    "SEC response received: status=%s attempt=%d url=%s",
                    response.status_code,
                    attempt,
                    url,
                )

                if response.status_code in RETRYABLE_STATUS_CODES:
                    last_error = SecRateLimitError(
                        f"Retryable SEC response {response.status_code} for {url}",
                        status_code=response.status_code,
                        attempts=attempt,
                        url=url,
                    )
                    if attempt <= self.max_retries:
                        # Exponential backoff with jitter prevents retry bursts.
                        backoff_seconds = (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                        LOG.warning(
                            "Retryable SEC response %s on attempt %d. Backing off %.2fs before retry. url=%s",
                            response.status_code,
                            attempt,
                            backoff_seconds,
                            url,
                        )
                        time.sleep(backoff_seconds)
                        continue
                    raise last_error

                response.raise_for_status()
                payload = response.json()
                self.last_attempts = attempt
                LOG.debug("SEC request succeeded on attempt %d: %s", attempt, url)
                return payload
            except requests.RequestException as exc:
                last_error = exc
                self.last_status_code = getattr(exc.response, "status_code", None)

                # Non-retryable HTTP failures should fail fast.
                if (
                    self.last_status_code is not None
                    and self.last_status_code not in RETRYABLE_STATUS_CODES
                ):
                    self.last_attempts = attempt
                    LOG.error(
                        "Non-retryable SEC response status=%s attempt=%d url=%s",
                        self.last_status_code,
                        attempt,
                        url,
                    )
                    raise SecRequestError(
                        f"Non-retryable SEC response {self.last_status_code} for {url}",
                        status_code=self.last_status_code,
                        attempts=attempt,
                        url=url,
                    ) from exc

                if attempt <= self.max_retries:
                    backoff_seconds = (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                    LOG.warning(
                        "Retryable SEC request error on attempt %d. Backing off %.2fs before retry. status=%s url=%s",
                        attempt,
                        backoff_seconds,
                        self.last_status_code,
                        url,
                    )
                    time.sleep(backoff_seconds)
                    continue
                break

        self.last_attempts = self.max_retries + 1
        if isinstance(last_error, SecRequestError):
            raise last_error

        raise SecRequestError(
            f"SEC request failed for {url}: {last_error}",
            status_code=self.last_status_code,
            attempts=self.last_attempts,
            url=url,
        ) from last_error

    def fetch_companyfacts(self, cik: str) -> dict[str, Any]:
        """Fetch SEC companyfacts JSON payload for a single CIK.

        Args:
            cik: Company CIK, with or without zero-padding.

        Returns:
            Parsed SEC companyfacts JSON payload.
        """
        cik10 = str(cik).zfill(10)
        url = f"{self.base_url}/api/xbrl/companyfacts/CIK{cik10}.json"
        return self._request_json(url)

    def fetch_submissions(self, cik: str) -> dict[str, Any]:
        """Fetch SEC submissions JSON payload for a single CIK.

        Args:
            cik: Company CIK, with or without zero-padding.

        Returns:
            Parsed SEC submissions JSON payload.
        """
        cik10 = str(cik).zfill(10)
        url = f"{self.base_url}/submissions/CIK{cik10}.json"
        return self._request_json(url)


def normalize_ticker(symbol: str) -> str:
    """Normalize ticker symbols to a common uppercase SEC-friendly format."""
    text = str(symbol).strip().upper().replace(" ", "")
    return text.replace("/", "-")


def _ticker_aliases(symbol: str) -> set[str]:
    """Build lookup aliases to handle `.` and `-` ticker variants."""
    normalized = normalize_ticker(symbol)
    aliases = {normalized}
    aliases.add(normalized.replace(".", "-"))
    aliases.add(normalized.replace("-", "."))
    return {value for value in aliases if value}


def fetch_sec_ticker_reference(
    session: requests.Session,
    url: str,
    timeout: int,
) -> list[dict[str, str]]:
    """Fetch SEC ticker reference feed and normalize row keys.

    Args:
        session: Requests session preconfigured with user agent.
        url: SEC ticker reference endpoint.
        timeout: Request timeout in seconds.

    Returns:
        List of normalized mapping rows with keys: ticker, cik, name, exchange.
    """
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    payload = response.json()

    if isinstance(payload, dict):

        def _sort_key(value: str) -> tuple[int, str]:
            """Sort numeric JSON keys in natural numeric order when possible."""
            text = str(value)
            return (0, f"{int(text):012d}") if text.isdigit() else (1, text)

        rows = [payload[key] for key in sorted(payload.keys(), key=_sort_key)]
    elif isinstance(payload, list):
        rows = payload
    else:
        raise ValueError("Unexpected SEC ticker reference payload type.")

    out: list[dict[str, str]] = []
    for row in rows:
        out.append(
            {
                "ticker": str(row.get("ticker", "")).strip(),
                "cik": str(row.get("cik_str", "")).strip(),
                "name": str(row.get("title", row.get("name", ""))).strip(),
                "exchange": str(row.get("exchange", "")).strip(),
            }
        )
    return out


def build_ticker_to_cik_index(rows: list[dict[str, str]]) -> dict[str, str]:
    """Create a one-to-one normalized ticker to CIK dictionary."""
    index: dict[str, str] = {}
    for row in rows:
        ticker = normalize_ticker(row.get("ticker", ""))
        cik = str(row.get("cik", "")).strip()
        if not ticker or not cik:
            continue
        index[ticker] = cik.zfill(10)
    return index


def build_ticker_reference_lookup(
    rows: list[dict[str, str]],
) -> dict[str, list[dict[str, str]]]:
    """Create alias-aware lookup mapping ticker variants to SEC candidates.

    Returns a one-to-many structure because some tickers can map to multiple
    CIK candidates and must be classified as ambiguous downstream.
    """
    lookup: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        ticker = str(row.get("ticker", "")).strip()
        cik = str(row.get("cik", "")).strip()
        if not ticker or not cik:
            continue

        normalized_row = {
            "ticker": normalize_ticker(ticker),
            "cik": cik.zfill(10),
            "name": str(row.get("name", "")).strip(),
            "exchange": str(row.get("exchange", "")).strip(),
        }
        for alias in _ticker_aliases(ticker):
            lookup[alias].append(normalized_row)

    return dict(lookup)


def iter_companyfacts_rows(
    payload: dict[str, Any],
    *,
    ticker: str,
    cik: str,
) -> Iterable[dict[str, Any]]:
    """Flatten SEC companyfacts payload into observation-level fact rows.

    Args:
        payload: Raw SEC companyfacts JSON payload.
        ticker: Ticker associated with payload file.
        cik: CIK associated with payload file.

    Yields:
        Normalized dictionaries with taxonomy, tag, unit, value, period, and
        filing metadata fields.
    """
    facts = payload.get("facts", {})
    cik10 = str(cik).zfill(10)
    ticker = str(ticker).strip().upper()

    for taxonomy, taxonomy_block in facts.items():
        if not isinstance(taxonomy_block, dict):
            continue
        for tag, tag_block in taxonomy_block.items():
            if not isinstance(tag_block, dict):
                continue
            units = tag_block.get("units", {})
            if not isinstance(units, dict):
                continue
            for unit, observations in units.items():
                if not isinstance(observations, list):
                    continue
                for obs in observations:
                    if not isinstance(obs, dict):
                        continue
                    yield {
                        "ticker": ticker,
                        "cik": cik10,
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "value": obs.get("val"),
                        "start": obs.get("start"),
                        "end": obs.get("end"),
                        "fy": obs.get("fy"),
                        "fp": obs.get("fp"),
                        "form": obs.get("form"),
                        "filed": obs.get("filed"),
                        "accn": obs.get("accn"),
                        "frame": obs.get("frame"),
                    }
