# Warehouse Foundation — Design Specification

Date: 2026-07-22
Status: Approved design, pending implementation planning
Relation: Implements sub-project 2 (the analytical store) of
`specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md`. Refines decision **D1**:
the store is **native DuckDB tables in a single `research.duckdb`**; Parquet
partitions are deferred (a one-line `COPY ... TO ... (FORMAT parquet)` export
when a real need appears). Stage 2 metrics (sub-project 3) build on top of this
foundation and are out of scope here.

---

## 1. Purpose and Scope

Provide a clean, rebuildable analytical store that the metrics engine, and later
the UI, read through a single seam. This first slice delivers the **fundamentals
layer only**: the raw quarterly fundamentals loaded from the Stage 1 CSVs, and
the derived fiscal-year annual table computed per the annualization rules of the
Buffett design spec §6.1.

### 1.1 In scope
1. A DuckDB access layer that is the ONLY module that opens the `.duckdb` file.
2. `fundamentals_quarterly` — loaded verbatim from the published Stage 1 CSVs
   (`data/processed/raw_fundamentals_<year>.csv`, 2006–2025) plus provenance.
3. `fundamentals_annual` — derived per §6.1 (flow = sum of 4 quarters or null;
   stock = fiscal-Q4 value or null; YTD-annual = Q4 full-year value).
4. `build_log` — one row per rebuild (audit/provenance).
5. Validation gates (hard) and a warning-level data-health report.
6. Atomic `warehouse-rebuild` CLI (build to temp, validate, swap).
7. Tests (synthetic fixtures; real behavior, not mocks).

### 1.2 Out of scope (deferred, named for the next sub-projects)
- All Stage 2 metrics (`metrics_quarterly`, `metrics_trend`), TTM computation.
- The statement-family dimension (general / banks / insurance) — needed by
  metric *applicability*, not by the fundamentals tables. Deferred to the
  metrics sub-project, which must source it (SimFin `us-companies.csv` sector, or
  a GICS mapping) since the Stage 1 CSVs do not carry family.
- Prices, scoring, Streamlit UI.
- Parquet export / partitioning.

## 2. Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| W1 | Storage model | Native DuckDB tables in one `data/warehouse/research.duckdb` | ~30k rows, single user, rebuildable from CSVs — Parquet partitioning is unnecessary machinery at this scale; DuckDB exports Parquet in one line if ever needed. |
| W2 | Annualization compute | SQL inside DuckDB | Idiomatic for the store; aggregation + null-strict guards expressed directly; verified by querying the built DB. |
| W3 | Family dimension | Deferred to metrics sub-project | Fundamentals tables do not need it; Stage 1 CSVs do not carry it. |
| W4 | Rebuild safety | Build to `research.duckdb.tmp`, validate, atomic rename | The live DB is never left half-built; corruption is never fatal (spec §4.2). |
| W5 | Source of truth | Stage 1 CSVs remain canonical | The warehouse is fully rebuildable from them at any time. |

## 3. Module layout

```
src/fundamentals_pipeline/
  contracts/
    fundamentals_annual_schema.py   # NEW: field classification + annual column names (spec-pinned, tested)
  warehouse/                        # NEW package — the ONLY code that opens the .duckdb
    __init__.py
    connection.py     # open_warehouse() context manager + read-only query(sql)->DataFrame; sole opener
    schema.py         # table DDL + provenance columns
    fundamentals_loader.py  # load fundamentals_quarterly from Stage 1 CSVs (validated)
    annualize.py      # fundamentals_quarterly -> fundamentals_annual (SQL, per §6.1)
    validation.py     # hard gates + data-health report
    rebuild.py        # orchestration: staging build -> validate -> atomic swap -> build_log
```

`connection.py` being the single opener is the spec §4.1 rule; downstream layers
(metrics, UI) query through this one seam.

## 4. Field classification (the annualization contract)

Defined in `contracts/fundamentals_annual_schema.py`, following Buffett spec §6.1
verbatim. All 35 Stage 1 raw fields are annualized (even fields no v1 metric uses
yet — clean and future-proof).

**Flow (14) → `<field>_annual` = SUM of the 4 fiscal quarters; null unless all 4
quarters present AND the field is non-null in each:**
`saleq, niq, oiadpq, xintq, txtq, epspxq, oancfq, prstkcq, capxq, dvpq, cogsq,
xsgaq, xrdq, dpq`
(`epspxq` summed per §6.1.5; never scale up 3 quarters.)

