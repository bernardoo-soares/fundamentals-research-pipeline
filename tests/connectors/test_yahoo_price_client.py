"""Tests for the Yahoo chart adapter and its symbol mapping.

No network: the session is faked. The behaviours under test are the ones that
decide whether a comparison is honest — a missing symbol must be
distinguishable from a transport failure, and an alias must never quietly
become a different security.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import requests

from fundamentals_pipeline.connectors.yahoo_price_client import (
    RATE_LIMITED_STATUS,
    SymbolNotFound,
    YahooPriceClient,
    YahooUnavailable,
)
from fundamentals_pipeline.contracts.yahoo_market_schema import (
    UNRESOLVED_SYMBOLS,
    VERIFIED_RENAMES,
    SymbolAliasRejected,
    to_yahoo_symbol,
    validate_renames,
)

START, END = date(2024, 1, 1), date(2024, 1, 5)


class FakeResponse:
    def __init__(self, status=200, payload=None, headers=None):
        self.status_code = status
        self._payload = payload or {}
        self.headers = headers or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeSession:
    """Returns a queued series of responses and records the calls."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.headers = {}
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        if not self._responses:
            raise AssertionError("more requests than queued responses")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _chart(closes, stamps=None):
    stamps = stamps or [1704153600 + 86400 * i for i in range(len(closes))]
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "timestamp": stamps,
                    "indicators": {"quote": [{"close": closes}]},
                    "meta": {"symbol": "TEST"},
                }
            ],
        }
    }


def _client(tmp_path, responses, **kwargs):
    return YahooPriceClient(
        cache_dir=tmp_path,
        session=FakeSession(responses),
        sleep=lambda _: None,
        **kwargs,
    )


# --- Shaping ----------------------------------------------------------------


def test_a_chart_response_becomes_date_close(tmp_path):
    client = _client(tmp_path, [FakeResponse(payload=_chart([10.0, 11.0, 12.0]))])
    frame = client.load("TEST", start=START, end=END)
    assert list(frame.columns) == ["date", "close"]
    assert frame["close"].tolist() == [10.0, 11.0, 12.0]


def test_null_closes_are_dropped_not_carried_forward(tmp_path):
    """Yahoo emits a null for a non-trading stamp; filling it invents a price."""
    client = _client(tmp_path, [FakeResponse(payload=_chart([10.0, None, 12.0]))])
    frame = client.load("TEST", start=START, end=END)
    assert frame["close"].tolist() == [10.0, 12.0]


def test_two_rows_for_one_day_keep_the_settled_close(tmp_path):
    stamps = [1704153600, 1704153600 + 3600, 1704240000]
    client = _client(
        tmp_path, [FakeResponse(payload=_chart([10.0, 10.5, 11.0], stamps))]
    )
    frame = client.load("TEST", start=START, end=END)
    assert len(frame) == 2
    assert frame["close"].tolist() == [10.5, 11.0]


def test_an_empty_series_is_empty_not_an_error(tmp_path):
    client = _client(tmp_path, [FakeResponse(payload=_chart([]))])
    assert client.load("TEST", start=START, end=END).empty


# --- Missing symbol vs transport failure ------------------------------------


def test_a_404_is_symbol_not_found_and_is_not_retried(tmp_path):
    """Retrying an honest 'no such symbol' just wastes someone's capacity."""
    session = FakeSession([FakeResponse(status=404)])
    client = YahooPriceClient(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, max_retries=4
    )
    with pytest.raises(SymbolNotFound):
        client.load("NOPE", start=START, end=END)
    assert len(session.calls) == 1


def test_an_error_body_is_symbol_not_found(tmp_path):
    payload = {"chart": {"error": {"code": "Not Found"}, "result": None}}
    client = _client(tmp_path, [FakeResponse(payload=payload)])
    with pytest.raises(SymbolNotFound):
        client.load("NOPE", start=START, end=END)


def test_rate_limiting_is_retried_then_reported(tmp_path):
    session = FakeSession([FakeResponse(status=RATE_LIMITED_STATUS)] * 3)
    client = YahooPriceClient(
        cache_dir=tmp_path, session=session, sleep=lambda _: None, max_retries=3
    )
    with pytest.raises(YahooUnavailable, match="429"):
        client.load("TEST", start=START, end=END)
    assert len(session.calls) == 3


def test_a_transient_failure_then_success_succeeds(tmp_path):
    client = _client(
        tmp_path,
        [FakeResponse(status=503), FakeResponse(payload=_chart([5.0]))],
        max_retries=3,
    )
    assert client.load("TEST", start=START, end=END)["close"].tolist() == [5.0]


