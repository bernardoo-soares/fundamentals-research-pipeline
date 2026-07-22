# Buffett Research Platform — Design Specification

Date: 2026-07-21
Status: Approved design, pending implementation planning
Supersedes: extends `specs/GENERAL_ARCHITECTURE.md` (Stages 2–3) without changing Stage 1 contracts except where explicitly stated.

---

## 1. Purpose and Product Identity

Evolve the existing Stage 1 fundamentals pipeline into an end-to-end research
platform that answers one question: **"which S&P 500 companies are wonderful
businesses by the standards of *Warren Buffett and the Interpretation of
Financial Statements* (Mary Buffett), and how have they behaved?"**

The platform is:
1. a **deterministic metrics engine** (Stage 2) computing Buffett-style
   fundamentals metrics from the published raw layer,
2. an **abstract scoring framework** whose first implementation is a heuristic
   Buffett scorecard (ML-swappable later),
3. an **interactive local UI** (ranked watchlist, transparent score drilldown,
   portfolio-vs-S&P comparison),
4. a **monthly automated refresh job** that ingests newly published data,
   validates it, and atomically updates the research store.

### 1.1 The Prime Directive: no false numbers

This project informs real investment decisions. Every displayed number must be:
- computed by a **pure, versioned, tested function** with a written formula,
- **null with an explicit reason code** when inputs are missing — imputation is
  banned by design,
- traceable in the UI down to the raw input values and fiscal periods that
  produced it,
- reproducible: identical inputs + code version + config ⇒ byte-identical
  outputs.

### 1.2 Non-goals

1. Not a historical alpha backtest. Selecting stocks with today's data from
   today's index membership is look-ahead + survivorship biased; the platform
   never presents historical performance of current picks as strategy
   validation.
2. Not a Bloomberg replacement; breadth/cleanliness beyond the S&P 500 scope is
   out of scope.
3. Not ML-first. ML is a future `Scorer` implementation, nothing more.
4. No intraday or short-horizon data.

---

## 2. Decision Log (agreed 2026-07-21)

| # | Decision | Choice | Rationale |
|---|---|---|---|
| D1 | Analytical storage | **DuckDB + Parquet** (`data/warehouse/`) | Single-file analytical DB; SQL window functions for trend metrics; matches 2026-03-15 direction. CSVs remain the raw audit/publish layer. |
| D2 | UI stack | **Streamlit** | Python-native, same venv/repo, fastest iteration; UI is a read-only viewer so polish ceiling is acceptable. |
| D3 | Refresh trigger | **Windows Task Scheduler → `fundamentals-pipeline refresh` CLI** | OS-native, runs unattended, logs + diff reports; catches up after missed runs. |
| D4 | Scoring style | **Graded ramps + literal book checklist, side by side** | Smooth 0–100 scoring anchored on book thresholds avoids cliff effects; the literal pass/fail checklist is always shown too. |
| D5 | Financials (banks/insurance) | **Score applicable subset, renormalize weights, show coverage badge** | ~90 S&P names; GM/current-ratio/interest tests are meaningless for them; sector scorecards deferred. |
| D6 | Market prices | **In v1** (Stooq EOD, no API key) | Enables P/E, earnings yield, and portfolio-vs-benchmark comparison. |
| D7 | Data freshness | **Accept SimFin free-tier ~12-month delay** | Measured: usable data complete through FY2024; FY2025 = Q1 only. Acceptable for 10-year-window quality analysis. UI displays the horizon permanently. Revisit (SEC EDGAR freshness layer or paid SimFin) is an explicit future option. |
| D8 | Portfolio comparison methodology | **Equal-weight, buy-and-hold, price returns both sides** | Deterministic and symmetric (Stooq is split-adjusted only; `^SPX` is a price index). Labeled as descriptive look-back, never backtest. |

---

## 3. Data Reality Audit (measured 2026-07-21, not assumed)

All numbers below were measured directly from the repository's files. The
audit script becomes a permanent pipeline step (§8.4) so these facts are
re-verified on every refresh.

### 3.1 Horizon and row coverage

| Year(s) | Source | Rows/quarters | Universe coverage |
|---|---|---|---|
| 2006–2022 | legacy Compustat CSVs | 4 quarters | 412–466 of 502 tickers |
| 2023–2024 | SimFin | 4 full quarters | **385–389 of 502 tickers** (~117 names absent from SimFin entirely) |
| 2025 | SimFin | **Q1: 395, Q2: 58, Q3: 28, Q4: 0** | partial |

