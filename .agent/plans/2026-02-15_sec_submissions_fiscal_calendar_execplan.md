# ExecPlan: SEC Submissions Ingestion and Fiscal Calendar Build

Status: `done`

## Goal
Add a separate SEC submissions ingestion stage and build an authoritative
per-company fiscal calendar reference table from submissions metadata.

## Scope
In scope:
1. Fetch SEC submissions JSON per mapped company.
2. Persist raw submissions files under a dedicated raw folder.
3. Write submissions ingestion log CSV.
4. Build fiscal calendar CSV with required columns.
5. Add CLI commands and tests.

Out of scope:
1. Merging submissions metadata into long facts dataset.
2. Fiscal quarter resolution logic using start/end dates.

## Assumptions
1. Mapping input comes from `data/reports/sec_cik_mapping.csv`.
2. Only rows with `mapping_status == mapped` are ingested.

## Data Contracts
1. Submissions raw files:
   - `data/raw/sec/submissions/<TICKER>_<CIK10>.json`
2. Submissions ingestion log:
   - `data/reports/sec_submissions_ingestion_log.csv`
   - Columns:
     `run_id,ticker,cik,status,http_code,attempts,latency_ms,file_path,error,fetched_at_utc`
3. Fiscal calendar output:
   - `data/reports/sec_fiscal_calendar.csv`
   - Columns:
     `ticker,cik,fiscal_year_end_mmdd,company_name,exchange`

## Sprint Roadmap

## Sprint 1: Connector and Step Implementation
Status: `done`

Objective:
- Add submissions fetch method and ingestion/calendar step functions.

Files (max 5):
1. `src/trading_bot/connectors/sec.py` (modify)
2. `src/trading_bot/steps/sec_submissions.py` (new)
3. `src/trading_bot/steps/__init__.py` (modify)

Exit Criteria:
1. New step functions produce expected output artifacts.

Validation:
```powershell
python -m compileall src
```

## Sprint 2: CLI Wiring
Status: `done`

Objective:
- Expose submissions stages in CLI.

Files (max 5):
1. `src/trading_bot/__main__.py` (modify)

Exit Criteria:
1. New commands appear in `python -m trading_bot --help`.

Validation:
```powershell
python -m trading_bot --help
```

## Sprint 3: Tests
Status: `done`

Objective:
- Add test coverage for connector, steps, and CLI dispatch.

Files (max 5):
1. `tests/sec/test_sec_client.py` (modify)
2. `tests/sec/test_sec_submissions_ingest.py` (new)
3. `tests/sec/test_sec_fiscal_calendar.py` (new)
4. `tests/sec/test_sec_cli.py` (modify)

Exit Criteria:
1. Tests validate file outputs and dispatch behavior.

Validation:
```powershell
python -m compileall src
```

## Sprint 4: Documentation
Status: `done`

Objective:
- Document new CLI commands and outputs.

Files (max 5):
1. `README.md` (modify)
2. `specs/SEC_EDGAR_IMPLEMENTATION_PLAN.md` (modify)

Exit Criteria:
1. Docs reflect new stages and artifacts.

Validation:
```powershell
python -m compileall src
```

## Risks and Mitigations
1. Risk: Missing submissions fields (`fiscalYearEnd`, `name`, `exchanges`).
   Mitigation: default to empty values and preserve audit rows.
2. Risk: API rate limiting at scale.
   Mitigation: reuse existing throttled/retrying `SecClient`.

## Validation Matrix
1. `python -m compileall src`
2. `python -m trading_bot --help`
3. `python -m trading_bot sec-ingest-submissions --help`
4. `python -m trading_bot sec-build-fiscal-calendar --help`

## Change Log
1. 2026-02-15: Created plan for submissions ingestion and fiscal calendar stages.
2. 2026-02-15: Implemented submissions ingestion and fiscal calendar steps, wired CLI commands, added tests, and updated docs/specs.
