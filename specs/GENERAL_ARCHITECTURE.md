# Project Architecture

## Goal
Build a fundamentals pipeline that produces normalized yearly CSV outputs and derived fundamentals-ratio yearly CSV outputs for the current universe, with a later extension for company scoring and yearly ranking.

## Time Horizon
1. Historical normalized base available from local files: `2006-2023`
   - Source for this path: `data/raw/Processed-Fundamentals/*.csv`.
2. Current extension window: `2023-2025`
   - Source for this phase: SimFin API.
3. `2023-2025` should be treated as fully SimFin-driven for the current implementation phase.
4. Final provider-selection policy for overlapping windows remains separate from the local Stage 1 historical publisher.

## Stage Goals

### Stage 1: Normalized Fundamentals CSVs
Primary objective:
- Build normalized yearly fundamentals CSVs for `2006` through `2025`.

Current plan:
1. Use already computed local historical data for `2006-2023` when building the local raw Stage 1 artifacts.
2. Use SimFin API for `2023-2025` inclusive.
3. Normalize both source paths into one canonical quarterly schema.
4. Apply a mandatory unit-normalization pass to the canonical raw fields before publish.
5. Emit one yearly CSV per year.
6. Explicitly document missing rows, missing fields, and unresolved source issues so dataset quality can be improved over time.

Expected outcome:
- A consistent yearly fundamentals dataset that can be consumed without caring which source produced the row.

### Stage 2: Computed Fundamentals Ratios CSVs
Secondary objective:
- Compute derived fundamentals metrics and ratio CSVs from the normalized raw fields only.

Current plan:
1. Read Stage 1 normalized yearly CSVs.
2. Compute deterministic derived metrics from the canonical raw fields.
3. Emit one yearly ratios/features CSV per year.
4. Document failures or invalid computations explicitly where source fields are missing or unusable.

Expected outcome:
- A reproducible yearly feature layer ready for screening and later scoring.

### Stage 3: Company Scoring and Ranking
Future objective:
- Build a scoring pipeline that evaluates companies on fundamentals and produces a yearly ranking.

Status:
- Planned, but not the focus of the current implementation phase.

## Current Implementation Focus
1. Finish Stage 1 normalized yearly fundamentals CSVs.
2. Finish Stage 2 yearly fundamentals-ratio CSVs.
3. Do not treat Stage 3 scoring/ranking as active implementation scope yet.

## Core CSV Contract
The core output shape for both Stage 1 and Stage 2 is:
1. one CSV per year
2. one row per `ticker, year, quarter`
3. sorted in ascending alphabetical order by `ticker`
4. within each ticker, sorted by `quarter` ascending (`1, 2, 3, 4`)

Example row order inside a yearly CSV:
```text
A 2023 1 ...
A 2023 2 ...
A 2023 3 ...
A 2023 4 ...
AAPL 2023 1 ...
AAPL 2023 2 ...
```

Required leading columns for yearly CSVs:
1. `ticker`
2. `year`
3. `quarter`

Stage 1 then appends normalized raw fundamentals columns.
Stage 2 then appends computed metrics columns.

## Source Allocation For This Phase
1. `2006-2023`
   - local historical raw-only Stage 1 path available from `data/raw/Processed-Fundamentals`
2. `2023-2025`
   - use SimFin only
3. Final precedence across overlapping source windows is a downstream integration decision.

## Core Data Flow
1. Build or load the current universe.
2. Load historical normalized-compatible raw fundamentals for `2006-2023`.
3. Fetch fundamentals for `2023-2025` from SimFin.
4. Map both paths into the same canonical quarterly schema.
5. Normalize canonical raw values to one published scale across providers.
6. Write yearly normalized fundamentals CSVs.
7. Compute derived fundamentals ratios from canonical raw fields.
8. Write yearly ratios/features CSVs.
9. Emit explicit QA artifacts describing failures, nulls, and unresolved coverage issues.
10. Later, consume the ratios/features layer for scoring and ranking.

