# Stage 2 — `metrics_quarterly` TTM & Point-in-Time Ratio Engine (slice 1)

Status: DESIGN — 2026-07-25. Not yet implemented.

This slice adds the second Stage 2 grain: `metrics_quarterly` (keyed by
`ticker, year, quarter, metric_id`), holding point-in-time and trailing-twelve-
month (TTM) ratios. It complements the already-shipped `metrics_trend` grain
(keyed by `as_of_year`, 10y/4y/2y windows). It follows the platform design
`specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md` §6.1.4 (TTM rules) and
§6.2 (metric catalog).

## 1. Goal

Compute the per-quarter profitability and leverage ratios a human uses to judge
a business, deterministically and null-honestly, from `fundamentals_quarterly`,
into a new `metrics_quarterly` warehouse table — reusing the existing metric
abstractions (frozen contract + pure compute + declarative registry) and the
cross-era semantics contract that Stage 1 remediation established.

## 2. Scope

### 2.1 Metrics in this slice (9)

Per-quarter-valued metrics from the platform catalog's **Earnings** and
**Debt & balance sheet** groups, plus one balance-sheet presence flag:

| metric_id | Formula | Null policy (reason_code) |
|---|---|---|
| `net_margin` | `niq_ttm / saleq_ttm` | `saleq_ttm == 0` → `zero_denominator` |
| `roa` | `niq_ttm / atq_latest` | `atq ≤ 0` → `zero_denominator`/`negative_base` |
| `roe` | `niq_ttm / ceqq_latest` | `ceqq < 0` → `negative_base`; `== 0` → `zero_denominator` |
| `debt_to_equity_adj` | `ltq / (ceqq + tstkq)`; `tstkq` null → `ltq / ceqq` | denom `< 0` → `negative_base`, `== 0` → `zero_denominator`; tstkq-null path keeps its **value** and sets `quality_flag = tstk_unavailable` (see §5.1) |
| `current_ratio` | `actq_latest / lctq_latest` | `lctq ≤ 0` → `zero_denominator`/`negative_base` |
| `st_lt_debt_ratio` | `dlcq_latest / dlttq_latest` | `dlttq` null/`≤ 0` → `missing_input`/`zero_denominator` |
| `lt_debt_payback_years` | `dlttq_latest / niq_ttm` | `niq_ttm ≤ 0` → `negative_base`/`zero_denominator` |
| `interest_pct_operating_income` | `xintq_ttm / oiadpq_ttm` | `oiadpq_ttm < 0` → `negative_base`, `== 0` → `zero_denominator`; **`xintq_ttm` mixed-era → `mixed_era_window`** |
| `treasury_stock_present` | `1.0` if `tstkq_latest > 0` else `0.0` | `tstkq` null → `missing_input` |

All missing/absent inputs → `missing_input`. Value XOR reason_code on every row.

### 2.2 Explicitly deferred (later slices)

- `gross_margin` (annual & TTM) — uses `cogsq` (non-equivalent) and also has an
  annual-grain variant; needs the annual-grain decision. Deferred.
- `negative_equity_strong_earnings` — hybrid: point-in-time `ceqq < 0` AND a
  10y `niq` window. Belongs with the scoring/negative-equity special case.
- Annual-grain variants of `net_margin`/`gross_margin` (neither quarterly nor a
  10y window). Deferred until the annual-metrics grain is designed.
- Valuation metrics (`pe_ttm`, `market_cap`, `earnings_yield`) — price-dependent,
  computed at query time; separate sub-project.

## 3. Time-basis rules (from platform §6.1.4, pinned here)

1. **TTM flow** (`saleq`, `niq`, `xintq`, `oiadpq`, …): sum of the **4 most
   recent consecutive quarters** ending at the as-of quarter. "Consecutive"
   means the four `(year, quarter)` keys form an unbroken run
   (`quarter_index = year*4 + (quarter-1)` increases by exactly 1 each step).
   Any of the 4 quarters absent, or any required field value null in them, or a
   calendar gap ⇒ null (`missing_input`). **Never scale up fewer than 4.**
