# Stage 2 Metrics — Trend Metrics (slice 1) Design Specification

Date: 2026-07-22
Status: Approved design, pending implementation planning
Relation: Implements the first slice of sub-project 3 (Stage 2 metrics engine) of
`specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md`. Reads the
`fundamentals_annual` table built by the warehouse foundation
(`specs/2026-07-22_WAREHOUSE_FOUNDATION_DESIGN.md`) and writes a new
`metrics_trend` table into the same `research.duckdb`.

---

## 1. Purpose and Scope

Stand up the deterministic metrics engine and its first batch of metrics. This
slice delivers **family-agnostic windowed (trend) metrics** computed from the
already-built `fundamentals_annual` table — the pieces that need no statement
family, no TTM, and no prices — while establishing the machinery every later
metric reuses: the metric **registry**, the **reason-code** set, the
`metrics_trend` table, a `metrics-build` action, and the golden/property test
harness.

### 1.1 In scope
1. `contracts/stage2_metrics_schema.py`: reason codes, the `metrics_trend`
   column contract, the `TrendMetric` abstraction, combinators, and the
   registry of slice-1 metrics.
2. `metrics/` package (pure compute, no I/O): window/CAGR helpers + the
   per-metric compute functions.
3. `metrics/builder.py`: reads `fundamentals_annual` and writes `metrics_trend`
   through the warehouse `connection.py` seam (drop + recreate; idempotent).
4. A `metrics-build` CLI (thin dispatcher over the builder function).
5. Golden tests (synthetic fixtures, hand-computed) + property tests.

### 1.2 Out of scope (later slices)
- `metrics_quarterly`, TTM, `staleness_quarters`, point-in-time snapshots.
- Statement-family dimension (general/banks/insurance) and general-only metrics
  (gross margin, SG&A/R&D/dep, current ratio, interest coverage).
- Valuation / prices / volatility, scoring, UI.

## 2. Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| M1 | First-slice metric set | Family-agnostic windowed metrics only | No family dimension or prices needed; reuses `fundamentals_annual` directly. |
| M2 | Grain | `metrics_trend` only (defer `metrics_quarterly`/TTM) | TTM (consecutive-4 + staleness) is the largest new machinery chunk; kept for slice 2. |
| M3 | Compute style | Pure functions (frame-in → rows-out), registry-driven | Spec §6.4; deterministic, testable in isolation. |
| M4 | Extension model | First-class `TrendMetric` + combinators; registry is the single extension point | Adding a metric = one declarative entry (+ a pure fn); most metrics are one-liners. |
| M5 | Integration | Standalone `metrics-build` action reading an existing warehouse | Keeps the merged `warehouse-rebuild` untouched; a later `refresh` chains them. |
| M6 | Callable core | Every action is a plain function returning structured results | CLI is a thin dispatcher; the future UI triggers the same function (platform spec §15.3). |

## 3. Metrics in this slice (all family-agnostic; keyed `(ticker, as_of_year, metric_id)`)

Two time-basis rule families apply (Buffett spec §6.1):

- **CAGR (endpoint rule, §6.1.2):** `CAGR_N(x) = (x[as_of_year] / x[as_of_year−N])^(1/N) − 1`.
  Requires both endpoints non-null; `x[start] ≤ 0 ⇒ null (negative_base)`; a
  missing endpoint ⇒ null (`missing_input`).
- **Window rule (coverage, §6.1.3):** window = the `N` fiscal years ending at
  `as_of_year`; computed only if **≥ ⌈0.8·N⌉** years are present (i.e. ≥8 for
  N=10) else null (`insufficient_history`). Consistency = fraction of present
  years meeting a predicate; trend = fraction of year-over-year increases among
  consecutive present years; count = number of present years meeting a predicate.

