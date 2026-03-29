"""Cache-first SimFin connector for raw fundamentals statement datasets.

This connector prefers reading the local SimFin cache directly. If a required
dataset file is missing, it falls back to the `simfin` package loaders, which
will populate the configured cache directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import pandas as pd

from ..core.exceptions import ConfigurationError, DataSourceError
from ..core.settings import get_settings


SIMFIN_QUARTERLY_DATASETS: dict[str, dict[str, str]] = {
    "income_general": {
        "filename": "us-income-quarterly.csv",
        "loader_name": "load_income",
        "variant": "quarterly",
    },
    "balance_general": {
        "filename": "us-balance-quarterly.csv",
        "loader_name": "load_balance",
        "variant": "quarterly",
    },
    "cashflow_general": {
        "filename": "us-cashflow-quarterly.csv",
        "loader_name": "load_cashflow",
        "variant": "quarterly",
    },
    "income_banks": {
        "filename": "us-income-banks-quarterly.csv",
        "loader_name": "load_income_banks",
        "variant": "quarterly",
    },
    "balance_banks": {
        "filename": "us-balance-banks-quarterly.csv",
        "loader_name": "load_balance_banks",
        "variant": "quarterly",
    },
    "cashflow_banks": {
        "filename": "us-cashflow-banks-quarterly.csv",
        "loader_name": "load_cashflow_banks",
        "variant": "quarterly",
    },
    "income_insurance": {
        "filename": "us-income-insurance-quarterly.csv",
        "loader_name": "load_income_insurance",
        "variant": "quarterly",
    },
    "balance_insurance": {
        "filename": "us-balance-insurance-quarterly.csv",
        "loader_name": "load_balance_insurance",
        "variant": "quarterly",
    },
    "cashflow_insurance": {
        "filename": "us-cashflow-insurance-quarterly.csv",
        "loader_name": "load_cashflow_insurance",
        "variant": "quarterly",
    },
}

SIMFIN_ANNUAL_CASHFLOW_DATASETS: dict[str, dict[str, str]] = {
    "cashflow_general_annual": {
        "filename": "us-cashflow-annual.csv",
        "loader_name": "load_cashflow",
        "variant": "annual",
    },
    "cashflow_banks_annual": {
        "filename": "us-cashflow-banks-annual.csv",
        "loader_name": "load_cashflow_banks",
        "variant": "annual",
    },
    "cashflow_insurance_annual": {
        "filename": "us-cashflow-insurance-annual.csv",
        "loader_name": "load_cashflow_insurance",
        "variant": "annual",
    },
}

SIMFIN_DATASETS: dict[str, dict[str, str]] = {
    **SIMFIN_QUARTERLY_DATASETS,
    **SIMFIN_ANNUAL_CASHFLOW_DATASETS,
}


class SimfinConnector:
    """Load required SimFin datasets from cache or via package fetch."""

    def __init__(
        self,
        *,
        data_dir: str | Path | None = None,
        api_key: str | None = None,
        import_module: Callable[[], Any] | None = None,
    ) -> None:
        settings = get_settings()
        self.data_dir = Path(data_dir) if data_dir else settings.simfin_data_dir
        self.api_key = api_key if api_key is not None else settings.simfin_api_key
        self._import_module = import_module or self._default_import_module

    @staticmethod
    def _default_import_module() -> Any:
        """Import and return the `simfin` module lazily."""
        try:
            import simfin as sf
        except ImportError as exc:  # pragma: no cover - guarded in tests via injection
            raise ConfigurationError(
                "The 'simfin' package is required when SimFin cache files are missing."
            ) from exc
        return sf

    @staticmethod
    def _read_cached_csv(path: Path) -> pd.DataFrame:
        """Read a cached SimFin CSV file using the vendor's semicolon delimiter."""
        return pd.read_csv(path, sep=";", low_memory=False)

    def _configure_module(self, module: Any) -> None:
        """Configure SimFin package state before dataset loading."""
        if not self.api_key:
            raise ConfigurationError(
                "SIMFIN_API_KEY is required when SimFin cache files are missing."
            )

        self.data_dir.mkdir(parents=True, exist_ok=True)
        module.set_api_key(self.api_key)
        module.set_data_dir(str(self.data_dir))

    def load_dataset(self, dataset_name: str) -> pd.DataFrame:
        """Load one named SimFin dataset."""
        if dataset_name not in SIMFIN_DATASETS:
            raise ValueError(f"Unsupported SimFin dataset: {dataset_name}")

        metadata = SIMFIN_DATASETS[dataset_name]
        dataset_path = self.data_dir / metadata["filename"]
        if dataset_path.exists():
            return self._read_cached_csv(dataset_path)

        module = self._import_module()
        self._configure_module(module)
        loader = getattr(module, metadata["loader_name"], None)
        if loader is None:
            raise ConfigurationError(
                f"SimFin module missing expected loader: {metadata['loader_name']}"
            )

        try:
            frame = loader(variant=metadata["variant"], market="us")
        except Exception as exc:  # pragma: no cover - defensive wrapper
            raise DataSourceError(
                f"SimFin dataset load failed for {dataset_name}."
            ) from exc

        if dataset_path.exists():
            return self._read_cached_csv(dataset_path)
        if isinstance(frame, pd.DataFrame):
            return frame.reset_index()

        raise DataSourceError(
            f"SimFin dataset load for {dataset_name} returned no readable DataFrame."
        )

    def load_quarterly_datasets(self) -> dict[str, pd.DataFrame]:
        """Load all quarterly datasets required by the raw fundamentals builder."""
        return {
            dataset_name: self.load_dataset(dataset_name)
            for dataset_name in SIMFIN_QUARTERLY_DATASETS
        }

    def load_raw_fundamentals_datasets(self) -> dict[str, pd.DataFrame]:
        """Load quarterly statements plus annual cashflow support datasets."""
        return {
            dataset_name: self.load_dataset(dataset_name)
            for dataset_name in SIMFIN_DATASETS
        }
