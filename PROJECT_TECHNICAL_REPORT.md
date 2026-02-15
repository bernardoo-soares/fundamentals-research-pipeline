# Trading Bot Technical Report (Deep Ownership Guide)

Last updated: 2026-02-14
Repository root: `C:\Users\berna\Dropbox\Trading_Bot`

## 0) Current Truth Snapshot

This section is intentionally operational and date-stamped so you can quickly orient.

1. Source package structure: `core`, `contracts`, `connectors`, `steps`, `workflows`.
2. CLI commands available:
   - `universe`
   - `legacy-fundamentals`
   - `full-run`
   - `sec-map-cik`
   - `sec-ingest-raw`
   - `sec-normalize-long`
3. Raw source volume today:
   - `data/raw/Processed-Fundamentals/*.csv`: 1488 files
   - `data/raw/sec/companyfacts/*.json`: 502 files
4. Current `data/processed` state: empty right now (`0` CSVs).
5. Validation baseline:
   - `python -m pytest -q` passes
   - `python -m compileall src` passes

Important scope note:

- Ratio computation is currently deferred and not implemented in pipeline outputs.
- Current legacy step produces canonical fundamentals only.

## 1) System Goal and Non-Goal

### Goal

Build an auditable fundamentals pipeline for current S&P 500 companies with deterministic artifacts.

### Non-Goal (current state)

Do not compute derived ratios yet. Only fetch, map, normalize, and persist canonical/traceable data.

## 2) Architecture You Own

```text
src/trading_bot/
  __init__.py
  __main__.py
  core/
    settings.py
    logging.py
    exceptions.py
  contracts/
    sec_metric_contract.py
    sec_metric_map.yml
  connectors/
    sp500.py
    sec.py
  steps/
    universe.py
    legacy_fundamentals.py
    sec_fundamentals.py
  workflows/
    full_run.py
```

### Layer responsibilities

1. `core`: shared infrastructure only.
2. `contracts`: strict schema/tag contract for SEC normalization.
3. `connectors`: external I/O adapters and parsing helpers.
4. `steps`: artifact-producing pipeline units.
5. `workflows`: orchestration across steps.

Design rule:

- Keep side effects in `steps`.
- Keep external transport/parsing in `connectors`.
- Keep policy/constraints in `contracts`.

## 3) Runtime Command Graph (Exact)

## 3.1 Universe

```powershell
python -m trading_bot universe --as-of-date 2026-02-07
```

Call chain:

1. `trading_bot.__main__.main`
2. `trading_bot.steps.universe.build_sp500_current_universe`
3. `trading_bot.connectors.sp500.SP500Constituents.get_sp500_current`

Artifact:

1. `data/universe_current.csv`

## 3.2 Legacy fundamentals (canonical only)

```powershell
python -m trading_bot legacy-fundamentals --start-date 2023-01-01 --end-date 2025-12-31
```

Call chain:

1. `trading_bot.__main__.main`
2. `trading_bot.steps.legacy_fundamentals.build_legacy_fundamentals`

Artifacts:

1. `data/processed/canonical_legacy_q.csv`
2. `data/processed/fundamentals_q_<year>.csv`

## 3.3 SEC mapping

```powershell
python -m trading_bot sec-map-cik --universe-path data/universe_current.csv --output-path data/reports/sec_cik_mapping.csv
```

Call chain:

1. `trading_bot.__main__.main`
2. `trading_bot.steps.sec_fundamentals.build_sec_cik_mapping`
3. `trading_bot.connectors.sec.fetch_sec_ticker_reference`
4. `trading_bot.connectors.sec.build_ticker_reference_lookup`

Artifact:

1. `data/reports/sec_cik_mapping.csv`

## 3.4 SEC raw ingestion

```powershell
python -m trading_bot sec-ingest-raw --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/companyfacts --log-path data/reports/sec_ingestion_log.csv
```

Call chain:

1. `trading_bot.__main__.main`
2. `trading_bot.steps.sec_fundamentals.run_sec_raw_ingestion`
3. `trading_bot.steps.sec_fundamentals._build_client`
4. `trading_bot.connectors.sec.SecClient.fetch_companyfacts`

Artifacts:

1. `data/raw/sec/companyfacts/<TICKER>_<CIK>.json`
2. `data/reports/sec_ingestion_log.csv`

## 3.5 SEC long normalization

```powershell
python -m trading_bot sec-normalize-long --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_map.yml --output-path data/processed/sec_facts_long_2023_2025.csv --start-year 2023 --end-year 2025
```

Call chain:

1. `trading_bot.__main__.main`
2. `trading_bot.steps.sec_fundamentals.normalize_sec_facts_long`
3. `trading_bot.contracts.sec_metric_contract.load_sec_metric_contract`
4. `trading_bot.connectors.sec.iter_companyfacts_rows`

Artifact:

1. `data/processed/sec_facts_long_2023_2025.csv`

## 3.6 Full workflow

```powershell
python -m trading_bot full-run --as-of-date 2026-02-07 --start-date 2023-01-01 --end-date 2025-12-31
```

Current behavior:

1. Runs `universe` step.
2. Runs `legacy-fundamentals` step.

Not included yet:

1. SEC mapping
2. SEC raw ingestion
3. SEC normalization

## 4) File-by-File Deep Technical Breakdown

## 4.1 `src/trading_bot/__main__.py`

### `_build_parser() -> argparse.ArgumentParser`

Responsibilities:

1. Load runtime defaults from `get_settings()`.
2. Define command grammar and flags.
3. Keep CLI thin (no business logic).

Commands/args defaults:

1. `universe`:
   - `--as-of-date`
   - `--output-dir` default `settings.data_root`
   - `--filename` default `settings.universe_filename`
2. `legacy-fundamentals`:
   - `--universe-path` default `<data_root>/universe_current.csv`
   - `--raw-dir` default `settings.legacy_fundamentals_dir`
   - `--output-dir` default `settings.processed_data_dir`
   - `--start-date`, `--end-date`
   - `--canonical-filename` default `settings.canonical_legacy_filename`
3. `full-run`:
   - `--data-root`
   - `--as-of-date`, `--start-date`, `--end-date`
4. `sec-map-cik`:
   - `--universe-path`
   - `--output-path`
5. `sec-ingest-raw`:
   - `--mapping-path`
   - `--raw-dir`
   - `--log-path`
   - `--run-id`
6. `sec-normalize-long`:
   - `--raw-dir`
   - `--mapping-path` default `src/trading_bot/contracts/sec_metric_map.yml`
   - `--output-path`
   - `--start-year`, `--end-year`

### `main() -> None`

Responsibilities:

1. Parse args.
2. Dispatch to one step/workflow function.
3. Print row-count/summary for shell UX.

Contract:

- Every command returns deterministic output type:
  - DataFrame commands print row count.
  - workflow returns summary dict.

## 4.2 `src/trading_bot/core/settings.py`

### `_env_int(name, default)` / `_env_float(name, default)`

- Strict conversion wrappers for env config.

### `AppSettings`

Typed runtime contract for the system.

Fields:

1. `wiki_url`
2. `sec_reference_url`
3. `sec_data_url`
4. `request_timeout_seconds`
5. `sec_rate_limit_per_second`
6. `sec_max_retries`
7. `user_agent`
8. `log_level`
9. `data_root`
10. `raw_data_dir`
11. `processed_data_dir`
12. `reports_data_dir`
13. `legacy_fundamentals_dir`
14. `universe_filename`
15. `canonical_legacy_filename`

### `get_settings()`

Behavior:

1. Resolve all env overrides and defaults.
2. Build immutable settings object.
3. Cache result process-wide.

Ownership tip:

- Any default path/URL policy changes should happen here only.

## 4.3 `src/trading_bot/core/logging.py`

### `JsonFormatter`

Format output fields:

1. `ts`
2. `level`
3. `logger`
4. `msg`
5. optional `exc_info`