**YTD-annual (3) → `<field>_annual` = fiscal-Q4 (full-year cumulative) value;
null if Q4 missing:**
`oancfy, capxy, prstkcy`

**Stock (18) → `<field>_q4` = value at fiscal Q4; null if Q4 row missing/null:**
`actq, lctq, ppentq, gdwlq, ivltq, atq, ceqq, dlcq, dlttq, req, tstkq, cheq,
cshfdq, cshopq, cshoq, ltq, invtq, rectq`

The `_annual` / `_q4` suffixes match the names the Stage 2 metric formulas already
reference (`saleq_annual`, `gdwlq_q4`, `rectq_q4`, …).

## 5. Data model (DuckDB)

Types: `VARCHAR` (ticker, source_era, pipeline_version, run_id, gate/status),
`INTEGER` (year, quarter, fiscal_year, counts), `DOUBLE` (all fields),
`BOOLEAN` (has_q4), `TIMESTAMP` (times). Every warehouse row carries
`computed_at` and `pipeline_version` (spec §4.2).

### 5.1 `fundamentals_quarterly` — grain `(ticker, year, quarter)`

Verbatim load of the 35 Stage 1 raw fields (all `DOUBLE`) keyed by
`(ticker, year, quarter)` (`year` = fiscal year, `quarter` = fiscal 1..4), plus:
- `source_era VARCHAR` — `legacy_compustat` (2006–2022) | `simfin` (2023–2025),
  derived from year.
- `computed_at TIMESTAMP`, `pipeline_version VARCHAR`.
- PRIMARY KEY `(ticker, year, quarter)`.

Column set is validated against `STAGE1_OUTPUT_COLUMNS` on load.

### 5.2 `fundamentals_annual` — grain `(ticker, fiscal_year)`

41 columns: 2 keys + 17 `_annual` (14 flow + 3 YTD) + 18 `_q4` (stock) + 2
completeness + 2 provenance.

```sql
CREATE TABLE fundamentals_annual (
  ticker VARCHAR NOT NULL,
  fiscal_year INTEGER NOT NULL,
  -- 14 FLOW -> _annual (SUM of 4 quarters, null unless 4/4 present & non-null):
  saleq_annual DOUBLE, niq_annual DOUBLE, oiadpq_annual DOUBLE, xintq_annual DOUBLE,
  txtq_annual DOUBLE, epspxq_annual DOUBLE, oancfq_annual DOUBLE, prstkcq_annual DOUBLE,
  capxq_annual DOUBLE, dvpq_annual DOUBLE, cogsq_annual DOUBLE, xsgaq_annual DOUBLE,
  xrdq_annual DOUBLE, dpq_annual DOUBLE,
  -- 3 YTD-annual -> _annual (Q4 full-year value):
  oancfy_annual DOUBLE, capxy_annual DOUBLE, prstkcy_annual DOUBLE,
  -- 18 STOCK -> _q4 (fiscal-Q4 value, null if no Q4):
  actq_q4 DOUBLE, lctq_q4 DOUBLE, ppentq_q4 DOUBLE, gdwlq_q4 DOUBLE, ivltq_q4 DOUBLE,
  atq_q4 DOUBLE, ceqq_q4 DOUBLE, dlcq_q4 DOUBLE, dlttq_q4 DOUBLE, req_q4 DOUBLE,
  tstkq_q4 DOUBLE, cheq_q4 DOUBLE, cshfdq_q4 DOUBLE, cshopq_q4 DOUBLE, cshoq_q4 DOUBLE,
  ltq_q4 DOUBLE, invtq_q4 DOUBLE, rectq_q4 DOUBLE,
  -- completeness flags (spec §4.3):
  quarters_present INTEGER,   -- count of quarter rows for this ticker-year (0..4)
  has_q4 BOOLEAN,             -- whether a fiscal-Q4 row exists
  computed_at TIMESTAMP, pipeline_version VARCHAR,
  PRIMARY KEY (ticker, fiscal_year)
);
```

Annualization SQL shape (per group `(ticker, year)`):
- flow: `CASE WHEN COUNT(*) = 4 AND COUNT(field) = 4 THEN SUM(field) END`
- stock / YTD: `MAX(CASE WHEN quarter = 4 THEN field END)` (null when no Q4)
- `quarters_present = COUNT(*)`, `has_q4 = BOOL_OR(quarter = 4)`