- SimFin cache freshly pulled 2026-03-29/30; max publish date present
  2026-03-03, yet only 92 of 51,374 income rows published after 2025-06-01
  ⇒ **free-tier ~12-month publication delay confirmed**. This is a property of
  the subscription tier, not staleness.
- Consequence (D7): the platform's "current" analysis year is **FY2024**.
  FY2025 annual metrics will be null via the `incomplete_year` rule (§6.1) —
  no special-casing needed.

### 3.2 Field-level coverage of the published Stage 1 files (selected)

| Field | 2006–2022 (legacy) | 2023–2024 (SimFin) | Notes |
|---|---|---|---|
| `saleq`, `niq`, `cshfdq` | 98–100% | 100% | strong |
| `xintq` | 87–93% | 81–83% | banks/insurance null by design |
| `actq`/`lctq` | 78–83% | 93% | financials don't report; by design |
| `gdwlq` | 84–94% | **0%** | SimFin balance file has **no goodwill column at all** (verified against full header) |
| `tstkq` | 96–99% | **57–58%** | SimFin sparse; fallback policy §6.3 |
| `dvpq` | 98–100% | 75–81% | |
| `capxy` | 97–99% | 95% (2025: 0%) | annual file lags |

### 3.3 Extension-field coverage (fields added, §5)

| Field | Legacy availability (2006–2022) | SimFin availability (2023–2025) | Notes |
|---|---|---|---|
| COGS / gross profit | `cogsq` 99% | `Cost of Revenue` / `Gross Profit` 89% | some general-file companies report no COGS split |
| SG&A | `xsgaq` 78% | `Selling, General & Administrative` 86% | |
| R&D | `xrdq` 47% | `Research & Development` 39% | null usually means **no R&D program**, not missing data → neutral policy §6.3 |
| D&A | `dpq` 89% | 97% via **cashflow stmt** `Depreciation & Amortization`; income-stmt col only **40%** and is never used | |
| Total liabilities | `ltq` 98% (Compustat standard) | `Total Liabilities` 100% (verified in balance header) | removes the `atq − ceqq` approximation |
| Inventories | `invtq` 95% | `Inventories` 66% | enables book's inventory check |
| Receivables | `rectq` 97% | `Accounts & Notes Receivable` 89% | enables book's receivables check |

Figures above are measured on the full published corpus (all 502 universe
tickers, 2006–2025; `data/reports/stage1_extension_coverage_2006_2025.csv`),
superseding the earlier 60-ticker random-sample estimate (3,325 rows,
2006–2023) used during initial design.

---

## 4. Architecture

### 4.1 Repository layout (additions marked +)

```
src/fundamentals_pipeline/
  contracts/    (+) stage2_metrics_schema.py   # metric registry: ids, formulas, versions
                (+) scorecard_schema.py         # score/checklist row contracts
                (+) price_schema.py             # price series contract
  connectors/   (+) stooq_price_client.py       # EOD price fetch, throttled
  steps/        (+) stage1 extension remaps (legacy + simfin builders)
                (+) stage2_metrics_builder.py
                (+) price_ingestion.py
                (+) data_availability_audit.py
  warehouse/    (new) duckdb access layer — the ONLY module opening the .duckdb
                loaders, rebuild, staging/swap, query API for UI
  scoring/      (new) base.py (Scorer protocol), buffett_heuristic.py,
                buffett_scorecard.yml (weights/ramps/thresholds)
  app/          (new) streamlit UI (read-only; sole write: manual_annotations)
data/warehouse/  research.duckdb + parquet partitions   (gitignored)
```

### 4.2 Data flow (strictly one-directional)

```
SimFin cache + legacy CSVs ──Stage 1 builders──▶ data/processed/raw_fundamentals_<year>.csv
Stooq ──price_ingestion──────────────────────────────────┐
raw CSVs ──warehouse_loader (validation gates)──▶ DuckDB │
   fundamentals_quarterly ─▶ fundamentals_annual (derived per §6.1)
   ─▶ metrics_quarterly / metrics_trend  ─▶ scores + checklist
   prices_daily ─▶ portfolio comparison views
DuckDB ──SELECT only──▶ Streamlit UI
```