| metric_id | version | rule | per-year quantity → aggregation |
|---|---|---|---|
| `revenue_cagr_2y` | 1 | CAGR (N=2) | `saleq_annual` |
| `revenue_cagr_4y` | 1 | CAGR (N=4) | `saleq_annual` |
| `revenue_cagr_10y` | 1 | CAGR (N=10) | `saleq_annual` |
| `retained_earnings_cagr_10y` | 1 | CAGR (N=10) | `req_q4` |
| `eps_up_year_fraction_10y` | 1 | window trend | `epspxq_annual` → fraction of YoY increases |
| `net_income_up_year_fraction_10y` | 1 | window trend | `niq_annual` → fraction of YoY increases |
| `net_margin_ge20_years_10y` | 1 | window consistency | `niq_annual / saleq_annual` → fraction > 0.20 |
| `buyback_years_10y` | 1 | window count | `prstkcy_annual` → count > 0 |
| `dividend_payer_years_10y` | 1 | window count | `dvpq_annual` → count > 0 |

"Present" for a year = the per-year quantity is non-null (which already
encodes annual completeness, since flow `_annual` columns are null on an
incomplete year). Thresholds (e.g. `0.20`, `> 0`) are **declarative fields** on
the metric, not magic numbers — tuning one bumps that metric's `version`.

`as_of_year` is computed over each ticker's fiscal-year range where the window
is dimensionally possible; within that range every `(ticker, as_of_year,
metric_id)` row carries either a `value` or a `reason_code` (exactly one).

## 4. Reason codes (closed set — subset of Buffett spec §6.3 used here)

`insufficient_history` | `negative_base` | `missing_input`

(The full enum lives in the contract for later slices:
`not_applicable_sector`, `zero_denominator`, `incomplete_year`,
`tstk_unavailable`.) **No imputation, ever** — a null value always carries a
reason code, and `value` XOR `reason_code` holds on every row.

## 5. Data model — new table `metrics_trend` (long format, in `research.duckdb`)

```sql
CREATE TABLE metrics_trend (
  ticker VARCHAR NOT NULL,
  as_of_year INTEGER NOT NULL,
  metric_id VARCHAR NOT NULL,
  value DOUBLE,                  -- null when reason_code is set
  reason_code VARCHAR,           -- null when value is present
  window_length INTEGER,         -- 2 / 4 / 10
  window_years_present INTEGER,  -- coverage count in the window
  metric_version VARCHAR,
  computed_at TIMESTAMP,
  pipeline_version VARCHAR,
  PRIMARY KEY (ticker, as_of_year, metric_id)
);
```

## 6. The `TrendMetric` abstraction and combinators (the extension point)

```python
# contracts/stage2_metrics_schema.py
@dataclass(frozen=True)
class TrendMetric:
    metric_id: str
    version: str
    window_length: int
    formula: str                 # human-readable; shown in UI == run (spec §6.4)
    compute: Callable[[pd.DataFrame], list[MetricPoint]]  # pure: one ticker's annual frame -> points
```

`MetricPoint = (as_of_year: int, value: float | None, reason_code: str | None,
window_years_present: int)` with `value` XOR `reason_code`.

Combinators (pure factories in `metrics/windows.py`) turn a per-year quantity
into a `compute` function, so registry entries are almost pure data:

```python
def cagr_metric(series_fn, n): ...                     # endpoint rule
def up_year_fraction_metric(series_fn, n): ...          # window trend
def consistency_fraction_metric(series_fn, predicate, n): ...  # window consistency
def count_years_metric(series_fn, predicate, n): ...    # window count

# series_fn maps a ticker's annual frame -> pd.Series indexed by fiscal_year
def col(name): ...              # e.g. col("saleq_annual")
def ratio(num, den): ...        # e.g. ratio("niq_annual", "saleq_annual")

REGISTRY: tuple[TrendMetric, ...] = (
    TrendMetric("revenue_cagr_10y", "1", 10, "CAGR_10(saleq_annual)",
                cagr_metric(col("saleq_annual"), 10)),
    TrendMetric("net_margin_ge20_years_10y", "1", 10,
                "fraction of window years with niq_annual/saleq_annual > 0.20",
                consistency_fraction_metric(ratio("niq_annual", "saleq_annual"),
                                            predicate=lambda v: v > 0.20, n=10)),
    ...
)
```

