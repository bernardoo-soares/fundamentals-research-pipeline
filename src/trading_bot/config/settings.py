from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


@dataclass(frozen=True)
class AppSettings:
    wiki_url: str
    request_timeout_seconds: int
    user_agent: str
    log_level: str
    data_root: Path
    raw_data_dir: Path
    processed_data_dir: Path
    reports_data_dir: Path
    legacy_fundamentals_dir: Path
    universe_filename: str
    canonical_legacy_filename: str


@lru_cache(maxsize=1)
def get_settings() -> AppSettings:
    data_root = Path(os.getenv("DATA_ROOT", "data"))
    raw_data_dir = Path(os.getenv("RAW_DATA_DIR", str(data_root / "raw")))
    processed_data_dir = Path(
        os.getenv("PROCESSED_DATA_DIR", str(data_root / "processed"))
    )
    reports_data_dir = Path(
        os.getenv("REPORTS_DATA_DIR", str(data_root / "reports"))
    )
    legacy_fundamentals_dir = Path(
        os.getenv(
            "LEGACY_FUNDAMENTALS_DIR",
            str(data_root / "raw" / "Processed-Fundamentals"),
        )
    )
    return AppSettings(
        wiki_url=os.getenv(
            "WIKI_URL",
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        ),
        request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 30),
        user_agent=os.getenv(
            "USER_AGENT",
            "TradingBot/0.2 (research workflow; contact: local-user)",
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        data_root=data_root,
        raw_data_dir=raw_data_dir,
        processed_data_dir=processed_data_dir,
        reports_data_dir=reports_data_dir,
        legacy_fundamentals_dir=legacy_fundamentals_dir,
        universe_filename=os.getenv("UNIVERSE_FILENAME", "universe_current.csv"),
        canonical_legacy_filename=os.getenv(
            "CANONICAL_LEGACY_FILENAME",
            "canonical_legacy_q.csv",
        ),
    )