## Architectural Principles
1. Canonical-first:
   - all source paths must land in the same normalized schema before any ratios are computed.
2. Unit-consistent publish layer:
   - provider-native units must not leak into the published yearly raw fundamentals files;
   - the published raw layer uses one shared scale across provider windows.
3. Raw before derived:
   - Stage 1 stores raw canonical fundamentals;
   - Stage 2 computes derived metrics from Stage 1 only.
4. Auditability:
   - each row should remain traceable to its source path, year, and transformation stage.
5. Deterministic keys:
   - quarterly records should use stable keys centered on `ticker`, `year`, and `quarter`.
6. Explicit source windows:
   - local historical raw files are an implemented path for `2006-2023`;
   - SimFin is the intended path for `2023-2025`.
7. Yearly outputs:
   - output artifacts are organized as one CSV per year per stage.
8. Stable ordering:
   - yearly CSVs should be sorted by `ticker`, then `year`, then `quarter`.
9. Explicit failure reporting:
   - the pipeline should document which tickers, rows, and fields are missing or failing so coverage can be improved deliberately.

## Data Zones
1. `data/raw`
   - source or cached source data.
2. `data/processed`
   - normalized canonical yearly outputs and derived yearly ratio outputs.
3. `data/reports`
   - QA, coverage, validation, and diagnostic artifacts.
4. `data/archive`
   - archived legacy provider artifacts that are not part of the active workspace path.
5. `data/warehouse`
   - the native DuckDB analytical store (`research.duckdb`), rebuildable from the Stage 1 CSVs; see `specs/2026-07-22_WAREHOUSE_FOUNDATION_DESIGN.md`.

## Active Inputs For This Phase
1. `data/universe_current.csv`
2. `data/raw/Processed-Fundamentals/*.csv` for the local historical Stage 1 path
3. `data/raw/vendor/simfin_cache/**` for `2023-2025`
4. production SimFin mapping reference:
   - `specs/SIMFIN_STAGE1_MAPPING.md`

## Target Output Families

### Stage 1 Outputs
1. normalized yearly fundamentals CSVs for `2006-2025`
2. each file contains rows shaped as `ticker, year, quarter, <raw fundamentals...>`
3. implemented local historical Stage 1 artifacts:
   - `data/processed/raw_fundamentals_<year>.csv`
   - `data/reports/legacy_raw_coverage_<start>_<end>.csv`
   - `data/reports/legacy_raw_missing_universe_<start>_<end>.csv`
   - `data/reports/legacy_raw_conflicts_<start>_<end>.csv`
4. optional additional QA artifacts for other provider paths
5. implemented SimFin raw fundamentals artifacts for `2023-2025`:
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
6. implemented Stage 1 extension coverage audit artifact:
   - `data/reports/stage1_extension_coverage_<start>_<end>.csv`

### Warehouse Outputs
Analytical store built from the Stage 1 CSVs by `warehouse-rebuild` (native DuckDB;
holds the Stage 2/3 tables as they are implemented). See
`specs/2026-07-22_WAREHOUSE_FOUNDATION_DESIGN.md`.
1. `data/warehouse/research.duckdb` (tables `fundamentals_quarterly`, `fundamentals_annual`, `build_log`; rebuildable, git-ignored)
2. `data/reports/warehouse_health_<start>_<end>.csv`
3. `metrics_trend` table in `research.duckdb` (Stage 2 windowed metrics; built by `metrics-build`)

### Stage 2 Outputs
1. yearly computed ratios/features CSVs for `2006-2025`
2. each file contains rows shaped as `ticker, year, quarter, <computed metrics...>`
3. optional QA artifacts for nulls, denominator issues, and sanity checks

### Stage 3 Outputs (Deferred)
1. yearly scoring CSVs
2. yearly company ranking CSVs

## Out of Scope For This Spec
1. Provider-specific API details
2. Provider-specific field mapping mechanics
3. CLI command names
4. Scoring-model details for Stage 3
