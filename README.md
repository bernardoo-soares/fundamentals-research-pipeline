# S&P 500 Fundamentals Research Pipeline

Data pipeline for building auditable S&P 500 fundamentals datasets from public and vendor-style sources.

The project focuses on research infrastructure: universe construction, source ingestion, schema mapping,
quality reports, and yearly fundamentals outputs. It is not an automated live trading system.

## Highlights

- Builds a current S&P 500 universe from Wikipedia.
- Normalizes quarterly fundamentals into a stable `ticker, year, quarter` contract.
- Supports a SimFin-backed fundamentals path for recent years.
- Keeps legacy SEC/companyfacts code available as an audit and research path.
- Emits coverage, missing-row, missing-field, and conflict reports.
- Uses a package-style `src/` layout with a command-line interface and tests.

## Architecture

```text
External sources
  -> connectors
  -> pipeline steps
  -> schema/contracts
  -> processed yearly CSVs
  -> QA reports
```

Main modules:

- `src/trading_bot/connectors`: source adapters for Wikipedia, SEC, and SimFin-style datasets.
- `src/trading_bot/contracts`: canonical schemas and mapping contracts.
- `src/trading_bot/steps`: runnable pipeline stages that produce artifacts.
- `src/trading_bot/workflows`: higher-level orchestration helpers.
- `specs`: design notes for the canonical schema, architecture, and SimFin mapping policy.
- `tests`: unit and integration-style tests using local fixtures/fakes where possible.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .[dev]
```

Create `.env` from `.env.example` if you need to override default paths or provider settings.

## Common Commands

Build the current S&P 500 universe:

```powershell
python -m trading_bot universe --as-of-date 2026-02-07
```

Build raw fundamentals from the SimFin path:

```powershell
python -m trading_bot simfin-raw-fundamentals `
  --universe-path data/universe_current.csv `
  --output-dir data/processed `
  --reports-dir data/reports `
  --start-year 2023 `
  --end-year 2025
```

Audit legacy Stage 1 outputs:

```powershell
python -m trading_bot legacy-stage1-audit `
  --universe-path data/universe_current.csv `
  --raw-dir data/raw/Processed-Fundamentals `
  --processed-dir data/processed `
  --reports-dir data/reports `
  --start-year 2006 `
  --end-year 2023
```

See all CLI commands:

```powershell
python -m trading_bot --help
```

## Outputs

The pipeline writes generated artifacts under `data/`, which is intentionally ignored by git.

Representative outputs:

- `data/universe_current.csv`
- `data/processed/raw_fundamentals_<year>.csv`
- `data/reports/simfin_raw_coverage_2023_2025.csv`
- `data/reports/simfin_raw_missing_universe_2023_2025.csv`
- `data/reports/simfin_raw_missing_rows_2023_2025.csv`
- `data/reports/simfin_raw_missing_fields_2023_2025.csv`
- `data/reports/simfin_raw_family_conflicts_2023_2025.csv`

The core output key is:

```text
ticker, year, quarter
```

Rows are sorted by ticker and quarter so downstream analysis can consume stable yearly CSVs.

## Data Notes

Large source files, generated datasets, provider caches, and reports are not committed. Some commands
require local data under `data/` or access to provider packages/APIs. Tests are designed to validate the
core contracts and transformation logic without depending on private datasets.

The current project scope is the fundamentals data layer. Future work can build on this foundation for
ratio computation, sector-aware scorecards, and research dashboards.

## Tests

```powershell
python -m pytest -q
python -m compileall src tests
python -m ruff check src tests
```

## Status

This is an active research project. The strongest implemented path is the fundamentals pipeline and its
audit reports; portfolio construction, scoring, and backtesting are intentionally outside the current
production scope.
