# Trading Bot

S&P 500 fundamentals pipeline with a simple layered `src/` layout.

Current provider direction:
- As of `2026-03-01`, SimFin is the agreed provider for fundamentals fetching in this phase.
- The SEC pipeline remains in the repository as a legacy research path and audit reference, but it is not the production-recommended data source.
- The SimFin implementation target is captured in `resumes/RESUME_2026-03-01.md` and is not yet wired into `src/trading_bot` as a CLI stage.

## Structure
- `src/trading_bot/core`: settings, logging, exceptions
- `src/trading_bot/contracts`: current schema/config contracts; SEC contract files remain for the legacy SEC path
- `src/trading_bot/connectors`: external source adapters (currently Wikipedia + SEC; SimFin connector pending)
- `src/trading_bot/steps`: runnable pipeline steps that write artifacts
- `src/trading_bot/workflows`: multi-step orchestration flows
- `data/raw`, `data/processed`, `data/reports`: data zones
- `tests`: unit tests for connectors/steps/workflows/contracts plus SimFin smoke references

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Create `.env` from `.env.example` and adjust paths/timeouts if needed.

## Current Status
- Active implementation direction: universe-wide SimFin pipeline with strict `2 requests/second` throttling.
- Current runnable CLI in `src/trading_bot` still exposes the older universe/legacy/SEC stages only.
- SimFin validation references:
  - `tests/smoke_simfin_2023.py`
  - `tests/smoke_simfin_single_ticker.py`

## CLI
Currently implemented commands:
```powershell
python -m trading_bot universe --as-of-date 2026-02-07
python -m trading_bot legacy-fundamentals --start-date 2023-01-01 --end-date 2025-12-31
python -m trading_bot sec-map-cik --universe-path data/universe_current.csv --output-path data/reports/sec_cik_mapping.csv
python -m trading_bot sec-ingest-raw --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/companyfacts --log-path data/reports/sec_ingestion_log.csv
python -m trading_bot sec-ingest-submissions --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/submissions --log-path data/reports/sec_submissions_ingestion_log.csv
python -m trading_bot sec-build-fiscal-calendar --submissions-dir data/raw/sec/submissions --mapping-path data/reports/sec_cik_mapping.csv --output-path data/reports/sec_fiscal_calendar.csv
python -m trading_bot sec-normalize-long --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_map.yml --output-path data/processed/sec_facts_long_2023_2025.csv --start-year 2023 --end-year 2025
python -m trading_bot sec-build-processed --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_map.yml --fiscal-calendar-path data/reports/sec_fiscal_calendar.csv --sec-cik-mapping-path data/reports/sec_cik_mapping.csv --output-dir data/processed --reports-dir data/reports --start-year 2023 --end-year 2025
```

Notes:
- The SEC commands above remain callable because they still exist in code.
- They are documented here as the current runtime surface, not as the recommended fundamentals provider path.
- A SimFin CLI command has not been added yet.

Pipeline stages are currently executed command-by-command from the CLI.

## Outputs
Currently generated when the corresponding implemented CLI stage runs:
- `data/universe_current.csv`
- `data/processed/canonical_legacy_q.csv`
- `data/processed/fundamentals_q_<year>.csv`
- `data/reports/sec_cik_mapping.csv`
- `data/reports/sec_ingestion_log.csv`
- `data/raw/sec/companyfacts/*.json`
- `data/reports/sec_submissions_ingestion_log.csv`
- `data/raw/sec/submissions/*.json`
- `data/reports/sec_fiscal_calendar.csv`
- `data/processed/sec_facts_long_2023_2025.csv` (legacy SEC long format: one row per mapped `canonical_field`)
- `data/processed/processed_fundamentals_<year>.csv` (legacy SEC processed output)
- `data/reports/sec_processed_coverage_2023_2025.csv`
- `data/reports/sec_fundamentals_conflicts_2023_2025.csv`
- `data/reports/sec_fiscal_resolution_unresolved_2023_2025.csv`

Ratio computation is intentionally deferred for now.

## Tests
```powershell
python -m pytest -q
python -m compileall src
```
