from __future__ import annotations

import pandas as pd
import pytest

from fundamentals_pipeline.connectors.simfin_dataset_loader import SimfinConnector
from fundamentals_pipeline.core.exceptions import ConfigurationError


def test_simfin_connector_reads_cached_csv_without_importing_package(tmp_path) -> None:
    cache_dir = tmp_path / "simfin_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / "us-income-quarterly.csv"
    pd.DataFrame(
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Revenue": 100.0,
            }
        ]
    ).to_csv(cached_path, sep=";", index=False)

    connector = SimfinConnector(
        data_dir=cache_dir,
        import_module=lambda: (_ for _ in ()).throw(AssertionError("import should not be called")),
    )
    frame = connector.load_dataset("income_general")

    assert list(frame.columns) == ["Ticker", "Fiscal Year", "Fiscal Period", "Revenue"]
    assert frame.loc[0, "Ticker"] == "AAPL"


def test_simfin_connector_refreshes_quarterly_cache_when_requested(tmp_path) -> None:
    cache_dir = tmp_path / "simfin_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached_path = cache_dir / "us-income-quarterly.csv"
    pd.DataFrame(
        [
            {
                "Ticker": "AAPL",
                "Fiscal Year": 2023,
                "Fiscal Period": "Q1",
                "Revenue": 100.0,
            }
        ]
    ).to_csv(cached_path, sep=";", index=False)

    class FakeSimfinModule:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, int]] = []

        def set_api_key(self, _value: str) -> None:
            return None

        def set_data_dir(self, _value: str) -> None:
            return None

        def load_income(self, *, variant: str, market: str, refresh_days: int):
            self.calls.append((variant, market, refresh_days))
            return pd.DataFrame(
                [
                    {
                        "Ticker": "AAPL",
                        "Fiscal Year": 2025,
                        "Fiscal Period": "Q1",
                        "Revenue": 150.0,
                    }
                ]
            )

    fake_module = FakeSimfinModule()
    connector = SimfinConnector(
        data_dir=cache_dir,
        api_key="test-key",
        refresh_quarterly=True,
        quarterly_refresh_days=0,
        import_module=lambda: fake_module,
    )

    frame = connector.load_dataset("income_general")

    assert fake_module.calls == [("quarterly", "us", 0)]
    assert frame.loc[0, "Fiscal Year"] == 2025


def test_simfin_connector_uses_annual_variant_for_annual_cashflow_dataset(tmp_path) -> None:
    class FakeSimfinModule:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str]] = []

        def set_api_key(self, _value: str) -> None:
            return None

        def set_data_dir(self, _value: str) -> None:
            return None

        def load_cashflow(self, *, variant: str, market: str):
            self.calls.append((variant, market))
            return pd.DataFrame(
                [
                    {
                        "Ticker": "AAPL",
                        "Fiscal Year": 2023,
                        "Change in Fixed Assets & Intangibles": -36.0,
                    }
                ]
            )

    fake_module = FakeSimfinModule()
    connector = SimfinConnector(
        data_dir=tmp_path / "missing_cache",
        api_key="test-key",
        import_module=lambda: fake_module,
    )

    frame = connector.load_dataset("cashflow_general_annual")

    assert fake_module.calls == [("annual", "us")]
    assert frame.loc[0, "Ticker"] == "AAPL"


def test_simfin_connector_requires_api_key_when_cache_is_missing(tmp_path) -> None:
    connector = SimfinConnector(
        data_dir=tmp_path / "missing_cache",
        api_key="",
        import_module=lambda: object(),
    )

    with pytest.raises(ConfigurationError, match="SIMFIN_API_KEY"):
        connector.load_dataset("income_general")