Key uniqueness (§6 gate) guarantees `COUNT(*) = 4` means Q1–Q4 distinct.

Worked example — AAPL FY2024 with quarterly `saleq = 90000/85000/94000/120000`,
`atq = .../.../.../365000`, `capxy = .../.../.../10500` →
`saleq_annual = 389000`, `atq_q4 = 365000`, `capxy_annual = 10500`,
`quarters_present = 4`, `has_q4 = true`. If Q2 is absent:
`saleq_annual → NULL`, `atq_q4 = 365000`, `quarters_present = 3`.

### 5.3 `build_log` — one row per rebuild

```sql
CREATE TABLE build_log (
  run_id VARCHAR, started_at TIMESTAMP, finished_at TIMESTAMP,
  start_year INTEGER, end_year INTEGER,
  quarterly_rows INTEGER, annual_rows INTEGER,
  gate_status VARCHAR,              -- 'passed' | 'failed'
  health_report_path VARCHAR,
  pipeline_version VARCHAR
);
```

## 6. Validation gates and data-health report

`validation.py`, run during rebuild:

**Hard gates (block the rebuild, raise explicit exceptions — no `SystemExit`):**
1. Each loaded year's columns equal `STAGE1_OUTPUT_COLUMNS`.
2. `(ticker, year, quarter)` is unique.

**Warnings (flagged, non-blocking) → `data/reports/warehouse_health_<start>_<end>.csv`:**
1. Reconciliation `|atq − (ltq + ceqq)| / atq ≤ 5%` per row (§6.4.5); rows outside
   are flagged (skip when any input null).
2. Unit-magnitude sanity (e.g. a known ticker's revenue in a plausible millions
   range).
3. Per-year quarterly row counts and annual-completeness stats
   (share of ticker-years with `quarters_present = 4`).

## 7. Rebuild orchestration (atomic)

`rebuild.py`:
1. Build all tables into `research.duckdb.tmp`.
2. Run hard gates; on failure, delete the temp file and raise (the live DB is
   untouched).
3. Run warning checks; write the health report.
4. Write the `build_log` row.
5. Atomically rename `research.duckdb.tmp` over
   `data/warehouse/research.duckdb`.

`data/warehouse/` is under the already-ignored `data/` — the DB is a rebuildable
artifact, never committed.

## 8. CLI

```
python -m fundamentals_pipeline warehouse-rebuild \
  --processed-dir data/processed \
  --warehouse-path data/warehouse/research.duckdb \
  --reports-dir data/reports \
  --start-year 2006 --end-year 2025
```

Prints artifact paths (`warehouse_path`, `health_report_path`) as `key=value`
lines, consistent with the other CLI stages. Missing year files in range raise
`FileNotFoundError` (consistent with the Stage 1 audit step).

## 9. Dependencies

Add `duckdb` (justification: the approved D1 analytical store; single
self-contained wheel, no heavy transitive dependencies), pinned minimally in
`pyproject.toml`. `pandas` already present; no `pyarrow` needed for native
tables. New behavior is test-covered (dependency policy).

## 10. Testing (real behavior, no mocks)

Synthetic Stage 1 CSVs in `tmp_path`, then rebuild and query the DB to assert:
1. quarterly load — rows, columns, dtypes, `source_era` mapping by year;
2. annualization — flow sums 4 quarters; flow nulls on a missing quarter or a
   null field in any quarter; stock takes Q4; stock nulls without Q4; YTD takes
   Q4; `quarters_present` / `has_q4` correct;
3. hard gates — a missing column and a duplicate `(ticker, year, quarter)` each
   fail the rebuild;
4. warnings — a reconciliation breach is flagged in the health report, not
   failed;
5. atomicity — a failing build leaves a pre-existing DB intact;
6. CLI smoke (monkeypatched) prints artifact paths.

Quality gate: `python -m pytest -q`, `python -m compileall src tests`,
`python -m ruff check src tests`. A full real-corpus rebuild is a manual
verification step (like Stage 1's re-publish), since `data/` is git-ignored.

## 11. Spec reconciliation

Update `specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md` D1 and §4 to record
the native-DuckDB / Parquet-deferred decision and reference this document, per
the `specs/` rule to keep specs aligned in the same change.