### `configure_logging(level="INFO")`

Behavior:

1. Idempotent setup.
2. If handlers exist, only level is updated.

### `get_logger(name)`

- Thin wrapper around stdlib logger retrieval.

### `utc_now_iso()`

- Canonical UTC timestamp helper used in logs and run IDs.

## 4.4 `src/trading_bot/core/exceptions.py`

Exception taxonomy:

1. `TradingBotError`
2. `ConfigurationError`
3. `DataSourceError`
4. `SecRequestError` (with status/attempt/url metadata)
5. `SecRateLimitError` specialized subtype

Design rationale:

- Preserve structured failure context for ingestion logs and upstream handling.

## 4.5 `src/trading_bot/contracts/sec_metric_contract.py`

This file enforces the SEC mapping contract.

### Core constant sets

1. `FETCH_ONLY_RAW_FIELDS` (23 canonical fields)
2. `HELPER_FALLBACK_FIELDS` (4 helper-only fields)
3. `REQUIRED_CANONICAL_FIELDS` (= fetch + helper)
4. `COMPUTE_ONLY_FIELDS` (forbidden in this contract)
5. Allowed enums for fact type, transform rules, quality tiers, forms.

### Data models

1. `MetricMapping`
2. `SecMetricContract`

### Parsing and validation flow

1. YAML load -> `_expect_mapping`
2. per-metric parse -> `_parse_metric_mapping`
3. per-metric semantic checks -> `_validate_metric_mapping`
4. whole-contract checks -> `validate_contract`

### `validate_contract(contract)` critical checks

1. Missing required canonical names -> fail.
2. Unsupported extra names -> fail.
3. Compute-only names leaked into contract -> fail.
4. Invalid forms/rules/types -> fail.
5. helper fallback references missing or non-helper field -> fail.

### `load_sec_metric_contract(path=None)`

Contract load API used by normalization stage.

Ownership tip:

- If normalization behavior changes, update YAML + this validator + schema tests together.

## 4.6 `src/trading_bot/contracts/sec_metric_map.yml`

Role:

- Declarative mapping policy from SEC tags to canonical fields.

Per metric shape:

1. `fact_type`
2. `unit_priority`
3. `form_priority`
4. `tag_priority`
5. `transform_rule`
6. `quality_tier`
7. optional `helper_fallbacks`
8. optional `component_tags`

Current version: `1.1.0`.

Ownership tip:

- Treat this as a contract file, not a casual config. Version bumps should be explicit and tested.

## 4.7 `src/trading_bot/connectors/sp500.py`

Class: `SP500Constituents`

### `_fetch_tables()`

1. GET Wikipedia page.
2. Parse HTML tables using pandas.

### `_get_current_members(tables)`

1. Reads table[0].
2. Accepts column names `symbol` or `ticker symbol`.
3. Returns ticker strings.

### `get_sp500_current()`

- orchestrates fetch + extraction.

Failure mode:

- layout drift on Wikipedia can break column discovery.

## 4.8 `src/trading_bot/connectors/sec.py`

Contains 3 concern groups: SEC HTTP client, ticker reference helpers, companyfacts row parser.

### `SecClient`

#### `__init__`

Validates:

1. `rate_limit_per_second > 0`
2. `max_retries >= 0`

State:

1. session headers
2. throttle timestamp
3. last status/attempt counters

#### `_throttle()`

- request pacing control.

#### `_request_json(url)`

Retry policy:

1. Retryable codes: `429,500,502,503,504`.
2. Backoff: `2^(attempt-1) + uniform(0,0.3)`.
3. Non-retryable HTTP error -> immediate `SecRequestError`.
4. Exhaust retries -> `SecRequestError`.

#### `fetch_companyfacts(cik)`

- builds endpoint path `/api/xbrl/companyfacts/CIK{cik10}.json`.

### Ticker reference utilities

#### `normalize_ticker(symbol)`

- uppercase, trim, remove spaces, map `/` -> `-`.

#### `_ticker_aliases(symbol)`

