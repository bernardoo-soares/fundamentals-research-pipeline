# Stage 1 Cross-Era Remediation (SP1b) — Design Specification

Date: 2026-07-24
Status: Implemented 2026-07-24 (branch `feature/stage1-cross-era-remediation`)
Relation: Remediates the Stage 1 layer defined in
`specs/2026-07-21_BUFFETT_RESEARCH_PLATFORM_DESIGN.md` §5 and the SimFin mapping
in `specs/SIMFIN_STAGE1_MAPPING.md`. Blocks sub-project 4 (scoring), which must
not consume the defective fields. Sits between SP1 (Stage 1 extension, PR #3)
and the next Stage 2 slice (`metrics_quarterly` + TTM).

---

## 1. Purpose

Stage 1 publishes canonical fields whose meaning silently changes at the
2022/2023 provider boundary, and fills three fields with substituted or imputed
values. Both violate the Prime Directive ("no false numbers") and the
engineering standards in `AGENTS.md` §S1 and §S4. This slice repairs them, and
adds the declarative contract plus measuring step that prevent the next
occurrence.

It also removes a hardcoded era boundary that is discarding usable data for
112 universe tickers in FY2023.

### 1.1 In scope
1. `contracts/field_era_semantics.py` — declared per-era field semantics.
2. `steps/cross_era_semantic_audit.py` + CLI — measures legacy-vs-SimFin
   agreement on the FY2023 overlap and reports contradictions.
3. Semantic fixes: add canonical `dvy`; restore `dvpq` to preferred-only;
   remove three imputing fallbacks and one dead branch.
4. `contracts/era_resolution.py` (declarative rule) + `steps/stage1_era_resolution.py`
   (the publish-boundary merge, §6.2), replacing `_LEGACY_MAX_YEAR = 2022`.
5. Regeneration of the 20 Stage 1 yearly CSVs and warehouse rebuild.
6. Repointing `dividend_payer_years_10y` and version bumps on affected metrics.

### 1.2 Out of scope
- `metrics_quarterly`, TTM, `staleness_quarters` (the next Stage 2 slice).
- Statement-family metrics, prices, scoring, UI.
- Any change to the SEC legacy research path.

---

## 2. Evidence base (measured 2026-07-24, not assumed)

All figures below were measured directly from the local corpora and warehouse.
Per `AGENTS.md` §S4.7, every claim in this section is a measurement; nothing is
projected.

### 2.1 Field semantics, from the vendor's own dictionary
`data/raw/VariablesDescriptor.txt` (Compustat variable descriptor):

| Field | Vendor definition | Consequence |
|---|---|---|
| `dvpq` | "Dividends - Preferred/Preference" | preferred only — **not** total dividends |
| `dvy` | "Cash Dividends" (YTD, cash-flow) | the true total-dividends field |
| `cshopq` | "Total Shares Repurchased - Quarter" | a **share count**, not a currency amount |
| `cshfdq` | "Com Shares for Diluted EPS" | distinct from `cshoq` "Common Shares Outstanding" |
| `prstkcy` | "Purchase of Common and Preferred Stock" | gross repurchase, YTD |
| `tstkq` | "Treasury Stock - Total (All Capital)" | `tstkcq` does not exist in this extract |

There is **no `prstkcq` column in the legacy extract at all** — Compustat
publishes no quarterly purchase-of-stock figure. This is why a substitute was
reached for.

### 2.2 The `dvy` mapping, validated on the FY2023 overlap
274 tickers with both legacy and SimFin FY2023 data:

| Candidate legacy source | agrees within 1% | within 5% | median rel. diff |
|---|---|---|---|
| `dvy` (Cash Dividends, total) | **92.9%** | 94.8% | **0.0000** |
| `cdvcy` (Common only) | 84.6% | 92.3% | 0.0000 |

Exact spot matches against SimFin "Dividends Paid": AAPL 15025 = 15025,
KO 7952 = 7952, MSFT 19800 = 19800, JNJ 11770 = 11770, XOM 14941 = 14941.
PG shows total 8999 against `dvpq` 72.0 — genuine preferred dividends, the
original defect in miniature. `cdvcy` is unpopulated (NaN) for most tickers in
this extract.

**Conclusion:** `dvy` is the correct legacy source for total dividends, and the
two eras are semantically equivalent for it. The residual ~7% disagreement is
enumerated by the audit (§5) and is expected to be fiscal-calendar alignment,
not a mapping error — this is an open item, not a settled claim.

### 2.3 The discarded legacy years
`fundamentals_loader.py:14` hardcodes `_LEGACY_MAX_YEAR = 2022`, routing all
2023+ rows to SimFin exclusively. Measured against the 502-ticker universe,
counting only ticker-years with ≥4 quarters:

| | SimFin (current) | Legacy available | Union achievable | Legacy adds | Overlap |
|---|---|---|---|---|---|
| FY2023 | 380 | 463 | **492 / 502** | **+112** | **351** |
| FY2024 | 378 | 33 | 383 | +5 | 28 |

The recovery is concentrated in **FY2023**. FY2024 — the platform's current
analysis year per platform spec §3.1 — gains only 5 tickers. This slice
therefore restores FY2023 to 98% of universe and creates a 351-ticker
reconciliation window; it does **not** materially repair the current year.

### 2.4 Cross-era divergences found
| Field | Legacy | SimFin | Severity |
|---|---|---|---|
| `dvpq` | preferred dividends | total dividends | **Critical** — fixed here |
| `prstkcq` | share count (via `cshopq` substitution) | currency | **Critical** — fixed here |
| `cshfdq` | diluted-EPS shares, or `cshoq` when absent | diluted shares | **Important** — fixed here |
| `epspxq` | as-reported basic EPS ex-XI | derived `NI(common)/Shares(basic)` | **Important** — irreducible, declared |
| `prstkcy` | gross repurchase (1 negative in 30,187) | net equity flow (488 negative in 3,548) | **Minor** — declared, measured |

---

### 2.5 Measured results after implementation (2026-07-24)

| Acceptance criterion | Target | Measured |
|---|---|---|
| FY2023 universe coverage (>=4 quarters) | >= 480 | **493 of 502** (was 380) |
| `dvy_annual` FY2023 golden values | exact | AAPL **15025**, KO **7952**, MSFT **19800** |
| `dividend_payer_years_10y` mean at as_of 2022 | plausible for a dividend-heavy index | **7.93** (was 1.43) |
| `prstkcq` null across legacy era | all rows | **30,660 of 30,660** |
| `source_era` populated | every row | **0 nulls**; BA/C/COP/CB/AMT served by legacy, AAPL/KO by SimFin |
| `value` XOR `reason_code` in `metrics_trend` | holds | **0 both, 0 neither** of 42,557 |
| `metrics_trend` rows with no matching annual row | 0 | **0** (was 90; era resolution closed the year gaps) |
| `req` cross-era agreement | >= 0.90 | **0.966** (was 0.217; see §2.6) |

Two defects were found by running the audit against the real corpus, both
fixed in commit `032c8cf`:

1. **In the audit itself.** It compared year-to-date fields quarter by
   quarter, but legacy states them cumulatively while SimFin broadcasts the
   annual total into all four quarters, so Q1-Q3 disagreed by construction.
   YTD fields are now compared at Q4 only. `dvy` moved 0.24 -> 0.943.
2. **A new data defect.** `txtq` and `tstkq` were sign-inverted between eras
   (99.1% and 99.9% sign-flip rates, magnitude ratio -1.0; JNJ `tstkq` legacy
   75662 vs SimFin -75662). The SimFin builder applied `_positive_expense` to
   `xsgaq`/`xrdq` but not to these. `tstkq` is the dangerous one:
   `debt_to_equity_adj` adds it back, so the flip computed a different formula
   per era. After the fix, `tstkq` 0.967 and `txtq` 0.937 agreement.

### 2.6 `req` root cause, investigated and fixed

`req` was the worst contradiction that fed a shipped metric, so it was traced
to root cause rather than deferred.

Compustat publishes two retained-earnings lines: `req` ("Retained Earnings",
**adjusted**) and `reunaq` ("**Unadjusted** Retained Earnings"). The identity
`req = reunaq + acomincq` (AOCI) holds within 0.1% for **98.4% of 19,982**
legacy ticker-years, and AOCI is negative in 66.9% of them. SimFin publishes
the as-reported line and has **no AOCI column at all**, so the eras could only
be reconciled on the unadjusted basis. Stage 1 now sources canonical `req`
from Compustat `reunaq`.

| legacy candidate vs SimFin RE (FY2023 overlap) | agree @1% | median rel. diff |
|---|---|---|
| `req` (adjusted) | 23.3% | 0.0427 |
| **`reunaq` (unadjusted)** | **95.8%** | **0.0000** |
| `req - acomincq` | 95.6% | 0.0000 |

`reunaq` was chosen over the algebraically equivalent `req - acomincq` despite
~4pp lower coverage: it is a raw field with an exact semantic match, whereas
the reconstruction is a derivation, and chaining the two would reintroduce the
fallback pattern this slice deleted. The shortfall becomes reasoned nulls.

**Impact before the fix.** 76% of tickers at as_of 2023 and 98% at as_of 2024
cross a provider boundary inside the 10-year window, so
`retained_earnings_cagr_10y` compared an adjusted start against an unadjusted
end. Across 249 affected tickers: mean error **+48.6 bps** annualized, 35.3%
beyond 50 bps, 23.3% beyond 100 bps, and **61% overstated** — a directional
bias, not noise. The tail was disqualifying:

| Ticker | Reported | True | Error |
|---|---|---|---|
| MSI | +28.1% | **-3.8%** | 3192 bps |
| NTAP | +38.5% | +73.1% | -3455 bps |
| ZTS | +68.1% | +43.6% | 2454 bps |
| F | +19.1% | +2.8% | 1630 bps |
| LMT | +12.8% | +0.8% | 1203 bps |

Motorola Solutions read as compounding retained earnings at 28% a year while
they were actually shrinking. Post-fix the metric returns the true values, and
`req` moves to **0.966 agreement** (median relative difference 0.0000).

**17 fields remain in CONTRADICTION** and are genuine open items, listed in
`data/reports/cross_era_reconciliation_2023.csv`. The largest are `cogsq`
(0.14), `dlttq` (0.27), `ppentq` (0.27), `xsgaq` (0.29). These
are unresolved provider definitional differences, **not** silenced: the
contract forbids lowering a threshold without a written justification, so they
stay visible until each is investigated. `saleq` (0.869), `cshfdq` (0.868) and
`xrdq` (0.860) sit just under the 0.90 default and are likely tolerance
calibration rather than defects.

## 3. Decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| R1 | Total-dividends repair | New canonical `dvy` on the YTD-annual pattern; `dvpq` restored to preferred-only | Matches vendor naming (`oancfy`/`capxy`/`prstkcy` precedent); no differencing, no derivation in the raw layer; validated §2.2 |
| R2 | `dvpq` in SimFin era | **null** | SimFin publishes no preferred-dividend field. Honest absence beats a wrong value |
| R3 | Imputing fallbacks | Delete all three; affected values become null | `AGENTS.md` §S4.2 — no imputation, ever |
| R4 | `prstkcq` in legacy era | **null** across 2006–2024 | The source field does not exist. `prstkcy_annual` remains the buyback source |
| R5 | `epspxq` divergence | Declare `eras_equivalent=False`; caveat affected metrics; measure the gap | SimFin publishes no EPS at all — derivation is the only option, so it cannot be fixed, only disclosed |
| R6 | Audit design | Declared contract + empirical verifier | `AGENTS.md` §S4.3; the declaration is what review and future provider swaps check against |
| R7 | Audit authority | CONTRADICTION fails the **audit step**; `warehouse-rebuild` stays warning-only | Rebuild must remain runnable on imperfect data; the audit is the gate run before trusting values |
| R8 | Era resolution precedence | Prefer **SimFin** where the ticker has SimFin coverage; legacy only fills tickers SimFin lacks | See §6.1 — avoids intra-ticker provider switching |
| R9 | Ordering | Contract → audit → semantic fixes → resolution policy | The resolution rule is chosen from measured agreement, not assumed |

---

## 4. Declared era semantics (deliverable 1)

New module `contracts/field_era_semantics.py`. Compute-free, pure data, no I/O —
the same shape as the existing contract modules.

```python
class Basis(StrEnum):          # how the number is stated over time
    DISCRETE_QUARTER = "discrete_quarter"
    YEAR_TO_DATE     = "year_to_date"
    POINT_IN_TIME    = "point_in_time"

class Unit(StrEnum):
    USD_MILLIONS = "usd_millions"
    SHARES_MILLIONS = "shares_millions"
    USD_PER_SHARE = "usd_per_share"

@dataclass(frozen=True)
class EraSource:
    column: str          # provider's own column name
    meaning: str         # the provider's own definition, quoted
    unit: Unit
    basis: Basis
    derived: bool = False    # True when the builder computes it

@dataclass(frozen=True)
class FieldEraSemantics:
    field: str
    legacy: EraSource | None     # None = not available in that era
    simfin: EraSource | None
    eras_equivalent: bool
    divergence_note: str = ""
    # Two distinct declarative thresholds (AGENTS.md §S1.3). Keeping them
    # separate matters: the first is per-value, the second per-field.
    value_tolerance: float = 0.01      # a row "agrees" within this rel. diff
    min_agreement_rate: float = 0.90   # required fraction of agreeing rows
    threshold_justification: str = ""  # why this rate, citing measurement

FIELD_ERA_SEMANTICS: tuple[FieldEraSemantics, ...] = (...)
```

Invariants, enforced by contract tests:
1. Every field in `STAGE1_OUTPUT_COLUMNS` has exactly one entry.
2. `eras_equivalent=True` requires both eras non-None and identical `unit` and
   `basis`. A unit or basis mismatch with `eras_equivalent=True` is a contract
   error, caught at import time — this alone would have caught `dvpq`.
3. `eras_equivalent=False` requires a non-empty `divergence_note`.
4. Any `min_agreement_rate` below the 0.90 default requires a non-empty
   `threshold_justification`. Thresholds may never be loosened silently to make
   a failing audit pass.

`dvy` is declared with `min_agreement_rate = 0.90`, justified by the measured
92.9% in §2.2. Setting the common default to 0.95 would have failed the very
field this slice validated — the threshold is chosen from the measurement, and
the residual 7% is carried as the open item in §10.5 rather than hidden by a
loosened bound.

---

## 5. Cross-era reconciliation audit (deliverable 2)

New step `steps/cross_era_semantic_audit.py`, CLI `cross-era-audit`. Callable
core returning a structured result; the CLI is a thin dispatcher
(`AGENTS.md` §S2.5).

**Method.** For the FY2023 overlap (351 tickers), build the legacy-sourced and
SimFin-sourced canonical frames independently, join on
`(ticker, year, quarter)`, and per field compute:

- `n_compared`, `null_rate_legacy`, `null_rate_simfin`
- `agreement_rate` — fraction within the field's `agreement_tolerance`
- `median_rel_diff`, `p90_rel_diff`
- `sign_flip_rate` — fraction where the two eras disagree on sign
- `magnitude_ratio` — median(legacy)/median(simfin), catching unit errors

**Verdicts** (closed set, mirroring the reason-code pattern):
`agree` | `divergent_declared` | `CONTRADICTION` | `insufficient_overlap`.

A field declared `eras_equivalent=True` whose `agreement_rate` falls below its
declared `min_agreement_rate` is a **CONTRADICTION**.

Failure propagation follows `AGENTS.md` "no `SystemExit` in library code": the
callable core returns a structured result containing the per-field verdicts and
raises `CrossEraContradictionError` (a `core.exceptions` subclass) when any
CONTRADICTION is present; only the CLI translates that into a non-zero exit
code. Output: `data/reports/cross_era_reconciliation_<year>.csv`, written
before the raise, so a failing run still leaves the evidence on disk.

Note the method's limit, stated explicitly per §S4.7: the overlap exists only
for FY2023 (and 28 tickers in FY2024). Fields absent from one era in that window
yield `insufficient_overlap`, not `agree` — absence of evidence is never
recorded as agreement.

---

## 6. Era resolution policy (deliverable 4)

New module `contracts/era_resolution.py`. Replaces the `_LEGACY_MAX_YEAR = 2022`
constant with a declared rule.

### 6.1 Precedence, and why
Rejected: "prefer legacy wherever available." Legacy covers FY2023 well (463
tickers) but FY2024 barely (33). Preferring legacy would give a ticker legacy
FY2023 and SimFin FY2024 — **relocating the provider discontinuity into the
middle of that ticker's series**, precisely the defect class this slice exists
to remove.

Adopted: **per-ticker provider continuity.** For years ≥ 2023, a ticker is
served by SimFin if SimFin covers it; otherwise by legacy. A ticker is never
served by both within the 2023+ window. The 112 recovered tickers are served by
legacy, their series ending FY2023, which surfaces honestly as staleness rather
than as absence.

### 6.2 Where the resolution happens, and the merge mechanics

This is the part the first draft of this spec omitted, and it is the largest
implementation risk in the slice. Today `legacy-raw-stage1` (2006–2023) and
`simfin-raw-fundamentals` (2023–2025) both write
`data/processed/raw_fundamentals_2023.csv`; whichever runs last silently wins.
Under R8 that file must instead hold rows from **both** providers.

Adopted: resolution happens at the **Stage 1 publish boundary**, in a new step
`steps/stage1_era_resolution.py`, which consumes the two builders' frames and
emits the single canonical yearly CSV. Rejected alternative: resolving inside
the warehouse loader, which would make the CSVs no longer the source of truth
and violate platform spec §4.2 rule 1.

Consequences:
1. **`source_era` becomes a published Stage 1 column**, appended to
   `STAGE1_OUTPUT_COLUMNS`. It is currently synthesised by the warehouse loader
   from the year — precisely the hardcoded inference being removed. Publishing
   it satisfies the standing rule "preserve auditability: include source
   metadata (source tag/version)" and makes the loader read provenance instead
   of guessing it.
2. Resolution is **whole-ticker-year, never row-by-row**: a `(ticker, year)`
   is served entirely by one provider. Mixing providers inside one fiscal year
   would corrupt every flow field, since annualization sums four quarters.
3. A ticker-year served by neither provider at ≥4 quarters is simply absent —
   never partially filled.
4. The step emits `data/reports/stage1_era_resolution_<year>.csv` recording the
   provider chosen per ticker and why, so the decision is auditable.

### 6.3 Provenance
`source_era` is populated per row from the resolution decision rather than
inferred from the year. `_LEGACY_MAX_YEAR` is deleted. `warehouse-rebuild`
gains a per-era row-count summary, and `fundamentals_loader` reads the
published `source_era` column instead of computing one.

---

## 7. Contract and downstream impact

1. `STAGE1_OUTPUT_COLUMNS` gains `dvy` (appended to `SUPPORT_RAW_FIELDS`,
   preserving leading-column stability per platform spec §5) and `source_era`
   (§6.2), which is provenance metadata rather than a raw field and is
   therefore appended last, after all raw-field groups.
2. `YTD_ANNUAL_FIELDS` gains `dvy` → `dvy_annual` = Q4 value.
3. `fundamentals_loader._validate_columns` enforces strict column equality, so
   **all 20 yearly CSVs must be regenerated** and the warehouse rebuilt. Both
   corpora are on disk (1,488 legacy CSVs; SimFin cache incl.
   `us-cashflow-annual.csv`) — compute only, no network, no API key. The
   loader stops synthesising `source_era` and reads the published column;
   `QUARTERLY_RAW_FIELDS` is unchanged, since `source_era` is already a
   `fundamentals_quarterly` column.
4. Registry: `dividend_payer_years_10y` repoints to `col("dvy_annual")`, its
   caveat is removed, and its `version` bumps `1` → `2`.
5. `eps_up_year_fraction_10y` and `net_margin_ge20_years_10y`: unchanged
   computation; `epspxq` divergence caveat added to the former's `formula`
   string with the measured divergence figure from §5.
6. Values that legitimately become null: `prstkcq` (all legacy years),
   `cshfdq` where the source lacked it, `dvpq` (all SimFin years).

---

## 8. Testing strategy

Per `AGENTS.md` §S3 and §S4.4–S4.6:

1. **Contract tests** — the §4 invariants, including the unit/basis mismatch
   check that would have caught `dvpq`.
2. **Golden tests, real hand-verified values** (§S4.4) — `dvy_annual` pinned to
   the measured figures: AAPL FY2023 = 15025, KO = 7952, MSFT = 19800.
   These are real published values, not synthetic fixtures.
3. **Property tests** — no imputation: for every removed fallback, a null input
   yields a null output; no `inf`/`NaN` reaches a stored column.
4. **Regression test** — a fixture reproducing the `prstkcq ← cshopq`
   substitution must now produce null, pinning the defect closed.
5. **Audit tests** — synthetic two-era frames exercising each verdict,
   including a deliberate unit error asserting `CONTRADICTION`.
6. **Determinism test** — building twice yields byte-identical CSVs (§S3.1).
7. **Real-corpus verification** (§S4.6, manual, no commit): row counts per era,
   FY2023 coverage reaching ~492, `dividend_payer_years_10y` rising to a
   plausible level for a dividend-heavy index, and the audit report reviewed
   field by field.

## 9. Acceptance criteria

1. `python -m pytest -q`, `python -m compileall src tests`,
   `python -m ruff check src tests` all clean.
2. No `fillna`-style substitution remains in the Stage 1 builders except the
   two legitimate accounting identities (`cogsq` from Revenue − Gross Profit;
   ticker from filename), each documented in the era-semantics contract.
3. `cross-era-audit` runs clean, with every `CONTRADICTION` either fixed or
   reclassified as a declared divergence with a written justification.
4. FY2023 universe coverage ≥ 480 tickers with ≥4 quarters.
5. `dividend_payer_years_10y` reads plausibly across the full 10-year window.
6. No hardcoded era boundary remains in `warehouse/` or `steps/`.

## 10. Known limitations (stated, not hidden)

1. The reconciliation window is FY2023 only; FY2024 has 28 overlapping tickers,
   too few to be authoritative.
2. `epspxq` cannot be reconciled — SimFin publishes no EPS. The divergence is
   disclosed and measured, never silently corrected.
3. The 112 recovered tickers end at FY2023 and will read as one year stale
   against SimFin-served tickers. This is honest, and the UI must show it.
4. FY2024 coverage remains ~383 of 502. Closing that gap needs a different data
   source and is not attempted here.
5. ~7% of tickers show >1% disagreement between legacy `dvy` and SimFin
   "Dividends Paid" in FY2023 (§2.2). The suspected cause is fiscal-calendar
   alignment, but this is **unverified**. The audit enumerates these tickers;
   investigating them is a follow-up, not a claim settled by this slice.
6. Resolution is whole-ticker-year (§6.2.2), so a ticker whose two providers
   each cover part of a fiscal year gets only the fuller provider's data —
   never a stitched year.