Rules:
1. CSVs remain the raw source of truth; DuckDB is **rebuildable from scratch**
   at any time via `fundamentals-pipeline warehouse-rebuild`. Corruption is never fatal.
2. No layer reads forward (metrics never read scores; UI computes nothing).
3. Every warehouse row carries `computed_at`, `pipeline_version`; metric rows
   carry `metric_version`; score rows carry `scorer_name`, `scorer_version`,
   `config_hash`.

### 4.3 Warehouse tables (initial)

| Table | Grain | Key content |
|---|---|---|
| `fundamentals_quarterly` | ticker, year, quarter | Stage 1 fields incl. extension; source_family; loaded from published CSVs |
| `fundamentals_annual` | ticker, fiscal_year | derived per annualization rules §6.1, incl. completeness flags |
| `metrics_quarterly` | ticker, year, quarter, metric_id | value, reason_code, metric_version |
| `metrics_trend` | ticker, as_of_year, metric_id | 10y/4y/2y window metrics; window coverage counts |
| `scores` | ticker, as_of_year, scorer_name, scorer_version, config_hash | composite, components, coverage_ratio, staleness_quarters |
| `score_criteria` | + criterion_id | value, points, weight, checklist_verdict, reason_code, input snapshot (json) |
| `prices_daily` | ticker, date | close (split-adjusted), source, ingested_at |
| `benchmark_daily` | symbol(`^SPX`), date | close |
| `manual_annotations` | ticker, created_at | starred flag, free-text note (only UI-writable table) |
| `refresh_log` | run_id | started/finished, gate results, diff summary |

---

## 5. Stage 1 Extension (sub-project 1)

Add **seven** canonical fields to the Stage 1 contract. Published CSV column
order: existing columns unchanged, new fields appended (downstream contract
`validate_stage1_frame_columns` extended accordingly; existing consumers
unaffected because leading columns are stable).

| New field | Legacy source | SimFin source (general family) | Unit class |
|---|---|---|---|
| `cogsq` | `cogsq` | `Cost of Revenue` (fallback: `Revenue − Gross Profit` when only one present; recorded in QA) | monetary |
| `xsgaq` | `xsgaq` | `Selling, General & Administrative` | monetary |
| `xrdq` | `xrdq` | `Research & Development` | monetary |
| `dpq` | `dpq` | cashflow-stmt `Depreciation & Amortization` (income-stmt column is only 40% populated — do not use) | monetary |
| `ltq` | `ltq` | `Total Liabilities` | monetary |
| `invtq` | `invtq` | `Inventories` | monetary |
| `rectq` | `rectq` | `Accounts & Notes Receivable` | monetary |

Notes:
1. Banks/insurance families: these fields map only where the family file
   provides them; otherwise null (`not_applicable_sector` at metric time).
   No proxies are fabricated.
2. All seven are monetary ⇒ SimFin values pass through the existing unit
   normalizer (÷ 1e6) exactly like current monetary fields.
3. `specs/SIMFIN_STAGE1_MAPPING.md` and `specs/CANONICAL_SCHEMA.md` are
   updated in the same change; a full-corpus coverage audit is produced as
   `data/reports/stage1_extension_coverage_<start>_<end>.csv` **before** any
   metric consumes the new fields.
4. Legacy builder change is additive: re-publish 2006–2022 files with the new
   columns; golden-ticker spot checks (AAPL, KO) guard against regression of
   existing columns.

---

## 6. Stage 2 — Deterministic Metrics Engine (sub-project 3)

### 6.1 Time-basis rules (fixed, spec-pinned, test-pinned)

1. **Annualization.** Flow fields (`saleq`, `niq`, `oancfq`, `capxq`, `dvpq`,
   `prstkcq`, `cogsq`, `xsgaq`, `xrdq`, `dpq`, …): fiscal-year value = sum of
   the 4 fiscal quarters; **any missing quarter ⇒ annual value is null**
   (`incomplete_year`). Never scale up 3 quarters. Stock fields (`atq`,
   `ceqq`, `dlcq`, `dlttq`, `req`, `tstkq`, `cheq`, `ltq`, `invtq`, `rectq`,
   `ppentq`, `gdwlq`, share counts): fiscal-year value = fiscal Q4 value; null
   if Q4 missing.