**Adding a metric** = append one `TrendMetric(...)` (often composing an existing
combinator). It flows automatically into the table, builder, and CLI — nothing
else changes. **Changing a computation** = edit the function and bump `version`;
the golden test fails on drift until the expected value is updated deliberately.

## 7. Builder and integration (callable core, thin entry point)

```python
# metrics/builder.py
def build_metrics_trend(*, warehouse_path, registry=REGISTRY,
                        pipeline_version=METRICS_PIPELINE_VERSION) -> dict[str, object]:
    """Read fundamentals_annual, run the registry, (re)build metrics_trend.
    Returns structured results: {metrics_trend_rows, metric_count, per_metric_counts}."""
```

- Opens the warehouse via `connection.open_warehouse` (the sole `.duckdb`
  opener), reads `fundamentals_annual` into a DataFrame, groups by `ticker`,
  runs each registry metric's pure `compute`, assembles the long frame, then
  `DROP TABLE IF EXISTS metrics_trend` + recreate + insert (idempotent /
  rebuildable). Raises `FileNotFoundError` if the warehouse or
  `fundamentals_annual` is absent.
- Returns a **structured result dict** (row counts, per-metric counts) so a CLI
  prints it and a future UI button renders it — the same callable, two entry
  points (platform spec §15.3).

CLI (thin dispatcher):
```
python -m fundamentals_pipeline metrics-build --warehouse-path data/warehouse/research.duckdb
```

## 8. Module layout

```
src/fundamentals_pipeline/
  contracts/
    stage2_metrics_schema.py   # NEW: ReasonCode set, metrics_trend contract, TrendMetric, MetricPoint, REGISTRY
  metrics/                     # NEW package (pure compute; no I/O)
    __init__.py
    windows.py                 # pure helpers + combinators (cagr_metric, *_fraction_metric, count_years_metric, col, ratio)
    builder.py                 # reads fundamentals_annual, runs REGISTRY, writes metrics_trend (via connection.py)
  __main__.py                  # NEW subcommand: metrics-build
```

`windows.py` holds the shared window logic (window slice for an `as_of_year`,
coverage/endpoint checks, YoY-increase fraction, consistency fraction, count),
so the metric functions stay one-liners.

## 9. Determinism and testing (the Prime Directive)

- **Pure functions:** metric code is frame-in → rows-out; no I/O, clock, or
  randomness. Same input ⇒ identical output.
- **Contract test:** every `REGISTRY` entry has a unique id, a non-empty
  `formula`, a `window_length` matching its rule, and a callable `compute`.
- **Combinator/unit tests:** `cagr` sign & symmetry (`CAGR_N` then inverse),
  `negative_base` on `start ≤ 0`, `insufficient_history` when < ⌈0.8·N⌉ present,
  up-year fraction on a known series, count/consistency predicates.
- **Golden tests:** synthetic `fundamentals_annual` fixtures with **hand-computed**
  expected values (an AAPL-shaped growth series; a KO-shaped steady-dividend
  series), asserted end-to-end through `build_metrics_trend`. Real `data/` is
  git-ignored, so committed goldens use synthetic fixtures (same pattern as the
  warehouse tests).
- **Property test:** on every produced row, exactly one of `value` /
  `reason_code` is non-null; no non-null value ever arises from null inputs.
- **CLI test:** `metrics-build` dispatches to the builder and prints the
  structured result.
- **Manual real-corpus verification** (no commit, `data/` git-ignored): run
  `metrics-build` on the real warehouse and spot-check a known ticker's
  `revenue_cagr_10y` and `dividend_payer_years_10y` against hand calculation.

Gate: `python -m pytest -q`, `python -m compileall src tests`,
`python -m ruff check src tests`.

## 10. Spec reconciliation

Mark the trend-metrics slice implemented in the Buffett spec §6 / §15.1 and note
the deferred pieces (`metrics_quarterly`/TTM, family, valuation), and add the
`metrics_trend` output to `specs/GENERAL_ARCHITECTURE.md`, per the `specs/`
alignment rule.
