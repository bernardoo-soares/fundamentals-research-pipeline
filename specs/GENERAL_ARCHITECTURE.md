# Project Architecture

## Goal
Build a fundamentals pipeline that produces normalized yearly CSV outputs and derived fundamentals-ratio yearly CSV outputs for the current universe, with a later extension for company scoring and yearly ranking.

## Time Horizon
1. Historical normalized base: `2006-2022`
   - Source for this phase: already computed local historical data.
2. Current extension window: `2023-2025`
   - Source for this phase: SimFin API.
3. `2023-2025` should be treated as fully SimFin-driven for the current implementation phase.
4. The local historical path should not be used for `2023` because coverage there is not sufficient for the intended final dataset.

## Stage Goals

### Stage 1: Normalized Fundamentals CSVs
Primary objective:
- Build normalized yearly fundamentals CSVs for `2006` through `2025`.

Current plan:
1. Use already computed local historical data for `2006-2022`.
2. Use SimFin API for `2023-2025` inclusive.
3. Normalize both source paths into one canonical quarterly schema.
4. Emit one yearly CSV per year.
5. Explicitly document missing rows, missing fields, and unresolved source issues so dataset quality can be improved over time.

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
1. `2006-2022`
   - use local historical data
2. `2023-2025`
   - use SimFin only
3. Do not use the local historical path for `2023` in the final dataset for this phase.

## Core Data Flow
1. Build or load the current universe.
2. Load historical normalized-compatible raw fundamentals for `2006-2022`.
3. Fetch fundamentals for `2023-2025` from SimFin.
4. Map both paths into the same canonical quarterly schema.
5. Write yearly normalized fundamentals CSVs.
6. Compute derived fundamentals ratios from canonical raw fields.
7. Write yearly ratios/features CSVs.
8. Emit explicit QA artifacts describing failures, nulls, and unresolved coverage issues.
9. Later, consume the ratios/features layer for scoring and ranking.

## Architectural Principles
1. Canonical-first:
   - all source paths must land in the same normalized schema before any ratios are computed.
2. Raw before derived:
   - Stage 1 stores raw canonical fundamentals;
   - Stage 2 computes derived metrics from Stage 1 only.
3. Auditability:
   - each row should remain traceable to its source path, year, and transformation stage.
4. Deterministic keys:
   - quarterly records should use stable keys centered on `ticker`, `year`, and `quarter`.
5. Explicit source windows:
   - local historical data is the intended path for `2006-2022`;
   - SimFin is the intended path for `2023-2025`.
6. Yearly outputs:
   - output artifacts are organized as one CSV per year per stage.
7. Stable ordering:
   - yearly CSVs should be sorted by `ticker`, then `year`, then `quarter`.
8. Explicit failure reporting:
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

## Active Inputs For This Phase
1. `data/universe_current.csv`
2. local historical data for `2006-2022`
3. `data/raw/vendor/simfin_cache/**` for `2023-2025`

## Target Output Families

### Stage 1 Outputs
1. normalized yearly fundamentals CSVs for `2006-2025`
2. each file contains rows shaped as `ticker, year, quarter, <raw fundamentals...>`
3. optional QA artifacts for coverage, missing rows, missing fields, and unresolved source issues

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
