# Trading Bot

S&P 500 universe and legacy fundamentals processing pipeline using a strict `src/` layout.

## Structure
- `src/trading_bot/config`: settings and environment configuration
- `src/trading_bot/services`: external data adapters (Wikipedia constituents)
- `src/trading_bot/pipelines`: universe build, legacy fundamentals normalization, full run
- `src/trading_bot/io`: shared infrastructure helpers
- `data/raw`, `data/processed`, `data/reports`: data zones
- `tests`: unit tests for pipelines

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Create `.env` from `.env.example` and adjust paths/timeouts if needed.

## CLI
```powershell
python -m trading_bot universe --as-of-date 2026-02-07
python -m trading_bot legacy-fundamentals --start-date 2023-01-01 --end-date 2025-12-31
python -m trading_bot full-run --as-of-date 2026-02-07 --start-date 2023-01-01 --end-date 2025-12-31
```

## Outputs
- `data/universe_current.csv`
- `data/processed/canonical_legacy_q.csv`
- `data/processed/fundamentals_q_<year>.csv`
- `data/processed/ratios_q_<year>.csv`

## Tests
```powershell
pytest
```
