# Project Architecture

## Goal
Retrieve the current S&P 500 universe and standardize fundamentals into auditable
outputs, combining local legacy files and SEC companyfacts normalization.

## Data Flow (High Level)
1) Fetch current S&P 500 constituents
2) Build legacy canonical quarterly rows from local wide files
3) Map universe tickers to SEC CIK
4) Ingest SEC companyfacts raw JSON payloads
5) Ingest SEC submissions raw JSON payloads
6) Build fiscal calendar reference table from submissions metadata
7) Normalize SEC facts into contract-driven long canonical facts
8) Ratio computation is deferred to a later stage

## Components

### 1) Universe Builder
- Sources:
  - Wikipedia S&P 500 current constituent list.
- Output:
  - `data/universe_current.csv` with `as_of_date`, `year`, `ticker`.

### 2) Legacy Fundamentals Canonicalization
- Source:
  - `data/raw/Processed-Fundamentals/*.csv`
- Input constraints:
  - Only current S&P 500 tickers from the universe output.
- Canonical fields:
  - `saleq`, `niq`, `oiadpq`, `xintq`, `txtq`, `epspxq`, `actq`, `lctq`,
    `ppentq`, `gdwlq`, `ivltq`, `atq`, `ceqq`, `dlcq`, `dlttq`, `req`,
    `tstkq`, `oancfq`, `prstkcq`, `capxq`, `cheq`, `dvpq`, `cshfdq`.

### 3) SEC Mapping and Raw Ingestion
- Sources:
  - SEC ticker reference JSON (`company_tickers.json`)
  - SEC companyfacts API (`data.sec.gov`)
- Outputs:
  - `data/reports/sec_cik_mapping.csv`
  - `data/reports/sec_ingestion_log.csv`
  - `data/raw/sec/companyfacts/*.json`

### 4) SEC Long Normalization
- Source:
  - `data/raw/sec/companyfacts/*.json`
- Contract:
  - `src/trading_bot/contracts/sec_metric_map.yml`
- Output:
  - `data/processed/sec_facts_long_2023_2025.csv`
- Shape:
  - Long-form facts table keyed by ticker/quarter plus `canonical_field`.
  - The step currently records mapping metadata (`transform_rule`, `quality_tier`) and does not yet execute derived transforms (for example Q4 extraction) into a wide quarterly table.

### 5) SEC Submissions Ingestion
- Source:
  - SEC submissions API (`data.sec.gov/submissions/CIK##########.json`)
- Outputs:
  - `data/reports/sec_submissions_ingestion_log.csv`
  - `data/raw/sec/submissions/*.json`

### 6) SEC Fiscal Calendar Reference
- Source:
  - `data/raw/sec/submissions/*.json`
- Output:
  - `data/reports/sec_fiscal_calendar.csv`
- Columns:
  - `ticker`, `cik`, `fiscal_year_end_mmdd`, `company_name`, `exchange`

### 7) Ratio Computation (Deferred)
- Derived ratios are intentionally not produced in the current code path.

## Workflow Orchestration
- `full-run` currently orchestrates only:
  - universe build
  - legacy fundamentals canonicalization
- SEC mapping/ingestion/normalization run as separate CLI stages.

## Outputs
Generated when each pipeline stage is executed:
- `data/universe_current.csv`
- `data/processed/canonical_legacy_q.csv`
- `data/processed/fundamentals_q_<year>.csv`
- `data/reports/sec_cik_mapping.csv`
- `data/reports/sec_ingestion_log.csv`
- `data/reports/sec_submissions_ingestion_log.csv`
- `data/raw/sec/submissions/*.json`
- `data/processed/sec_facts_long_2023_2025.csv`
- `data/reports/sec_fiscal_calendar.csv`
