# S&P 500 Fundamentals Research Pipeline

[![CI](https://github.com/bernardoo-soares/fundamentals-research-pipeline/actions/workflows/ci.yml/badge.svg)](https://github.com/bernardoo-soares/fundamentals-research-pipeline/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)
[![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

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

- `src/fundamentals_pipeline/connectors`: source adapters for Wikipedia, SEC, and SimFin-style datasets.
- `src/fundamentals_pipeline/contracts`: canonical schemas and mapping contracts.
- `src/fundamentals_pipeline/steps`: runnable pipeline stages that produce artifacts.
- `src/fundamentals_pipeline/workflows`: higher-level orchestration helpers.
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
python -m fundamentals_pipeline universe --as-of-date 2026-02-07
```

Build raw fundamentals from the SimFin path:

```powershell
python -m fundamentals_pipeline simfin-raw-fundamentals `
  --universe-path data/universe_current.csv `
  --output-dir data/processed `
  --reports-dir data/reports `
  --start-year 2023 `
  --end-year 2025
```

Audit Stage 1 extension-field coverage:

```powershell
python -m fundamentals_pipeline stage1-extension-audit `
  --processed-dir data/processed `
  --reports-dir data/reports `
  --start-year 2006 `
  --end-year 2025
```

Audit legacy Stage 1 outputs:

```powershell
python -m fundamentals_pipeline legacy-stage1-audit `
  --universe-path data/universe_current.csv `
  --raw-dir data/raw/Processed-Fundamentals `
  --processed-dir data/processed `
  --reports-dir data/reports `
  --start-year 2006 `
  --end-year 2023
```

Rebuild the DuckDB analytical warehouse:

```powershell
python -m fundamentals_pipeline warehouse-rebuild `
  --processed-dir data/processed `
  --warehouse-path data/warehouse/research.duckdb `
  --reports-dir data/reports `
  --start-year 2006 --end-year 2025
```

See all CLI commands:

```powershell
python -m fundamentals_pipeline --help
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
- `data/reports/simfin_raw_unit_normalization_2023_2025.csv`
- `data/reports/simfin_raw_alias_hits_2023_2025.csv`
- `data/reports/stage1_extension_coverage_<start>_<end>.csv`
- `data/warehouse/research.duckdb` (analytical store; rebuildable, git-ignored)
- `data/reports/warehouse_health_<start>_<end>.csv`

The core output key is:

```text
ticker, year, quarter
```

Rows are sorted by ticker and quarter so downstream analysis can consume stable yearly CSVs.

Published raw fundamentals use one shared scale across the full history: monetary fields in
`USD millions`, share-count fields in `millions of shares`, and per-share fields unchanged. SimFin-native
base units are normalized to that published scale before the yearly CSVs are written (see
`specs/SIMFIN_STAGE1_MAPPING.md`).

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
