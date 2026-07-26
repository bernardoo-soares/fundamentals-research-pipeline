# SP4 — Buffett Scoring Framework

Status: DESIGN — 2026-07-26 (branch `feature/sp4-buffett-scorer`).

Implements platform spec §7: the `Scorer` protocol, the `BuffettHeuristicScorer`
v1 with graded ramps and the literal book checklist, and the `scores` /
`score_criteria` tables.

Prime Directive: **no false numbers.** A score is a number a human acts on with
money, so every criterion carries its metric value, points, weight, checklist
verdict and reason code, and a score that cannot be computed honestly is not
published.

---

## 1. The blocking finding: the moat component collapses at FY2024

Measured before designing. All 23 criteria metrics from §7.2 now exist (SP3
completed them), but their **availability is not uniform across as-of years**,
because five of them are legacy-era restricted or era-guarded — restrictions
added in PRs #12/#13 in response to real data defects, after §7.2's weights were
written.

Non-null criterion values, FY2022 (462 tickers with trend rows) vs FY2024 (357):

| component | criterion | FY2022 | FY2024 |
|---|---|---|---|
| **Profitability & moat (30%)** | `gross_margin` | 417 | **5** |
| | `gross_margin_ge40_years_10y` | 397 | **6** |
| | `sga_pct_gross_profit` | 343 | **5** |
| | `rd_pct_gross_profit` | 184 | **2** |
| | `dep_pct_gross_profit` | 413 | **5** |
| | `net_margin_ge20_years_10y` | 442 | 343 |
| **Earnings consistency (20%)** | all 4 | 434–461 | 343–371 |
| **Debt discipline (25%)** | `interest_pct_operating_income` | 414 | **4** |
| | other 4 | 390–456 | 279–367 |
| **Capital allocation (15%)** | `capex_pct_net_income_avg10y` | 421 | **4** |
| | other 3 | 295–466 | 221–332 |
| **Growth context (10%)** | `receivables_pct_sales_trend_10y` | 436 | **6** |
| | other 3 | 433–454 | 325–340 |

**At FY2024, five of the six Profitability criteria are empty.** Under §7.4.1's
renormalization rule as written, the 30%-weight component would rest entirely on
`net_margin_ge20_years_10y` — one criterion carrying **six times** its designed
5% share, silently. That is not "the same component measured with less data"; it
is a different measurement wearing the same label.

D7 declares FY2024 the platform's current analysis year, so this is not an edge
case — it is the year a user screens on.

### 1.1 Consequence adopted: a declared minimum component coverage

§7.4.1 handles a component with *zero* applicable criteria (exclude and
renormalize) but not one with *one of six*. This design adds a declared floor:

```yaml
min_component_coverage: 0.50   # a component needs a majority of its criteria
```

A component below the floor is **excluded exactly like a zero-coverage one**, and
top-level weights renormalize across the survivors. Measured separation at
FY2024 makes 0.50 a clean cut rather than a fitted one:

| component | FY2024 coverage | verdict at 0.50 |
|---|---|---|
| profitability_moat | 1/6 = **0.167** | excluded |
| capital_allocation | 3/4 = 0.75 | kept |
| growth_context | 3/4 = 0.75 | kept |
| debt_discipline | 4/5 = 0.80 | kept |
| earnings_consistency | 4/4 = 1.00 | kept |

The next-lowest component sits at 0.75, so the floor has 0.25 of headroom on
either side and no component is near it. At FY2022 every component is at or near
1.00 and nothing is excluded.

### 1.2 What this means for the product, stated plainly

**FY2022 is the last as-of year at which a full Buffett scorecard can be
computed.** At FY2024 the composite is assembled from four components with no
moat measure at all — and moat is the centre of the thesis, not a nice-to-have.
The score is still honest (the exclusion and the coverage ratio are recorded and
badged), but it answers a narrower question.

This is a direct downstream cost of the `cogsq` era defect. It raises
root-causing the remaining `cogsq` residual from "largest open item" to "the
thing blocking the product's headline year", and it should be weighed against
building SP5/SP6 first.

Scores are computed for **every** as-of year — the `scores` table grain is
`(ticker, as_of_year, scorer_name, scorer_version, config_hash)` — so the UI can
offer both, with coverage badges telling the user which year to trust. No
as-of year is special-cased in code.

---

## 2. Architecture

### 2.1 The seam (`contracts/scorecard_schema.py`)

```python
class Scorer(Protocol):
    name: str
    version: str
    def score(self, inp: ScorerInput) -> ScorerOutput: ...
```

Frozen value objects: `ScorerInput` (ticker, as_of_year, metric values with
reason codes, source_family, staleness_quarters), `CriterionResult` (criterion_id,
metric_id, value, points, weight, checklist verdict, reason_code, annotation),
`ScorerOutput` (composite, component scores, coverage, badges, criteria).

