# Trading Bot

S&P 500 fundamentals pipeline with a simple layered `src/` layout.

Current provider direction:
- As of `2026-03-01`, SimFin is the agreed provider for fundamentals fetching in this phase.
- The SEC pipeline remains in the repository as a legacy research path and audit reference, but it is not the production-recommended data source.
- The current SimFin raw fundamentals implementation is cache-first by default, with optional quarterly refresh and validated ticker aliasing for provider mismatches.

## Structure
- `src/trading_bot/core`: settings, logging, exceptions
- `src/trading_bot/contracts`: current schema/config contracts; SEC contract files remain for the legacy SEC path
- `src/trading_bot/connectors`: external source adapters (currently Wikipedia, SEC, and SimFin cache/package loading)
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
- Active implementation direction: SimFin-backed raw fundamentals for `2023-2025`.
- Current runnable CLI now includes a dedicated `simfin-raw-fundamentals` command for the raw fundamentals export path.
- SimFin validation references:
  - `tests/smoke_simfin_2023.py`
  - `tests/smoke_simfin_single_ticker.py`
- Production SimFin mapping reference:
  - `specs/SIMFIN_STAGE1_MAPPING.md`

## CLI
Currently implemented commands:
```powershell
python -m trading_bot universe --as-of-date 2026-02-07
python -m trading_bot legacy-fundamentals --start-date 2023-01-01 --end-date 2025-12-31
python -m trading_bot legacy-raw-stage1 --raw-dir data/raw/Processed-Fundamentals --output-dir data/processed --reports-dir data/reports --start-year 2006 --end-year 2023
python -m trading_bot simfin-raw-fundamentals --universe-path data/universe_current.csv --output-dir data/processed --reports-dir data/reports --start-year 2023 --end-year 2025
python -m trading_bot simfin-raw-fundamentals --universe-path data/universe_current.csv --output-dir data/processed --reports-dir data/reports --start-year 2023 --end-year 2025 --refresh-quarterly-cache --quarterly-refresh-days 0
python -m trading_bot stage1-extension-audit --processed-dir data/processed --reports-dir data/reports --start-year 2006 --end-year 2025
python -m trading_bot sec-map-cik --universe-path data/universe_current.csv --output-path data/reports/sec_cik_mapping.csv
python -m trading_bot sec-ingest-raw --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/companyfacts --log-path data/reports/sec_ingestion_log.csv
python -m trading_bot sec-ingest-submissions --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/submissions --log-path data/reports/sec_submissions_ingestion_log.csv
python -m trading_bot sec-build-fiscal-calendar --submissions-dir data/raw/sec/submissions --mapping-path data/reports/sec_cik_mapping.csv --output-path data/reports/sec_fiscal_calendar.csv
python -m trading_bot sec-normalize-long --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_mapping.yml --output-path data/processed/sec_facts_long_2023_2025.csv --start-year 2023 --end-year 2025
python -m trading_bot sec-build-processed --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_mapping.yml --fiscal-calendar-path data/reports/sec_fiscal_calendar.csv --sec-cik-mapping-path data/reports/sec_cik_mapping.csv --output-dir data/processed --reports-dir data/reports --start-year 2023 --end-year 2025
```

Notes:
- The SEC commands above remain callable because they still exist in code.
- They are documented here as the current runtime surface, not as the recommended fundamentals provider path.
- SimFin raw fundamentals uses the local cache first, can force-refresh quarterly datasets through SimFin, and applies a small validated alias map when universe tickers differ from SimFin provider tickers.

Pipeline stages are currently executed command-by-command from the CLI.

## Outputs
Currently generated when the corresponding implemented CLI stage runs:
- `data/universe_current.csv`
- `data/processed/canonical_legacy_q.csv`
- `data/processed/fundamentals_q_<year>.csv`
- `data/processed/raw_fundamentals_<year>.csv` (raw-only local historical Stage 1 output)
- `data/reports/legacy_raw_coverage_2006_2023.csv`
- `data/reports/legacy_raw_missing_universe_2006_2023.csv`
- `data/reports/legacy_raw_conflicts_2006_2023.csv`
- `data/processed/raw_fundamentals_2023.csv`
- `data/processed/raw_fundamentals_2024.csv`
- `data/processed/raw_fundamentals_2025.csv`
- `data/reports/simfin_raw_coverage_2023_2025.csv`
- `data/reports/simfin_raw_missing_universe_2023_2025.csv`
- `data/reports/simfin_raw_missing_rows_2023_2025.csv`
- `data/reports/simfin_raw_missing_fields_2023_2025.csv`
- `data/reports/simfin_raw_family_conflicts_2023_2025.csv`
- `data/reports/simfin_raw_unit_normalization_2023_2025.csv`
- `data/reports/simfin_raw_alias_hits_2023_2025.csv`
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
- `data/reports/stage1_extension_coverage_<start>_<end>.csv`

`legacy-raw-stage1` publishes raw and support fields only with leading columns
`ticker,year,quarter`. Ratio computation is intentionally deferred to a later
stage.

`simfin-raw-fundamentals` publishes the same raw fundamentals contract for
`2023-2025`, using the field mapping policy in `specs/SIMFIN_STAGE1_MAPPING.md`
and leaving unsupported fields explicitly null.
Published raw fundamentals outputs use one shared scale across the full
history:
- monetary fields in `USD millions`
- share-count fields in `millions of shares`
- per-share fields unchanged
SimFin-native base units are normalized to that published scale before the
yearly CSVs are written.

## Tests
```powershell
python -m pytest -q
python -m compileall src
```
