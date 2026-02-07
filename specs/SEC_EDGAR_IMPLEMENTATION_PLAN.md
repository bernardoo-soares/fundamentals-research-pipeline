# SEC EDGAR Pipeline Implementation Plan (2023-2025, Current S&P 500)

## 1. Objective
Build an auditable quarterly fundamentals pipeline that:
1. Uses the current S&P 500 universe from `data/universe_current.csv`.
2. Reuses legacy fundamentals history and narrows it to required columns.
3. Appends SEC EDGAR-derived quarterly data for fiscal years `2023`, `2024`, `2025`.
4. Recomputes all derived metrics and ratios from raw canonical fields.
5. Produces final datasets for screening and manual analysis.

## 2. Locked Decisions
1. Rebalance cadence: every 2 years.
2. Data timing policy: conservative (filing-date aware).
3. Quarterly policy: Q4 from 10-K quarter extraction.
4. ROA/ROE policy: trailing 4-quarter logic.
5. Missing data policy: allow missing values.
6. Universe policy: use current constituents exactly as provided.
7. Data scope now: fill and standardize `2023-2025`.
8. Long-term investments policy: broad-quality fallback family.

## 3. Target Architecture
### 3.1 Layers
1. Universe layer:
`data/universe_current.csv` is the source of truth for tickers.
2. Legacy narrowing layer:
Convert large per-company files in `data/raw/Processed-Fundamentals/` into compact canonical history.
3. SEC raw ingestion layer:
Store raw SEC payloads for traceability.
4. SEC normalization layer:
Map SEC facts to canonical quarterly fields.
5. Canonical merge layer:
Merge legacy + SEC into one canonical quarterly table.
6. Feature/ratio layer:
Compute all ratios and screening metrics.
7. Reporting layer:
Coverage, missingness, and final screen-ready datasets.

### 3.2 Canonical Raw Schema (minimal)
Primary keys:
1. `ticker`
2. `fyearq`
3. `fqtr`

Traceability fields:
1. `period_end`
2. `filed_date`
3. `form_type`
4. `source_system`
5. `source_tag_map_version`

Raw fields needed for metrics in `specs/GENERAL_ARCHITECTURE.md`:
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

Fallback-compatible helper fields:
1. `oancfy` (for Q4 extraction/fallback)
2. `prstkcy` (fallback for repurchase estimation)
3. `cshopq` (share repurchase proxy)

## 4. SEC Mapping Strategy
Use a versioned mapping file:
`src/trading_bot/config/sec_metric_map.yml`

Each canonical field stores:
1. Priority-ordered SEC tags.
2. Expected unit type.
3. Fact type:
`duration` or `instant`.
4. Transformation rule:
`direct`, `sum_components`, `q4_extract`.
5. Quality tier:
`primary`, `fallback`, `proxy`.

Long-term investments (`ivltq`) broad-quality policy:
1. Prefer direct noncurrent investments total tags.
2. If absent, sum non-overlapping noncurrent investment components.
3. Do not include cash/short-term equivalents.
4. Capture chosen source tag in audit columns.

## 5. Quarter Construction Rules
1. Q1-Q3:
Use 10-Q duration facts directly when available.
2. Q4 duration facts:
Use 10-K extraction:
`Q4 = FY - (Q1 + Q2 + Q3)`.
3. Instant facts:
Use quarter-end aligned values from filed facts at/after period end and before cutoff.
4. Conservative policy:
Only use facts with `filed_date <= snapshot_cutoff`.

## 6. Ratio and Metric Computation Rules
All derived values must be recomputed from canonical raw fields.

Core formulas:
1. `Operating_Margin = oiadpq / saleq`
2. `Net_Profit_Margin = niq / saleq`
3. `Current_Ratio = actq / lctq`
4. `Debt_to_Equity = (dlcq + dlttq) / ceqq`
5. `Short_Term_Debt = dlcq / (dlcq + dlttq)`
6. `Healthy_Long_Term_Debt = dlttq / ceqq`
7. `Book_Value = ceqq`
8. `Treasury_Adjusted_Debt_to_Equity = (dlcq + dlttq) / (ceqq - abs(tstkq))`
9. `Retained_Earnings_Growth = YoY(req)`
10. `Share_Repurchases = prstkcq` with fallback from proxies if missing

TTM/4-quarter rules:
1. `ROA = TTM(niq) / Avg4Q(atq)`
2. `ROE = TTM(niq) / Avg4Q(ceqq)`
3. Growth metrics use rolling 4-quarter aggregates where needed.