- includes dot/dash aliases (`BRK.B` <-> `BRK-B`).

#### `fetch_sec_ticker_reference(session, url, timeout)`

1. Parses SEC reference payload as dict or list.
2. Normalizes row keys to `ticker,cik,name,exchange`.

#### `build_ticker_to_cik_index(rows)`

- direct normalized dict map.

#### `build_ticker_reference_lookup(rows)`

- alias-aware lookup to candidate rows.

### Companyfacts parser

#### `iter_companyfacts_rows(payload, ticker, cik)`

Flattens nested JSON:

1. taxonomy
2. tag
3. unit
4. observation list

Yields normalized row dict with fields:

1. `ticker,cik,taxonomy,tag,unit,value,start,end,fy,fp,form,filed,accn,frame`

## 4.9 `src/trading_bot/steps/universe.py`

### `_normalize_ticker(value)`

- uppercase normalization.

### `_coerce_date(value)`

- parse or default to current date.

### `build_sp500_current_universe(output_dir="data", as_of_date=None, filename="universe_current.csv")`

Algorithm:

1. resolve as-of date
2. fetch member list
3. normalize/dedupe/sort
4. build DataFrame with `as_of_date`,`year`,`ticker`
5. ensure output dir
6. write CSV

## 4.10 `src/trading_bot/steps/legacy_fundamentals.py`

This module now only handles canonical fundamentals ingestion from legacy raw files.

### `CANONICAL_RAW_FIELDS`

Canonical set currently produced from legacy source:

1. `saleq`
2. `niq`
3. `oiadpq`
4. `xintq`
5. `txtq`
6. `epspxq`
7. `actq`
8. `lctq`
9. `ppentq`
10. `gdwlq`
11. `ivltq`
12. `atq`
13. `ceqq`
14. `dlcq`
15. `dlttq`
16. `req`
17. `tstkq`
18. `oancfq`
19. `prstkcq`
20. `capxq`
21. `cheq`
22. `dvpq`
23. `cshfdq`

### `_normalize_ticker(value)`
### `_coerce_date(value)`

- primitive parsing utilities.

### `_load_universe_tickers(universe_path)`

1. read CSV
2. require `ticker` column
3. return normalized set

### `_legacy_input_columns()`

Defines read projection from huge raw files.

Includes fallback-support columns:

1. `tstkcq`, `cshopq`, `cshoq`, `prstkcy`

### `_coerce_numeric_columns(df, columns)`

- vectorized numeric coercion with `errors="coerce"`.

### `_load_legacy_file(path, ticker_fallback)`

Algorithm detail:

1. read projected columns only
2. determine ticker:
   - prefer `tic`
   - fallback file prefix
3. fallback mappings:
   - `tstkcq -> tstkq`
   - if `prstkcq` missing:
     - use `cshopq`
     - else use `prstkcy / 4`
4. if `cshoq` exists and `cshfdq` missing/null -> backfill `cshfdq`
5. parse `datadate -> period_end`
6. ensure numeric keys (`fyearq`,`fqtr`)
7. infer missing fiscal keys from `period_end`
8. drop rows missing `ticker,fyearq,fqtr`
9. cast keys to int64
10. add audit columns:
    - `source_system=legacy_processed_fundamentals`
    - `source_tag_map_version=legacy-v1`
    - `filed_date` = NaT
    - `form_type` = NA
11. enforce canonical column set
12. dedupe by `ticker,fyearq,fqtr` keeping latest row

### `_apply_date_filter(df, start_date, end_date)`

1. build `period_dates` from `period_end`
2. if missing, fallback to end-of-quarter timestamp from `fyearq/fqtr`
3. filter by `start_date`, `end_date`

### `_write_year_partitions(df, output_dir)`

1. group by `fyearq`
2. write one file per fiscal year:
   - `fundamentals_q_<year>.csv`

### `build_legacy_fundamentals(...)`

Main algorithm:

1. load settings and universe tickers
2. resolve raw and output dirs
3. validate raw dir exists
4. parse date filters
5. iterate all raw CSV files
6. filter files by universe ticker prefix
7. parse each file via `_load_legacy_file`
8. concat frames
9. apply date filter
10. stable sort + dedupe on key
11. write canonical file
12. write yearly fundamentals partitions
13. return DataFrame

Failure behavior:

1. raw dir missing -> `FileNotFoundError`
2. no matching files -> `RuntimeError`
3. malformed universe -> `ValueError`

## 4.11 `src/trading_bot/steps/sec_fundamentals.py`

This module contains all current SEC pipeline steps.

### `build_sec_cik_mapping(universe_path, output_path)`

Algorithm:

1. read universe CSV, require `ticker`
2. normalize + unique + sort tickers
3. fetch SEC reference rows
4. build alias lookup
5. for each ticker:
   - 1 unique CIK candidate -> `mapped`
   - >1 unique CIK -> `ambiguous`
   - 0 candidates -> `missing`
6. write sorted mapping CSV

Output columns:

1. `ticker`
2. `cik`
3. `sec_ticker`
4. `sec_name`
5. `exchange`
6. `mapping_status`
7. `mapped_at_utc`

### `_build_client()`

- builds `SecClient` from settings.

### `run_sec_raw_ingestion(mapping_path, raw_dir, log_path, run_id=None, client=None)`

Algorithm:

1. default `run_id` to UTC timestamp
2. read mapping file and require columns
3. keep only mapped rows with non-empty ticker/cik
4. ensure raw/log directories exist
5. for each mapped ticker:
   - fetch payload
   - write JSON file
   - capture log metadata
   - on errors capture status/error context
6. write ingestion log CSV

`INGESTION_LOG_COLUMNS` schema:

1. `run_id`
2. `ticker`
3. `cik`
4. `status`
5. `http_code`
6. `attempts`
7. `latency_ms`
8. `file_path`
9. `error`
10. `fetched_at_utc`

### Normalization constants

1. `LONG_FACT_COLUMNS`
2. `DEDUPE_KEY`

### `_parse_file_name(path)`

- validates `<ticker>_<cik>.json` naming.

### `_coerce_year(value)`
### `_coerce_quarter_from_fp(value)`
### `_coerce_timestamp(value)`

- parsing helpers for fiscal fields and dates.

### `_resolve_canonical_field(tag_full, mapping)`

1. match against `tag_priority` -> primary tag selection
2. match against `component_tags` -> component selection

Returns:

- `(canonical_field, is_component_tag)` or `None`.

### `_build_row(...)`

Gatekeeping logic for one candidate row:

1. form must be allowed by contract
2. unit must be allowed by contract
3. year must be in target range
4. quarter must be inferable (`fp` or period end)
5. value must be numeric

Builds normalized row with audit metadata.

### `normalize_sec_facts_long(raw_dir, mapping_path, output_path, start_year=2023, end_year=2025)`

Algorithm detail:

1. load validated contract
2. resolve output path:
   - if path is existing dir -> auto filename
   - if path has non-csv suffix -> treat as directory
3. iterate all raw SEC json files
4. flatten facts with `iter_companyfacts_rows`
5. resolve each tag to canonical field
6. build candidate rows via `_build_row`
7. create DataFrame with fixed column order
8. if empty -> write empty CSV and return
9. coerce datetime fields and normalize `accn`
10. deterministic dedupe:
    - sort by `DEDUPE_KEY + [filed_date, accn]`
    - drop dupes keep last
11. final stable sort by ticker/year/quarter/field/time
12. write CSV and return

## 4.12 `src/trading_bot/workflows/full_run.py`

### `_summary_years(df)`

1. if `period_end` exists, derive years from it
2. else fallback to `fyearq`

### `run_full_pipeline(data_root=None, as_of_date=None, start_date=None, end_date=None)`

1. resolve root path
2. run universe step
3. run legacy fundamentals step
4. return summary map:
   - `universe_rows`
   - `canonical_rows`
   - `years`
   - `universe_path`
   - `canonical_path`