`ChecklistVerdict` is a closed `StrEnum`: `PASS | FAIL | NOT_APPLICABLE`.

Scorers read **only** `metrics_*` tables — never raw fundamentals, never prices.
Scores never feed back into metrics, so there is no leakage path by construction
and the metrics layer doubles as a future ML feature matrix.

### 2.2 Config, hash-pinned (`scoring/buffett_scorecard.yml`)

Every weight, ramp anchor, checklist threshold and the coverage floor is a
config value, never a literal in a function (S1.3). `config_hash =
sha256(canonical serialisation)` is stored on every score row, so a config edit
is visible in the data rather than silently changing history.

Canonicalisation is explicit (sorted keys, fixed float formatting, UTF-8) so the
hash is stable across YAML round-trips — hashing raw file bytes would change on
a whitespace edit and is therefore not used.

### 2.3 Pure compute (`scoring/`)

- `ramps.py` — piecewise-linear interpolation over declared `(x, points)`
  anchors. Pure, no I/O.
- `checklist.py` — the literal book rules, each a declared comparison
  (`>`, `>=`, `<`, `<=`) against a threshold.
- `buffett_scorer.py` — assembles criteria into components into a composite.

`scoring/builder.py` is the only module that touches the warehouse, mirroring
`metrics/builder.py`.

### 2.4 Ramps

A ramp is a list of anchors, evaluated by linear interpolation and clamped
outside the ends. `gross_margin` from §7.3:

```yaml
gross_margin:
  ramp: [[0.20, 0], [0.40, 80], [0.60, 100]]
  checklist: {op: ">", threshold: 0.40}
  weight: 0.30
```

Anchors must be strictly increasing in `x`; the loader rejects otherwise, since
a non-monotonic ramp would make points ambiguous. Descending-good metrics (lower
is better: `sga_pct_gross_profit`, `interest_pct_operating_income`,
`lt_debt_payback_years`, `debt_to_equity_adj`, `capex_pct_net_income_avg10y`,
`receivables_pct_sales_trend_10y`) are expressed with **descending points** over
ascending x, so one evaluator serves both directions and no metric needs an
`invert` flag.

## 3. Null handling (§7.4), restated exactly

1. A criterion whose metric is null for any reason is `NOT_APPLICABLE`,
   contributes no points and no weight; remaining weights renormalize **within
   the component**.
2. A component with zero applicable criteria — **or coverage below
   `min_component_coverage` (§1.1)** — is excluded; top-level weights
   renormalize across the survivors.
3. If *every* component is excluded, the composite is **null with a reason
   code**, never 0. A zero composite would rank a company as terrible when the
   truth is that nothing is known about it. This is the value-XOR-reason
   invariant applied at the score grain.
4. `negative_equity_strong_earnings == 1` replaces the `roe` criterion with full
   points and the annotation "negative equity with durable earnings — book
   special case" (§7.4.3). Measured: 23 companies at FY2022 (AZO, ORLY, MCD, PM,
   MO, SBUX, TDG …), a recognisable roster of sustained-buyback franchises.
5. R&D null is `NOT_APPLICABLE`, never penalised and never rewarded (§6.3.2):
   a null `xrdq` cannot be distinguished from "no R&D programme".
6. Badges: `coverage_ratio < 0.60` ⇒ `low_confidence`; `staleness_quarters > 4`
   ⇒ `stale_data`.

## 4. Determinism

Criteria are evaluated in declared config order; components in declared order.
Renormalisation divides by a sum accumulated in that fixed order, so the result
is float-reproducible. No clock, no randomness, no dict-ordering dependence.
`computed_at` is metadata and never influences a value (S3.4).

## 5. Verification plan

1. Golden: a hand-computed scorecard for one real company, every criterion's
   points and the composite derived by hand in the test.
2. Property: composite is null-or-reasoned when all components are excluded;
   points always within `[0, 100]`; weights within a component always sum to 1.0
   after renormalisation (or the component is excluded).
3. Real corpus: score distribution, coverage distribution, badge counts, and the
   FY2022-vs-FY2024 component-exclusion difference.
4. Determinism: scoring the same input twice yields identical rows; the config
   hash is stable across a YAML round-trip.

## 6. Out of scope

1. The UI (SP5/SP6) — this slice writes tables only.
2. Sector scorecards for banks/insurance. D5's renormalisation handles them:
   their inapplicable criteria null out and the coverage badge shows it.
   Publishing `source_family` to Stage 1 would let D5 renormalise deliberately
   rather than incidentally, and is still open.
3. Any `MLScorer`. The protocol exists so it can be added without touching this
   one.