2. **CAGR.** `CAGR_N(V) = (V_end / V_start)^(1/N) − 1` over fiscal years.
   Requires both endpoints non-null; `V_start ≤ 0 ⇒ null (negative_base)`.
   "Revenue growth over past 4 years" ≡ `CAGR_4(annual saleq)`, endpoints
   FY_latest and FY_latest−4.
3. **10-year window metrics.** Window = the 10 fiscal years ending at
   `as_of_year`. Computed only if **≥ 8 of 10** years have the required annual
   value; else null (`insufficient_history`). Consistency = fraction of
   present years meeting the criterion. Trend = fraction of year-over-year
   increases among consecutive present years. No regression fitting in v1.
4. **TTM.** Sum of the 4 most recent available consecutive quarters (flows);
   most recent quarter (stocks). If the 4 quarters are not consecutive ⇒ null
   (`missing_input`). `staleness_quarters` = quarters between latest available
   quarter and the global latest quarter in the warehouse.
5. **Annual EPS** = sum of the 4 quarterly `epspxq`. Documented approximation
   (ignores intra-year share-count drift); acceptable because EPS is used for
   trend/consistency, not valuation precision. Golden tests pin this exact
   definition. (P/E in the UI uses TTM EPS on the same rule.)

### 6.2 Metric catalog

Grain: `metrics_quarterly` for point-in-time/TTM metrics; `metrics_trend`
(keyed by `as_of_year`) for windowed metrics. Every metric has: `metric_id`,
formula string, version, unit, applicability (general / banks / insurance),
era availability.

**Margins & cost discipline** (general family only — n.a. for banks/insurance):

| metric_id | Formula | Book anchor |
|---|---|---|
| `gross_margin` | `(saleq − cogsq) / saleq` (annual & TTM) | > 40% |
| `gross_margin_ge40_years_10y` | fraction of window years with GM > 0.40 | 10-yr consistency |
| `sga_pct_gross_profit` | `xsgaq_annual / gross_profit_annual` | "not high, not low" |
| `rd_pct_gross_profit` | `xrdq_annual / gross_profit_annual` | "should not spend too much" |
| `dep_pct_gross_profit` | `dpq_annual / gross_profit_annual` | low is better (KO ≈ 6%) |

**Earnings** (all families):

| metric_id | Formula | Book anchor |
|---|---|---|
| `net_margin` | `niq / saleq` (annual & TTM) | > 20% is excellent |
| `net_margin_ge20_years_10y` | fraction of window years with NM > 0.20 | each-year history |
| `eps_annual` | Σ quarterly `epspxq` | — |
| `eps_up_year_fraction_10y` | fraction of YoY increases in `eps_annual` | 10-yr upward trend |
| `net_income_up_year_fraction_10y` | same on annual `niq` | upward trend |

**Debt & balance sheet:**

| metric_id | Formula | Book anchor | Applicability |
|---|---|---|---|
| `interest_pct_operating_income` | `xintq_ttm / oiadpq_ttm`, null if `oiadpq_ttm ≤ 0` (`zero_denominator`/`negative_base`) | < 15% | general |
| `current_ratio` | `actq / lctq` | > 1 good (book notes great outliers below 1) | general |
| `lt_debt_payback_years` | `dlttq_latest / niq_ttm`, null if `niq_ttm ≤ 0` | ≤ 3–4 years | all |
| `debt_to_equity_adj` | `ltq / (ceqq + tstkq)`; if `tstkq` null → `ltq / ceqq` flagged `tstk_unavailable`; null if denominator ≤ 0 | ≤ 0.80 great | all |
| `st_lt_debt_ratio` | `dlcq / dlttq` (null-safe) | prefer LT borrowers | all |
| `roa` | `niq_ttm / atq` | high can mean vulnerability — informational, scored gently | all |
| `roe` | `niq_ttm / ceqq`, null if `ceqq ≤ 0` → see special case | consistently high | all |
| `negative_equity_strong_earnings` | `ceqq < 0` AND ≥ 8 of 10 window years positive `niq_annual` | durable-advantage special case | all |

**Capital allocation:**

| metric_id | Formula | Book anchor |
|---|---|---|
| `capex_pct_net_income_avg10y` | `Σ capxy / Σ niq_annual` over window years where both present (≥ 8 required) | < 50% good, < 25% great |
| `retained_earnings_cagr_10y` | `CAGR_10(req)` (Q4 values); `negative_base` handled | steady additions |
| `buyback_years_10y` | count of window years with `prstkcy > 0` | buybacks = good sign |
| `treasury_stock_present` | `tstkq > 0` latest | presence = good sign |
| `dividend_payer_years_10y` | count of window years with `dvpq_annual > 0` | informational |