## 5) Artifact Contracts (Output Schemas)

## 5.1 `data/universe_current.csv`

Columns:

1. `as_of_date` (ISO date string)
2. `year` (int)
3. `ticker` (uppercase symbol)

## 5.2 `data/reports/sec_cik_mapping.csv`

Columns:

1. `ticker`
2. `cik`
3. `sec_ticker`
4. `sec_name`
5. `exchange`
6. `mapping_status` (`mapped|ambiguous|missing`)
7. `mapped_at_utc`

## 5.3 `data/reports/sec_ingestion_log.csv`

Columns:

1. `run_id`
2. `ticker`
3. `cik`
4. `status` (`ok|error`)
5. `http_code`
6. `attempts`
7. `latency_ms`
8. `file_path`
9. `error`
10. `fetched_at_utc`

## 5.4 `data/processed/canonical_legacy_q.csv`

Key:

1. `ticker`
2. `fyearq`
3. `fqtr`

Audit columns:

1. `period_end`
2. `filed_date`
3. `form_type`
4. `source_system`
5. `source_tag_map_version`

Raw canonical columns:

1. 23 fields listed in `CANONICAL_RAW_FIELDS`.

## 5.5 `data/processed/fundamentals_q_<year>.csv`

- Per-year partitions of canonical legacy dataframe.

## 5.6 `data/processed/sec_facts_long_2023_2025.csv`

Columns:

1. `ticker`
2. `cik`
3. `fyearq`
4. `fqtr`
5. `period_start`
6. `period_end`
7. `filed_date`
8. `form_type`
9. `accn`
10. `frame`
11. `canonical_field`
12. `value`
13. `unit`
14. `source_tag`
15. `quality_tier`
16. `fact_type`
17. `transform_rule`
18. `is_component_tag`
19. `source_system`
20. `source_tag_map_version`

## 6) Tests: Full Map to Behavior

## 6.1 Core pipeline tests

1. `tests/test_sp500_universe.py`
   - universe ticker normalization
   - output file writing
2. `tests/test_legacy_fundamentals.py`
   - universe filtering
   - canonical and fundamentals outputs only

## 6.2 Contract tests

1. `tests/schema/test_sec_metric_contract.py`
   - mapping file existence
   - exact canonical field set
   - compute-only exclusion
   - allowed form checks
   - helper/component validation

## 6.3 SEC tests

1. `tests/sec/test_sec_reference.py`
   - ticker normalization and alias behavior
2. `tests/sec/test_sec_cik_mapping.py`
   - mapped/missing/ambiguous mapping logic
3. `tests/sec/test_sec_client.py`
   - retry and failure semantics
4. `tests/sec/test_sec_ingest_raw.py`
   - raw json output + ingestion log behavior
5. `tests/sec/test_sec_fact_parser.py`
   - companyfacts flattening
6. `tests/sec/test_sec_normalize_facts.py`
   - form/unit/year filtering and mapping
7. `tests/sec/test_sec_normalize_output.py`
   - deterministic dedupe tie-break
8. `tests/sec/test_sec_cli.py`
   - CLI dispatch integration

## 7) Invariants You Must Protect

1. Universe ticker column is mandatory.
2. Quarterly key is always `ticker,fyearq,fqtr`.
3. Contract fields must match exact required canonical set.
4. SEC raw filenames must be `<TICKER>_<CIK10>.json`.
5. SEC long normalization dedupe must be deterministic.
6. No ratio computation in current runtime steps.
7. CLI remains thin and delegates behavior to steps/workflows.

## 8) Failure Modes and Debug Playbook

## 8.1 Universe issues

Symptoms:

1. symbol column missing
2. HTTP failure from Wikipedia

Check:

```powershell
python -m trading_bot universe --help
```

## 8.2 SEC mapping issues

Symptoms:

1. many `missing` or `ambiguous`

Check:

```powershell
python -m trading_bot sec-map-cik --universe-path data/universe_current.csv --output-path data/reports/sec_cik_mapping.csv
```

Inspect:

```powershell
Get-Content data/reports/sec_cik_mapping.csv -TotalCount 20
```

## 8.3 SEC ingestion issues

Symptoms:

1. status `error` in ingestion log

Check:

```powershell
python -m trading_bot sec-ingest-raw --mapping-path data/reports/sec_cik_mapping.csv --raw-dir data/raw/sec/companyfacts --log-path data/reports/sec_ingestion_log.csv
```

Inspect errors:

```powershell
Import-Csv data/reports/sec_ingestion_log.csv | Where-Object { $_.status -eq 'error' } | Select-Object -First 20
```

## 8.4 SEC normalization empty output

Symptoms:

1. normalized_rows=0

Likely causes:

1. contract path wrong
2. raw dir empty
3. form/unit/year filters exclude all observations

Check:

```powershell
python -m trading_bot sec-normalize-long --raw-dir data/raw/sec/companyfacts --mapping-path src/trading_bot/contracts/sec_metric_map.yml --output-path data/processed/sec_facts_long_2023_2025.csv --start-year 2023 --end-year 2025
```

## 8.5 Legacy no matching files

Symptoms:

1. `RuntimeError: No legacy fundamentals matched...`

Likely causes:

1. universe tickers do not exist in raw file prefixes
2. raw dir path misconfigured

## 9) Ownership Program (How You Become Fully Autonomous)

This is the most important section.

## 9.1 Phase 1 - Read with execution

Goal: map code paths in your head.

For each command:

1. run the command
2. open called step function
3. open connector/helper functions it depends on
4. open matching tests
5. write 5 bullets:
   - input files
   - output files
   - key transformations
   - invariant checks
   - failure behavior

Commands order:

1. `universe`
2. `legacy-fundamentals`
3. `sec-map-cik`
4. `sec-ingest-raw`
5. `sec-normalize-long`
6. `full-run`

## 9.2 Phase 2 - Controlled modifications

Goal: own behavior changes safely.

Exercises:

1. Add one new optional CLI arg to an existing command and pass it through.
2. Add one new assertion in a matching test file.
3. Add one extra audit field to one output and update tests.

Rule:

- no code change without a corresponding test change when behavior changes.

## 9.3 Phase 3 - Debug drills

Goal: gain operational confidence.

Do these intentionally:

1. break mapping path and recover.
2. pass empty raw dir and inspect outputs.
3. run sec ingest with fake failing client (see test pattern).

## 9.4 Phase 4 - Architecture ownership

Goal: protect simplicity while scaling.

Any new feature must answer:

1. Is it connector logic, step logic, contract logic, or workflow logic?
2. What artifact contract changes?
3. What invariant can break?
4. What tests prove it remains safe?

## 9.5 Personal checklist before each merge

```powershell
python -m pytest -q
python -m compileall src
python -m trading_bot --help
```

And manually verify:

1. output schemas unchanged unless intentional
2. docs reflect changed behavior
3. no dead paths or duplicate logic introduced

## 10) Active TODOs (Project-level)

1. Add final merged canonical quarterly table (legacy + SEC precedence).
2. Add deterministic conflict-resolution artifact.
3. Integrate SEC stages into `full-run` when you decide.
4. Reintroduce ratio stage later as a dedicated step (not mixed into canonical ingest).

## 11) Your Annotation Template

Use this copy/paste block for each module:

```md
### Module: <path>
- Purpose:
- Inputs:
- Outputs:
- Side effects:
- Invariants:
- Failure modes:
- Tests covering it:
- My notes:
```

Use this for each command:

```md
### Command: <command>
- Step function:
- Connectors used:
- Contract used:
- Files read:
- Files written:
- How to validate quickly:
- What can go wrong first:
```

## 12) Ownership Rules (Keep It Simple)

1. No generic folders beyond current layers.
2. Keep one responsibility per function.
3. Keep outputs explicit and version-aware.
4. Keep contract strictness high (fail fast).
5. Keep documentation synchronized with runtime behavior.
6. Prefer deleting dead complexity over adding abstraction early.
