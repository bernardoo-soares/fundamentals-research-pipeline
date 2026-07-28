"""Cache-first loader for the SimFin daily share-price dataset.

Mirrors `simfin_dataset_loader`: read the cached vendor CSV when present, and
fall back to the `simfin` package (which needs an API key) when it is not. One
bulk file replaces the ~500 throttled per-ticker requests the Stooq design
required, so there is no rate limiting, no retry-with-backoff and no per-ticker
failure isolation to get wrong -- the download either succeeds or it does not.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd

from ..core.exceptions import ConfigurationError
from ..core.settings import get_settings

SHAREPRICES_DATASET = "us-shareprices-daily"
SHAREPRICES_VARIANT = "daily"
SHAREPRICES_MARKET = "us"

# The vendor writes semicolon-delimited CSV.
_VENDOR_DELIMITER = ";"


class SimfinPriceConnector:
    """Load the SimFin daily share-price dataset from cache or vendor fetch."""

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
        try:
            import simfin as sf
        except ImportError as exc:  # pragma: no cover - injected in tests
            raise ConfigurationError(
                "The 'simfin' package is required when the cached share-price "
                "file is missing."
            ) from exc
        return sf

    @property
    def cache_path(self) -> Path:
        """Where the vendor CSV lives once downloaded."""
        return self.data_dir / f"{SHAREPRICES_DATASET}.csv"

    def load(self) -> pd.DataFrame:
        """Return the daily share-price frame, preferring the local cache.

        The returned frame carries the vendor's own column names; mapping them
        onto our contract is the builder's job, so a vendor rename surfaces
        there as an explicit error rather than as silently-null columns.
        """
        if self.cache_path.exists():
            return pd.read_csv(
                self.cache_path, sep=_VENDOR_DELIMITER, low_memory=False
            )

        module = self._import_module()
        if not self.api_key:
            raise ConfigurationError(
                "SIMFIN_API_KEY is required when the cached share-price file "
                f"is missing ({self.cache_path})."
            )
        module.set_data_dir(str(self.data_dir))
        module.set_api_key(self.api_key)
        frame = module.load_shareprices(
            variant=SHAREPRICES_VARIANT, market=SHAREPRICES_MARKET
        )
        # The package returns a (Ticker, Date) MultiIndex; the builder wants
        # both as ordinary columns.
        return frame.reset_index()
