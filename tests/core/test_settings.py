from __future__ import annotations

import os

from fundamentals_pipeline.core.settings import get_settings


def test_get_settings_loads_simfin_api_key_from_dotenv(tmp_path, monkeypatch) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text("SIMFIN_API_KEY = test-simfin-key\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SIMFIN_API_KEY", raising=False)
    get_settings.cache_clear()

    try:
        settings = get_settings()
        assert settings.simfin_api_key == "test-simfin-key"
    finally:
        os.environ.pop("SIMFIN_API_KEY", None)
        get_settings.cache_clear()