**Growth & working-capital quality** (all families unless noted):

| metric_id | Formula | Book anchor |
|---|---|---|
| `revenue_cagr_2y/4y/10y` | `CAGR_N(saleq_annual)` | growth context |
| `receivables_pct_sales_trend_10y` | trend of `rectq_q4 / saleq_annual` (down = good) | lower % receivables than peers |
| `inventory_earnings_correspondence_10y` | fraction of window years where inventory YoY and `niq_annual` YoY move the same direction (general family; requires `invtq`) | inventory & earnings on corresponding rise |
| `goodwill_trend` | YoY changes in `gdwlq_q4` | **2006–2022 only** — SimFin provides no goodwill; UI shows "unavailable after 2022 (not provided by source)" |

**Valuation (price-dependent; computed at query time from `prices_daily` + metrics, same determinism rules):**

| metric_id | Formula | Note |
|---|---|---|
| `market_cap` | `close_latest × cshfdq_latest × 1e6` | shares stored in millions |
| `pe_ttm` | `close_latest / eps_ttm`, null if `eps_ttm ≤ 0` | book: never overpay |
| `earnings_yield` | `eps_ttm / close_latest` | equity-bond framing |

Explicitly out of scope (not computable honestly): tax-truthfulness
cross-check vs SEC filings; market-timing signals.

### 6.3 Null & special-value policies

Reason codes (enumerated, closed set):
`missing_input | incomplete_year | negative_base | zero_denominator |
not_applicable_sector | insufficient_history | tstk_unavailable`.

1. **No imputation, ever.** A null input yields a null metric with a reason.
2. **R&D neutrality:** null `xrdq` cannot be distinguished from "no R&D
   program" (e.g. Coca-Cola). The R&D criterion is marked n.a. on null —
   never penalized, never rewarded.
3. **Treasury-stock fallback:** null `tstkq` ⇒ `debt_to_equity_adj` computed
   without add-back, flagged `tstk_unavailable` (affects ~43% of SimFin rows).
4. **Negative equity:** `roe` is null (`negative_base`), and the
   `negative_equity_strong_earnings` flag takes over in scoring (§7.4).
5. Divisions never produce `inf`/`-inf`/NaN leakage — guarded, reasoned nulls.

### 6.4 Determinism machinery

1. **Pure functions**: metrics code is frame-in → frame-out. No I/O, network,
   clock, or randomness. Same input ⇒ same output.
2. **Golden tests**: committed fixtures with hand-computed expected values from
   the real published CSVs for: AAPL (general, buybacks, R&D), KO (general,
   no R&D, dividends), JPM (bank — n.a. cascade), TRV (insurance family),
   plus one negative-equity name if present in-universe (candidate identified
   during implementation from the actual data). Any drift fails CI.
3. **Property tests**: null-in ⇒ null-or-reasoned-out; no non-null from null
   inputs; CAGR sign/symmetry; zero-denominator handling; annualization
   requires exactly 4 quarters.
4. **Metric registry** (`stage2_metrics_schema.py`): every metric declares id,
   formula string (shown in UI tooltips), version, unit, applicability, era.
   The registry is the single source both for computation dispatch and UI
   display — formula shown is formula run.
5. **Reconciliation sanity checks** (warning-level QA, not hard gates):
   `|atq − (ltq + ceqq)| / atq ≤ 5%` else row flagged in data-health report;
   unit-magnitude checks (e.g. AAPL revenue in expected millions range).

---

## 7. Scoring Framework (sub-project 4)

### 7.1 Abstraction

```python
class Scorer(Protocol):
    name: str          # e.g. "buffett_heuristic"
    version: str       # semver; bump on any logic change
    def score(self, inp: ScorerInput) -> ScorerOutput: ...
```

- `ScorerInput`: per-ticker metric vectors (from `metrics_*` tables only —
  scorers never touch raw fundamentals or prices), reason codes, statement
  family, `as_of_year`, staleness.
- `ScorerOutput` rows for `scores` and `score_criteria` (§4.3): composite
  0–100, component scores, per-criterion audit (metric value, points, weight,
  checklist verdict `pass|fail|n.a.`, reason code, raw-input snapshot).