2. **Point-in-time stock** (`atq`, `ceqq`, `ltq`, `tstkq`, `dlcq`, `dlttq`,
   `actq`, `lctq`): the value **at the as-of quarter itself** (not "latest in
   the ticker" — every quarter row gets its own point value). Null if absent.
3. A metric row is emitted for **every** `(ticker, year, quarter)` present in
   `fundamentals_quarterly`; TTM metrics at quarters lacking a full trailing
   4-quarter run are null (`missing_input`), not omitted.
4. No `inf`/`-inf`/`NaN` ever reaches a stored value column (property-tested).

## 4. Cross-era handling — the load-bearing decision

The provider boundary (legacy Compustat ↔ SimFin) is **per ticker-year**, and
`source_era` is **uniform within every `(ticker, year)`** (verified on the built
warehouse: 0 of 33,692 ticker-years mix eras). Two consequences fix how era
purity is enforced at this grain:

1. **Point-in-time stock metrics use a single quarter ⇒ a single era.** There is
   no window and therefore no within-row era mixing. `debt_to_equity_adj`,
   `current_ratio`, `st_lt_debt_ratio`, `treasury_stock_present`, and the
   `dlttq_latest` leg of `lt_debt_payback_years` are each internally valid at
   every quarter. They need **no** era guard — a correction to the earlier
   assumption that `st_lt_debt_ratio`/`lt_debt_payback_years` require a
   whole-metric single-era restriction (that restriction is a *trend*-grain
   concern, where a 10y window crosses years).

2. **A TTM window can cross a ticker's era-switch year.** Mixing is only a defect
   when the summed field is **not** cross-era equivalent. So the guard is
   **per-field and automatic**, driven by the existing
   `contracts/field_era_semantics.py`:

   > A TTM sum on a field with `eras_equivalent=False` whose 4-quarter window
   > spans more than one `source_era` yields **no value**, reason
   > `mixed_era_window`. A TTM on an `eras_equivalent=True` field mixes freely
   > (the providers are declared to measure it identically).

   Among the 9 metrics only `interest_pct_operating_income` triggers this: its
   `xintq` leg is non-equivalent (legacy gross vs SimFin net-of-income, 89.8%
   sign-flip). `oiadpq`, `niq`, `saleq` are all equivalent, so their boundary-
   crossing TTMs are permitted. `interest_pct` is this slice's exemplar of the
   guard, exactly as `cogsq`/gross-margin was for the trend-grain guard.

3. **Non-equivalent fields used point-in-time are stored with `source_era` and
   carry a documented cross-era-comparability caveat, not a restriction.** Each
   quarterly value of `st_lt_debt_ratio` (`dlcq`/`dlttq`), `lt_debt_payback_years`
   (`dlttq`), and `interest_pct` (`xintq`) is valid *within* its quarter's era,
   but a value from a legacy quarter and a value from a SimFin quarter for the
   same ticker sit on different bases — a trend chart across the switch year
   shows a basis break, not a business change. These metrics have **soft** book
   anchors ("prefer LT borrowers", "≤ 3–4 years", "< 15%") applied to a single-
   era value, so per the project decision heuristic (restrict only when a hard
   threshold flips *by provider within a comparison*) they are **caveated, not
   era-restricted**. The stored `source_era` lets the UI render the caveat and
   draw the basis break.

## 5. Architecture

Mirrors the shipped trend layer: declare the contract, implement pure compute,
register declaratively, build at the I/O edge.

### 5.1 Contracts (`contracts/`)

- **`metric_reason_codes.py` (NEW).** Extract the shared `ReasonCode`,
  `REASON_CODES`, and a `validate_value_xor_reason(value, reason_code)` helper
  out of `stage2_metrics_schema.py`. Both grains import them from here (S2.6: a
  rule expressed once). `stage2_metrics_schema.py` re-exports `ReasonCode`/
  `REASON_CODES` so existing imports keep working (no value/version change → no
  golden drift). No new reason codes are needed.
- **`metrics_quarterly_schema.py` (NEW).**
  - `QuarterPoint` — frozen dataclass `(year, quarter, value, reason_code,
    quality_flag, source_era)`; `__post_init__` calls
    `validate_value_xor_reason(value, reason_code)` and additionally requires
    that `quality_flag` (if set) is in `QUALITY_FLAGS` **and** accompanies a
    present `value` (a flag annotates a value; it never explains a null).
  - `QUALITY_FLAGS = frozenset({ReasonCode.TSTK_UNAVAILABLE})` — advisory flags
    that co-exist with a value. **`tstk_unavailable` is a quality flag, not a
    reason code.** The platform spec (§6.3) lists it among reason codes, but the
    project's mandatory invariant (S4.5: "value XOR reason_code on every row")
    forbids a reason code from co-existing with a value. `tstk_unavailable`
    annotates *how* a present value was computed (equity add-back omitted), so
    it is modelled as a quality flag on a non-null value. The string constant is
    reused from `ReasonCode.TSTK_UNAVAILABLE` (one literal, DRY).
  - `QuarterMetric` — frozen dataclass `(metric_id, version, formula,
    compute)`. No `requires_single_era` flag: era purity is enforced inside the
    TTM helper by field semantics, not declared per metric.
  - `METRICS_QUARTERLY_COLUMNS`, `create_metrics_quarterly_ddl()`,
    `METRICS_QUARTERLY_PIPELINE_VERSION = "metrics-quarterly-1.0"`.

  Table `metrics_quarterly`: PK `(ticker, year, quarter, metric_id)`; columns
  `value DOUBLE, reason_code VARCHAR, quality_flag VARCHAR, source_era VARCHAR,
  metric_version VARCHAR, computed_at TIMESTAMP, pipeline_version VARCHAR`.
  `source_era` is the era of the as-of quarter (always single-valued) —
  provenance for the UI caveat. `quality_flag` is null except on the
  `debt_to_equity_adj` tstk-fallback path.

### 5.2 Pure compute (`metrics/`)

- **`quarterly.py` (NEW).** Pure, frame-in → `list[QuarterPoint]`. No I/O.
  - `_quarter_index(year, quarter) -> int` = `year*4 + (quarter-1)`.
  - `ttm_flow(frame, field) -> dict[int, TtmResult]` keyed by quarter_index:
    for each as-of quarter with a full consecutive 4-run of present values,
    returns `TtmResult(total, eras=frozenset[str])`; else absent. Era-aware:
    if `semantics_for(field).eras_equivalent is False` and `len(eras) > 1`, the
    result is marked mixed (the combinator nulls it `mixed_era_window`).
  - `stock_at(frame, field) -> dict[int, StockResult]`: the per-quarter value +
    that quarter's `source_era`.
  - Combinators returning `ComputeFn` (frame → `list[QuarterPoint]`), each
    emitting one point per quarter of the ticker:
    `ttm_ratio(num_field, den_field)`, `ttm_over_stock(num_field, den_field)`,
    `stock_over_ttm(num_field, den_field)`, `stock_ratio(num_field, den_field)`,
    `debt_to_equity_adj_metric()` (tstk fallback + flag),
    `presence_flag(field, threshold)`.
  - Denominator policy in one place: `== 0 → zero_denominator`, `< 0 →
    negative_base` (except where a metric's spec says `< 0` is allowed — none in
    this slice). `mixed_era_window` from a non-equivalent mixed TTM leg takes
    precedence over a denominator check on that same leg.
- **`quarterly_registry.py` (NEW).** The 9 `QuarterMetric` entries + a
  `validate_quarterly_registry()` (duplicate-id guard) run at import.

### 5.3 Builder (I/O edge, `metrics/`)

- **`quarterly_builder.py` (NEW).** `build_metrics_quarterly(*, warehouse_path,
  registry, pipeline_version)`: read `fundamentals_quarterly`, group by ticker,
  sort by `(year, quarter)`, run each metric's compute, drop+recreate
  `metrics_quarterly`, insert. Returns `{metrics_quarterly_rows, metric_count,
  per_metric_counts, reason_code_counts}`. Mirrors `build_metrics_trend`;
  `warehouse/connection.py` remains the only opener of the DB.

### 5.4 CLI (`__main__.py`)

- Add subcommand `metrics-quarterly-build --warehouse-path <default research.duckdb>`,
  a thin dispatcher over `build_metrics_quarterly` (no logic in `__main__`).

## 6. Determinism & verification (S3/S4 — non-negotiable)

1. **Pure compute, deterministic order.** Sort each ticker by `(year, quarter)`
   before compute; iterate the registry in declared order. `computed_at` is
   metadata only.
2. **Golden tests — real, hand-verified values.** At least one real golden per
   derived quantity, hand-computed from the published corpus with the
   derivation written down. Concretely (values confirmed against the built
   warehouse and known public figures during implementation, then pinned):
   - `net_margin` for AAPL at the fiscal quarter whose TTM = FY2023
     (`niq_ttm / saleq_ttm`, ≈ 0.25 against Apple's published FY2023 $97.0B /
     $383.3B). The exact quarter key and value are read from the warehouse and
     pinned; the arithmetic is written in the test.
   - `roe`, `roa`, `debt_to_equity_adj` for one large-cap each, same method
     (numerator/denominator quoted from the warehouse rows in the test body).
   - One `tstk_unavailable` case: a SimFin-era row with null `tstkq` →
     `debt_to_equity_adj = ltq / ceqq`, flagged.
   - One `mixed_era_window` case: `interest_pct` at a ticker's era-switch
     boundary quarter where the `xintq` TTM window spans both eras → null.
   - One `negative_base` case: `roe` where `ceqq < 0` → null.
   Synthetic fixtures exercise mechanics (consecutive-run detection, denom
   signs) and are labelled synthetic, not golden.
3. **Property tests (S4.5):** null-in ⇒ null-or-reasoned-out; no non-null from
   null inputs; value XOR reason_code on every row; no `inf`/`-inf`/`NaN` in any
   stored value; a non-equivalent TTM leg spanning >1 era never yields a value.
4. **Real-corpus verification step (S4.6), recorded in the PR:** total rows,
   per-metric non-null coverage, reason-code distribution (esp. how many
   `mixed_era_window` for `interest_pct` and `tstk_unavailable` for
   `debt_to_equity_adj`), and spot-checked named tickers (AAPL, KO, plus a
   negative-equity name). Report measured numbers, caveat the `xintq`/`dlttq`/
   `dlcq` cross-era comparability explicitly.
5. **Versioning:** each metric `version="1"`; any later change to a computation
   bumps that metric's version and must break its golden test.

## 7. Out of scope / open items

- The `xintq`/`dlttq`/`dlcq` cross-era **basis break** is disclosed, not fixed
  (irreducible: providers define the concepts differently and publish no
  reconciling leg). Carried as a documented caveat on those three metrics.
- `saleq_ttm` residual tail (the 0.80 agreement threshold's open item from Stage
  1) still applies to `net_margin`; the plausibility gate already nulls
  impossible negative revenue, so no new handling here.
- No annual-grain metrics, no scoring, no valuation, no UI — separate slices.