## 7. Sprint Plan
Each sprint should be a small PR-sized unit with tests and artifacts.

### Sprint 0: Baseline and Contracts
Goal:
Freeze data contracts and file conventions.

Tasks:
1. Create canonical schema definition file.
2. Define mapping contract and quality flags.
3. Define output file naming and partition strategy.

Deliverables:
1. `specs/CANONICAL_SCHEMA.md`
2. `src/trading_bot/config/sec_metric_map.yml` (initial stub)
3. `tests/schema/` contract tests

Exit criteria:
1. Schema tests pass.
2. Mapping file validates.

### Sprint 1: Legacy Narrowing (2006-2024 existing)
Goal:
Convert large 663-column legacy files into compact canonical history table.

Tasks:
1. Read per-company files from `data/raw/Processed-Fundamentals/`.
2. Keep only canonical fields and keys.
3. Standardize dtypes and null handling.
4. Output compact quarterly history.

Deliverables:
1. `data/processed/canonical_legacy_q.csv`
2. `data/reports/legacy_coverage_report.csv`

Exit criteria:
1. One row per `ticker,fyearq,fqtr` after dedupe policy.
2. Coverage report generated.

### Sprint 2: SEC Raw Ingestion (2023-2025 scope)
Goal:
Fetch raw SEC data only for current S&P 500 tickers and persist raw artifacts.

Tasks:
1. Map `ticker -> CIK` for current universe.
2. Fetch `companyfacts` payloads.
3. Persist raw JSON with metadata.
4. Log request outcomes and errors.

Deliverables:
1. `data/raw/sec/companyfacts/*.json`
2. `data/raw/sec/sec_ingestion_log.csv`

Exit criteria:
1. Raw payload exists for all reachable tickers.
2. Failures are explicit and retryable.

### Sprint 3: SEC Normalization and Q4 Extraction
Goal:
Map raw SEC facts into canonical quarterly rows for `2023-2025`.

Tasks:
1. Apply tag priority map and unit filters.
2. Build quarter-level values for duration and instant facts.
3. Apply Q4 extraction from 10-K for duration fields.
4. Add source tag and quality metadata.

Deliverables:
1. `data/processed/canonical_sec_q_2023_2025.csv`
2. `data/reports/sec_mapping_quality_report.csv`

Exit criteria:
1. Canonical SEC rows keyed by `ticker,fyearq,fqtr`.
2. All mapped fields include source traceability.

### Sprint 4: Merge and Recompute Derived Metrics
Goal:
Merge legacy + SEC and recompute all derived metrics.

Tasks:
1. Merge canonical legacy and canonical SEC rows.
2. Resolve precedence for overlapping quarters.
3. Recompute all ratios and derived metrics from raw fields only.
4. Generate final fundamentals and ratios datasets.

Deliverables:
1. `data/processed/fundamentals_q_2023_2025.csv`
2. `data/processed/ratios_q_2023_2025.csv`
3. `data/reports/final_coverage_2023_2025.csv`

Exit criteria:
1. No engineered legacy columns reused.
2. Derived metrics are reproducible from raw canonical columns.

### Sprint 5: Validation and Operationalization
Goal:
Make pipeline auditable, repeatable, and ready for future runs.

Tasks:
1. Add CLI commands for each stage.
2. Add end-to-end integration test on sample tickers.
3. Add data quality gates and run summary report.
4. Document rerun and backfill procedures.

Deliverables:
1. CLI docs and runbook.
2. Integration tests and QA checks.
3. `data/reports/run_summary_<date>.md`

Exit criteria:
1. One command can rebuild 2023-2025 outputs.
2. QA gates pass or produce explicit failure report.

## 8. Dedupe and Conflict Resolution Policy
1. Key:
`ticker,fyearq,fqtr`.
2. Prefer SEC canonical rows over legacy for `2023-2025`.
3. If multiple SEC facts candidate:
prefer highest mapping tier, then latest filed fact before cutoff.
4. Keep conflict log:
`data/reports/conflict_resolution_log.csv`.

## 9. Data Quality Gates
1. Row uniqueness by key.
2. Numeric parse validity.
3. Missingness per metric by ticker/year.
4. Outlier sanity checks for ratio denominators near zero.
5. Coverage thresholds for report publication.

## 10. Immediate Next Sprint to Start
Start with Sprint 0 and Sprint 1 only.
Reason:
This reduces complexity first, validates canonical contracts, and makes SEC append deterministic.