- Reproducibility key: `(scorer_name, scorer_version, config_hash)` where
  `config_hash = sha256(canonical yaml)`. Identical inputs+key ⇒ identical rows.
- **ML seam**: a future `MLScorer` implements the same protocol over the same
  tables; the UI reads `scores` generically with a scorer picker; the metrics
  layer doubles as the feature matrix. Scores never feed back into metrics
  (no leakage by construction).

### 7.2 BuffettHeuristicScorer v1 — components and weights

Config lives in `scoring/buffett_scorecard.yml` (committed; hash-pinned).

| Component | Weight | Criteria |
|---|---|---|
| Profitability & moat | 30% | `gross_margin` (TTM), `gross_margin_ge40_years_10y`, `net_margin_ge20_years_10y`, `sga_pct_gross_profit`, `rd_pct_gross_profit`, `dep_pct_gross_profit` |
| Earnings consistency | 20% | `eps_up_year_fraction_10y`, `net_income_up_year_fraction_10y`, `net_margin` (TTM), `roe` (TTM; replaced by the negative-equity special case when triggered, §7.4.3) |
| Debt discipline | 25% | `lt_debt_payback_years`, `debt_to_equity_adj`, `interest_pct_operating_income`, `st_lt_debt_ratio`, `current_ratio` |
| Capital allocation | 15% | `capex_pct_net_income_avg10y`, `buyback_years_10y`, `retained_earnings_cagr_10y`, `treasury_stock_present` |
| Growth context | 10% | `revenue_cagr_4y`, `revenue_cagr_10y`, `receivables_pct_sales_trend_10y`, `inventory_earnings_correspondence_10y` |

### 7.3 Graded ramps + literal checklist

- Each criterion maps its metric through a **piecewise-linear ramp** anchored
  on the book threshold. Example (`gross_margin`): ≤ 0.20 → 0 pts; 0.40 →
  80 pts; ≥ 0.60 → 100 pts; linear between. All ramps in the YAML config.
- In parallel, the **literal checklist** applies the book's raw rule
  (GM > 40%? interest < 15%? adj D/E ≤ 0.80? payback ≤ 4y? capex < 25%/50%?
  current ratio > 1? …) producing `pass|fail|n.a.` per criterion and a
  headline "N/M applicable criteria passed". Both are stored and both are
  displayed — the graded score ranks, the checklist grounds.

### 7.4 Null handling and special cases in scoring

1. A criterion whose metric is null (any reason) is **excluded**; remaining
   weights renormalize **within the component**; a component with zero
   applicable criteria is excluded and top-level weights renormalize.
2. Every score row records `criteria_coverage` (applicable/total) and derives
   badges: coverage < 60% ⇒ **low confidence**; `staleness_quarters > 4` ⇒
   **stale data**. Badges are prominent in every UI surface (D5).
3. `negative_equity_strong_earnings` true ⇒ the ROE-related criterion is
   replaced by full points + annotation "negative equity with durable
   earnings — book special case", instead of a garbage/null ROE.
4. R&D criterion on null: n.a. (§6.3), excluded, renormalized.

---

## 8. UI (sub-project 5; Streamlit, `app/`)

Global elements: permanent data-horizon banner — *"Fundamentals through
FY2024 (SimFin free tier, ~12-month delay). Last refresh: {date}. {n}/502
universe tickers covered in the current era."* All tables exportable to CSV.

### 8.1 Page ① Ranking

- Table: rank, ticker, name, sector, composite, per-component mini-bars,
  checklist "N/M", badges (low confidence / stale / financial-subset),
  data-through year.
- Controls: scorer picker (future-proof), sector filter, min coverage,
  hide-stale toggle, min score, text search.
- Row multi-select → "Compare vs S&P 500" (page ③) with selection carried.

### 8.2 Page ② Company drilldown — score transparency (hard requirement)

Clicking any score opens its full anatomy; **every number is a door**:

1. **Waterfall**: composite → component contributions (weight × score).
2. **Criterion table** (one row per book rule):
   - the book's rule, quoted ("Interest expense should be < 15% of operating
     income");
   - actual metric value, threshold, points × weight, checklist verdict;
   - **inputs row**: the raw Stage 1 values and their fiscal periods used
     (e.g. `xintq TTM = 412 [2023Q2–2024Q1]`, `oiadpq TTM = 4,962`);
   - the exact formula string from the metric registry;
   - if n.a.: the reason code in plain words ("not applicable: bank — COGS
     not reported").
   Everything hand-verifiable against the published CSVs in under a minute.
3. **Trend charts** (10–20y): gross margin, net margin, EPS, ROE, LT-debt
   payback, retained earnings, capex % NI — each with the book threshold drawn
   as a horizontal line and null years visibly gapped (never interpolated).
4. **Provenance box**: source family, alias applied, quarters present,
   data-through, `scorer_version`, `config_hash`, `pipeline_version`.
5. Valuation strip: latest price (date shown), market cap, P/E (TTM),
   earnings yield — null-honest (`eps_ttm ≤ 0 ⇒ "P/E: n/m"`).

### 8.3 Page ③ Portfolio vs S&P 500

- Input: N selected tickers. Toggle window: 2y / 5y / 10y.
- Chart: indexed to 100 at window start — equal-weight **buy-and-hold**
  portfolio vs `^SPX`. **Price returns both sides, dividends excluded on both
  sides** (symmetric by construction; stated on-chart).
- Per-stock contribution table (start/end price, return, weight drift).
- **Insufficient-history policy**: any ticker lacking a price at window start
  is **excluded from that window**, listed explicitly ("Excluded from 10y
  window: ABNB (IPO 2020-12)") — never silently included from a later date.
- **Printed caveat on the chart**: *"Descriptive look-back of today's
  selection. Selection uses current fundamentals (look-ahead) and current
  index membership (survivorship). This is not evidence of strategy
  performance."*

### 8.4 Page ④ Data health

- Coverage heatmap (ticker × year, quarters present).
- The uncovered-tickers list (~117 names) with reasons where known.
- Extension-field coverage table (live output of the availability audit).
- Last refresh: gate results, diff summary (new quarters, restatements,
  coverage deltas), link to full report file.
- Reconciliation warnings (§6.4.5).

### 8.5 Page ⑤ Watchlist

- Star/unstar from any page; free-text notes with timestamps.
- Backed by `manual_annotations` — the only table the UI writes.

---

## 9. Prices (part of sub-project 6)

1. Source: **Stooq** EOD CSV endpoints (free, no key). Tickers mapped
   (e.g. `AAPL` → `aapl.us`); benchmark `^SPX`.
2. Ingestion: incremental (fetch since last stored date); throttled ≥ 500 ms
   between requests; retry-with-backoff; per-ticker failure isolation (one
   failure never aborts the run; failures listed in refresh report).
3. Validation gates: non-negative prices; date monotonicity; gap detection
   (> 10 trading-day gaps flagged); |daily move| > 50% flagged for review
   (not dropped — flagged).
4. Stored split-adjusted as provided. **Dividend-adjustment is explicitly not
   applied**; the UI labels all return figures "price return". Total-return
   upgrade is future work and must be symmetric (portfolio and benchmark)
   before it ships.
5. Refresh cadence: monthly with the main job (sufficient for the product;
   no intraday ambition).

---

## 10. Monthly Refresh Job (part of sub-project 6)

`fundamentals-pipeline refresh` — one idempotent CLI command:

```
1. SimFin re-pull (quarterly + annual, refresh_days policy)
2. Stage 1 rebuild for the SimFin era (2023→latest)
3. Data-availability audit (regenerates §3 numbers; compares vs previous)
4. Load → STAGING DuckDB (research.duckdb.staging)
5. Stage 2 metrics build (staging)
6. Scores build (staging)
7. Stooq incremental price pull (staging)
8. VALIDATION GATES (hard):
   a. schema contract (all tables, all columns, dtypes)
   b. row-count sanity (no year loses > 2% rows vs previous run)
   c. golden-ticker invariance: settled years (≤ FY2022) byte-identical for
      fixture tickers unless pipeline_version changed
   d. unit-magnitude checks (known-scale spot values)
   e. price gates (§9.3)
9. All pass → atomic swap staging→live (os.replace) + write diff report:
   data/reports/refresh/refresh_<run_id>.md
   (new quarters count, restated values w/ before→after, coverage deltas,
    price failures, gate results)
   Any fail → abort, keep last good DB, write failure report, exit non-zero
10. refresh_log row either way
```

Scheduling: Windows Task Scheduler, monthly, "run as soon as possible after a
missed start" enabled. Registration is scripted:
`fundamentals-pipeline install-refresh-task` emits/registers the scheduled task
(PowerShell `Register-ScheduledTask`) so setup is reproducible.

Manual invocation is identical (`fundamentals-pipeline refresh`), satisfying "run it
whenever I want" with zero drift between manual and scheduled behavior.

---

## 11. Testing Strategy

| Layer | Tests |
|---|---|
| Stage 1 extension | mapping unit tests per provider; golden spot-checks that existing columns are unchanged after re-publish |
| Metrics engine | golden fixtures (hand-computed, §6.4.2); property tests (§6.4.3); annualization/TTM/CAGR edge cases; era-availability (goodwill post-2022 null) |
| Scoring | ramp math unit tests; renormalization under nulls; special cases (negative equity, R&D n.a., bank subset); regression fixture: full scorecard output for fixture tickers pinned per scorer version |
| Warehouse | loader contract tests; rebuild-from-CSV round-trip equality; staging/swap atomicity (failure leaves live untouched) |
| Prices | parser tests on recorded Stooq payloads; gate tests (gaps, spikes); portfolio math golden test (hand-computed 3-ticker example incl. exclusion policy) |
| Refresh | gate-failure simulations; diff-report content tests |
| UI | smoke test (app imports and pages render against a fixture DB); no business logic in UI to test — by design |

Quality gate unchanged: `python -m pytest -q` + `python -m compileall src`.

---

## 12. Build Order (six sub-projects, each with its own ExecPlan)

| # | Sub-project | Depends on | Headline deliverable |
|---|---|---|---|
| 1 | Stage 1 extension | — | 7 new fields in published CSVs (2006–2025) + coverage audit report |
| 2 | Warehouse | 1 | DuckDB layer, loaders, `warehouse-rebuild`, staging/swap |
| 3 | Metrics engine | 2 | full catalog + golden tests + registry |
| 4 | Buffett scorer | 3 | framework + v1 scorecard + config |
| 5 | UI (pages ①②④⑤) | 4 | ranking, drilldown, health, watchlist |
| 6 | Prices + comparison + refresh | 5 | page ③, Stooq connector, `refresh` + Task Scheduler |

Each sub-project follows the repo standard: ExecPlan in `.agent/plans/`,
quality gate green before merge, docs updated in the same change.

---

## 13. Risks and Open Items

1. **SimFin free-tier delay** (accepted, D7): analysis trails ~12 months.
   Revisit triggers: user wants current-year data → options are SEC EDGAR
   freshness layer (repo already contains the ingestion path) or paid SimFin.
2. **~117 universe tickers absent from SimFin era**: scored on legacy history
   with staleness badges. Same revisit options as above could close the gap.
3. **Stooq reliability/coverage**: some tickers may be missing or renamed;
   per-ticker failure isolation + health-page visibility. Fallback provider
   (e.g. Yahoo) only as a deliberate future decision — not silently mixed.
4. **SimFin restatements**: refresh diff report surfaces before→after for any
   changed settled value; golden-ticker gate prevents silent drift of
   published history.
5. **Ticker symbol churn** (renames, delistings in universe refresh): alias
   map is validated and reported per run (existing mechanism).
6. **Approximations, all documented**: annual EPS = Σ quarterly EPS;
   `cogsq` fallback from `Revenue − Gross Profit`; treasury fallback for
   D/E. Each is registry-documented and surfaced in UI tooltips.
7. **Deferred explicitly**: sector-specific scorecards (banks/insurance),
   ML scorer, total-return comparison, SEC freshness layer, DuckDB → anything
   multi-user.

---

## 14. Acceptance Criteria (v1 complete when)

1. `fundamentals-pipeline refresh` runs end-to-end on this machine, green gates, and a
   scheduled task exists.
2. UI shows a full ranking with badges; every score drills down to
   criterion → formula → raw inputs → fiscal periods.
3. Golden tests pin metric values for ≥ 4 hand-verified companies; property
   tests enforce null discipline; the full quality gate is green.
4. Portfolio comparison reproduces a hand-computed 3-ticker example exactly,
   applies the exclusion policy, and displays the caveat.
5. No number anywhere in the UI lacks a traceable formula, version, and
   reason-coded null path.
