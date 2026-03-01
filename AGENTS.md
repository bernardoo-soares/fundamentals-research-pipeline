# Trading Bot Agent Guide

## Project Purpose
Build and operate a robust, auditable fundamentals pipeline for current S&P 500 companies, with SEC-first extensibility and reproducible outputs for screening and portfolio research.

## State Handoffs
1. `resumes/`: session handoff notes ("state of the art") that capture current project status, decisions made, and the exact next steps to resume work later.

## Instruction Chain
Codex should read instruction files in this order:
1. Root `AGENTS.md`.
2. Directory-scoped `AGENTS.override.md` files from root down to current working directory.
3. Stop at context size limits if reached; prefer nearest override when conflicts exist.

## How To Run
Setup:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
```

Main commands:
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

## Pre-PR Quality Gate
Required:
```powershell
python -m pytest -q
python -m compileall src
```

Linting:
1. No dedicated linter is configured yet.
2. If lint tooling is added later, update this section and make it required.

## Dependency Policy
1. Prefer standard library and existing dependencies first.
2. Add a new dependency only when:
   - it removes substantial custom complexity, or
   - it is required for reliability/security/performance.
3. New dependency changes must include:
   - why existing stack is insufficient,
   - minimal version pin in `pyproject.toml`,
   - test coverage for introduced behavior.

## Code Style Rules (Non-Obvious)
1. Keep raw and derived layers separate:
   - raw canonical fields in steps/connectors,
   - ratios/features only in compute stage.
2. Preserve auditability:
   - include source metadata (`filed_date`, `form_type`, source tag/version).
3. Use deterministic keys for quarterly records:
   - `ticker`, `fyearq`, `fqtr`.
4. Never silently overwrite conflicting records:
   - log or emit a conflict artifact.
5. Prefer explicit exceptions over `SystemExit` in library code.

## Repo Map
1. `src/trading_bot/core`: shared settings/logging/exceptions utilities.
2. `src/trading_bot/contracts`: typed SEC metric contract and mapping config.
3. `src/trading_bot/connectors`: external source adapters.
4. `src/trading_bot/steps`: source-facing and normalization pipeline steps.
5. `src/trading_bot/workflows`: orchestration entrypoints that compose steps.
6. `specs`: architecture and execution plans.
7. `tests`: unit/integration tests.
8. `data/raw`: source/landing files.
9. `data/processed`: canonical and transformed tables.
10. `data/reports`: coverage, QA, and screening outputs.
11. `.agents/skills`: repo-scoped skills.
12. `.agent/PLANS.md`: planning standard and ExecPlan format.
13. `.agent/plans`: execution plan documents for substantial changes.

## Skills
1. Repo-scoped skills live at `.agents/skills/**/SKILL.md`.
2. Keep skills short, trigger-based, and workflow-oriented.
3. Use progressive disclosure: load skill instructions only when triggered by task.

## Scoped Overrides
Current directory-scoped instruction files:
1. `src/AGENTS.override.md`
2. `tests/AGENTS.override.md`
3. `specs/AGENTS.override.md`
4. `data/AGENTS.override.md` (local workspace guidance; may be VCS-ignored)

## Planning Standard
1. For non-trivial work, follow `.agent/PLANS.md`.
2. Create/update an ExecPlan file in `.agent/plans/` for tasks that:
   - span multiple modules, or
   - introduce schema/pipeline behavior changes, or
   - require phased delivery.
3. Keep plan status current as work progresses.