def test_a_network_error_is_retried(tmp_path):
    client = _client(
        tmp_path,
        [requests.ConnectionError("boom"), FakeResponse(payload=_chart([7.0]))],
        max_retries=3,
    )
    assert client.load("TEST", start=START, end=END)["close"].tolist() == [7.0]


def test_retry_after_is_honoured_over_the_default_backoff():
    waits: list[float] = []
    client = YahooPriceClient(
        cache_dir=".",
        session=FakeSession([]),
        sleep=waits.append,
    )
    response = FakeResponse(status=RATE_LIMITED_STATUS, headers={"Retry-After": "7"})
    assert client._backoff_for(response, attempt=1) == 7.0


def test_rate_limiting_backs_off_far_longer_than_a_5xx():
    """A 429 means we asked for too much; a 1.5s retry just asks again."""
    client = YahooPriceClient(cache_dir=".", session=FakeSession([]))
    limited = client._backoff_for(FakeResponse(status=RATE_LIMITED_STATUS), 1)
    server_error = client._backoff_for(FakeResponse(status=503), 1)
    assert limited > server_error * 5


# --- Cache ------------------------------------------------------------------


def test_the_second_call_is_served_from_cache(tmp_path):
    session = FakeSession([FakeResponse(payload=_chart([1.0, 2.0]))])
    client = YahooPriceClient(
        cache_dir=tmp_path, session=session, sleep=lambda _: None
    )
    first = client.load("TEST", start=START, end=END)
    second = client.load("TEST", start=START, end=END)
    assert len(session.calls) == 1
    assert first.equals(second)


def test_refresh_goes_back_to_the_network(tmp_path):
    session = FakeSession(
        [FakeResponse(payload=_chart([1.0])), FakeResponse(payload=_chart([9.0]))]
    )
    client = YahooPriceClient(
        cache_dir=tmp_path, session=session, sleep=lambda _: None
    )
    client.load("TEST", start=START, end=END)
    refreshed = client.load("TEST", start=START, end=END, refresh=True)
    assert len(session.calls) == 2
    assert refreshed["close"].tolist() == [9.0]


def test_index_and_class_symbols_get_distinct_cache_files(tmp_path):
    """Stripping the separator would collide BRK-B with BRKB."""
    client = YahooPriceClient(cache_dir=tmp_path, session=FakeSession([]))
    paths = {
        client.cache_path(s).name for s in ("^GSPC", "BRK-B", "BRKB", "GSPC")
    }
    assert len(paths) == 4


# --- Symbol mapping ---------------------------------------------------------


def test_most_tickers_map_unchanged():
    assert to_yahoo_symbol("AAPL") == "AAPL"
    assert to_yahoo_symbol("  ko  ") == "KO"


def test_the_class_separator_is_swapped():
    """Measured: this warehouse writes BRK.B, Yahoo writes BRK-B."""
    assert to_yahoo_symbol("BRK.B") == "BRK-B"


def test_a_verified_rename_is_applied():
    assert to_yahoo_symbol("BK") == "BNY"


def test_an_unresolved_symbol_maps_to_none_rather_than_a_guess():
    assert to_yahoo_symbol("HOLX") is None
    assert "HOLX" in UNRESOLVED_SYMBOLS


def test_every_rename_records_how_it_was_verified():
    for source, (target, evidence) in VERIFIED_RENAMES.items():
        assert evidence.strip(), f"{source} -> {target} has no evidence"


def test_a_share_class_alias_is_rejected():
    """The trap this guard exists for: BRK.B -> BRK-A 'resolves' and is wrong."""
    with pytest.raises(SymbolAliasRejected, match="share class"):
        validate_renames({"BRK.B": ("BRK-A", "it resolves")})


def test_an_unevidenced_rename_is_rejected():
    with pytest.raises(SymbolAliasRejected, match="verified"):
        validate_renames({"OLD": ("NEW", "   ")})


def test_the_shipped_rename_table_passes_its_own_guard():
    validate_renames()


def test_the_user_agent_is_assigned_not_defaulted():
    """`Session.headers` already holds "python-requests/x.y.z", so
    `setdefault` is a silent no-op -- and Yahoo's edge answers that agent with
    429. Every apparent rate limit while building this connector was that.
    """
    from fundamentals_pipeline.contracts.yahoo_market_schema import USER_AGENT

    session = requests.Session()
    assert "python-requests" in session.headers["User-Agent"]
    YahooPriceClient(cache_dir=".", session=session)
    assert session.headers["User-Agent"] == USER_AGENT
    assert "python-requests" not in session.headers["User-Agent"]
