# Stage 1/2 — `oiadpq` Cross-Era Remediation

Status: IMPLEMENTED — 2026-07-25 (branch `feature/oiadpq-era-remediation`).

**Real-corpus verification (2026-07-25 rebuild, 2006–2024, 33,692 quarters × 9
metrics = 303,228 rows, `metrics-quarterly-1.1`).** Measured, not expected:

*Stage 1.* `oiadpq` in the FY2023 SimFin staged frame is now non-null for
1,429/1,429 general rows and **0/47 banks, 0/59 insurance**. `source_family` is
present in the staged CSV and absent from the published Stage 1 CSV, as designed.
Era resolution is unchanged at 30,660 legacy / 3,032 SimFin rows.

*Audit.* Contradictions **10 → 9**; `oiadpq` is now `divergent_declared`. The
report carries 36 pooled rows plus 108 per-family rows. For `oiadpq`: general
n=1,331 agreement 0.447, banks n=0, insurance n=0 — the two proxy families no
longer produce a comparable value at all. The pooled rate rose 0.422 → 0.447
precisely because the 0.000-agreement bank rows are gone, which is the defect
the per-family split exists to expose.

*Metric.* `interest_pct_operating_income` (version 2): no SimFin-era row retains
a value, and the 24,948 legacy values remain. Exactly **1,491** rows — the ones
that previously held a value — are relabelled `era_not_supported`. The other
1,541 SimFin rows were already reasoned nulls and **keep their more specific
diagnosis**: 856 `mixed_era_window`, 656 `missing_input`, 29 `negative_base`.
Full breakdown of the metric's 33,692 rows:

| era | outcome | rows |
|---|---|---|
| legacy | value present | 24,948 |
| legacy | `missing_input` | 4,636 |
| legacy | `negative_base` | 1,076 |
| simfin | `era_not_supported` | 1,491 |
| simfin | `mixed_era_window` | 856 |
| simfin | `missing_input` | 656 |
| simfin | `negative_base` | 29 |

`apply_era_restriction` relabels only points that still carry a value, matching
`windows.require_single_era`'s `_blocked` helper. An earlier draft of this slice
overrode every prior reason, which flattened those 1,541 rows to
`era_not_supported` and erased two real signals from the reason-code tallies:
that SimFin populates `xintq` sparsely, and that 856 windows are era-contaminated.
Corpus-wide reason counts are therefore unchanged by this slice apart from the
1,491 relabelled rows — `missing_input` 25,702, `negative_base` 5,837,
`zero_denominator` 1,797 and `mixed_era_window` 856 all stand exactly as before.

*Invariants (all of `metrics_quarterly`).* 0 `inf`/`NaN`; 0 value-XOR-reason
violations; 0 quality flags on a null; 0 `era_not_supported` outside the
restricted metric.

*Legacy immutability — the hard gate.* PASSED, proven structurally rather than
by comparison: **0** legacy as-of quarters have a four-quarter window spanning
more than one era (all 1,065 mixed windows end in SimFin quarters), so the
`oiadpq` equivalence flip cannot reach a legacy value; `apply_era_restriction`
is a no-op for legacy rows because legacy is in `supported_eras`; and the
banks/insurance null-out is confined to the SimFin builder. Empirically the row
count is 24,948 before and after with none added or removed, and the KO 2019Q4
golden is unchanged at 0.08974480599563608.

*Method caveat (S4.7).* The plan's original gate compared against a CSV baseline.
That instrument is **lossy** — DuckDB's CSV export truncates doubles (TYL 2015Q3
exported as 0.0001060089400872 against the true 0.00010600894008728069), which
manufactured 17,218 spurious "drifted" rows at ≤7.6e-13 relative, none above
1e-12. The warehouse value matches exact arithmetic (0.012 / 113.19800000000001)
and the CSV value does not. A SQL `SUM` recomputation was also rejected as an
oracle because DuckDB's summation does not associate identically to Python's
`sum()`. Do not use either method for a future byte-identity gate; the
structural argument above is the sound one.

Resolves one of the ten open Stage 1 CONTRADICTIONs recorded in
`specs/2026-07-24_STAGE1_PLAUSIBILITY_AND_ERA_BATCH2_DESIGN.md` and in the
reconciliation report `data/reports/cross_era_reconciliation_2023.csv`.
`oiadpq` is declared `eras_equivalent=True` in
`contracts/field_era_semantics.py` while agreeing on only **42.2%** of the
FY2023 provider overlap — and it is the denominator of a metric that already
ships values, `interest_pct_operating_income`.

Investigation performed 2026-07-25 against the real corpus. Every number in §2
was measured, not assumed (S4.7). The scripts were exploratory and are not
committed; §2 records the findings so they need not be re-derived.

## 1. Goal

Make `oiadpq` mean exactly one thing, and stop `interest_pct_operating_income`
from presenting a cross-era artifact as a business signal. Nothing in this
slice may change a single legacy-era value.

## 2. Root cause — two distinct defects under one verdict

The pooled 42.2% hides two unrelated problems. Splitting the FY2023 overlap
(1,422 comparable rows) by SimFin statement family separates them cleanly:

| family | rows | tickers | agreement | median rel. diff |
|---|---|---|---|---|
| general | 1,319 | 331 | 0.446 | 0.0158 |
| insurance | 51 | 13 | 0.098 | 0.0918 |
| banks | 40 | 11 | **0.000** | **0.8992** |
| *unattributed* | 12 | 3 | 0.583 | 0.0022 |

The 12 unattributed rows matched no SimFin income file on the join key and are
excluded from the per-family conclusions; they are listed for completeness so
the four groups reconcile to the 1,422 comparable rows.

### 2.1 Defect 1 — family proxy substitution (mapping bug, 24 tickers)

`steps/simfin_raw_fundamentals_builder.py` assigns `oiadpq` in the block shared
by all three families (line 338), *before* the family branch. The same builder
deliberately nulls `xintq`, `cogsq`, `xsgaq`, `xrdq`, `actq`, `lctq` for
`banks` and `insurance` because those concepts do not map. `oiadpq` was missed.

SimFin's "Operating Income (Loss)" is a different aggregate in those files:

- **banks:** `Net Revenue after Provisions − Total Non-Interest Expense`
- **insurance:** derived after `Total Claims & Losses`

Neither is Compustat's Operating Income After Depreciation. Publishing them as
`oiadpq` is proxy substitution, which S4.2 classifies as imputation. The
correct output is null.

### 2.2 Defect 2 — irreducible classification boundary (general family)

Measured against the 663 available Compustat columns, no remapping rescues it:

| candidate | agreement | | candidate | agreement |
|---|---|---|---|---|
| `oiadpq` (current) | 0.443 | | `revtq − xoprq − dpq` | 0.453 |
| `oiadpq + spiq` | **0.474** | | `oiadpq − spiq` | 0.267 |
| `piq − nopiq + xintq` | 0.474 | | `oibdpq` | 0.003 |
| `oibdpq − dpq` | 0.448 | | `saleq − cogsq − xsgaq` | 0.008 |

These candidates are measured on the 1,311 general-family rows that also join
to a raw Compustat record, so the `oiadpq` baseline reads 0.443 here against
0.446 in the §2 table (1,319 rows). The eight-row difference is join coverage,
not a discrepancy.

The ceiling is 47.4%, far below the 0.90 threshold. For contrast, the two
successful Stage 1 remediations moved `req` 23.3% → 95.8% (`reunaq`) and
`ceqq` 64.7% → 94.0% (`seqq + mibtq`). Those had a right answer; this does not.

Three hypotheses were tested and **rejected**:

1. **Special/abnormal items.** Subtracting SimFin `Abnormal Gains (Losses)`
   makes it worse (0.443 → 0.307). `spiq` is non-zero on 70.7% of rows and
   SimFin `Abnormal` on 53.9%, but they do not reconcile.
2. **Same cause as `cogsq`.** Spearman correlation of the two relative
   differences is only 0.210; `oiadpq` agrees 50.6% where `cogsq` agrees
   against 44.0% where it does not. Largely independent.
3. **Fiscal-calendar misalignment.** The annual grain is *worse* (0.374 across
   326 full-year tickers, against 0.446 quarterly).

**The decisive measurement:** 73.9% of rows agree under *at least one* of the
candidate definitions, while no single definition exceeds 47.4%. Which
definition reconciles varies per company. That is a per-company judgement about
what belongs above the operating line (restructuring, impairments, gains on
sale, litigation) — not a formula that can be chosen once.

Supporting shape: the legacy/SimFin ratio is symmetric about exactly 1.000
(p25 1.000, p50 1.000, legacy higher on 50.5% of rows), dispersion
p90/p10 = 1.21. So unlike `cogsq` there is no systematic bias to correct, and
unlike `ppentq` (2.17) it is not a gross definitional offset — it is genuine
per-row disagreement.

**Verdict: irreducible by remapping.** The declaration is wrong, not the data.

### 2.3 Effect on the shipped metric

Across the 286 dual-era tickers carrying an `interest_pct_operating_income`
value on both sides of their switch year: median |step| across the boundary
**1.906**, and **83/286 = 29.0%** flip the platform spec's `< 15%` verdict.

Attribution matters. That step is dominated by the **already-declared `xintq`**
divergence (SimFin reports interest net of interest income and with the
opposite sign; 89.8% sign-flip rate), not by `oiadpq`. Representative rows:
AMCR 0.1104 → −0.1880, IP 0.1996 → −0.3063. `oiadpq` contributes a further
~1.6% median denominator error (p90 27%).

The conclusion is that **both legs of this metric break across the era
boundary**, and it is the only metric consuming either field.

### 2.4 Related gap found while measuring (not fixed here)

Platform spec §6.2 declares `interest_pct_operating_income` applies to family
`general` only, and decision D5 calls the interest test "meaningless" for
financials — but the registry enforces no family restriction. SimFin-era bank
rows come out `missing_input` only by luck (`xintq` is nulled there); *legacy*-
era bank rows carry a real value the spec says should not exist. Recorded as an
open item in §7; the era restriction in §3.3 does not address it.

## 3. Scope — four changes

### 3.1 Stage 1 builder: stop publishing a proxy as `oiadpq`

Move the `oiadpq` assignment out of the shared block in
`steps/simfin_raw_fundamentals_builder.py` into the family branch: mapped from
`Operating Income (Loss)` for `general`, `_empty_numeric_series(frame)` for
`banks` and `insurance` — the treatment `xintq`/`cogsq`/`xsgaq` already receive.

This is a null-out, never a remap. SimFin publishes no bank- or
insurance-equivalent of Compustat operating income.

Downstream consequence: those ticker-years lose `oiadpq` in
`fundamentals_annual` too, since annualization requires all four quarters. No
live metric consumes them (SimFin-era `interest_pct` for banks is already
`missing_input` because `xintq` is null there, and §3.3 restricts the metric to
the legacy era regardless).

### 3.2 Era semantics: `oiadpq` is not cross-era equivalent

In `contracts/field_era_semantics.py`, change the `oiadpq` entry from
`_equivalent_usd(...)` to an explicit `FieldEraSemantics` with
`eras_equivalent=False` and a `divergence_note` recording §2.2 — the 47.4%
candidate ceiling, the three rejected hypotheses, the 73.9%-under-some-
definition finding, and the symmetric-ratio shape.

Two consequences follow automatically:

1. The audit verdict moves `CONTRADICTION` → `divergent_declared`, taking the
   open contradiction count **10 → 9**.
2. `metrics/quarterly.ttm_flow` already consults `field_era_semantics`, so a
   TTM sum on `oiadpq` whose four-quarter window is not provably single-era
   becomes `mixed_era_window` with no further code. This protects any future
   metric (`operating_margin` being the obvious one) without additional work.

### 3.3 Quarterly era restriction, and `interest_pct_operating_income`

`metrics_quarterly` has no era-restriction mechanism; `requires_single_era` and
`windows.require_single_era` are trend-grain only. This slice adds one.

**Contract** (`contracts/metrics_quarterly_schema.py`):

```python
@dataclass(frozen=True)
class QuarterMetric:
    metric_id: str
    version: str
    formula: str
    compute: ComputeFn
    supported_eras: frozenset[str] | None = None   # None = every era
```

**Reason code** (`contracts/metric_reason_codes.py`): add
`ERA_NOT_SUPPORTED = "era_not_supported"` to the closed set.

**Pure enforcement** (`metrics/quarterly.py`):

```python
def apply_era_restriction(
    points: list[QuarterPoint],
    supported_eras: frozenset[str] | None,
) -> list[QuarterPoint]:
    """Null every point whose source_era falls outside the declared set.

    A point with unknown provenance (source_era None) is nulled too: refusing
    rather than assuming membership, mirroring windows.require_single_era.
    Returns points unchanged when supported_eras is None.
    """
```

**Central application** (`metrics/quarterly_builder.py`): the builder calls
`apply_era_restriction` once per metric, immediately after `metric.compute`.
Declaration and enforcement cannot drift, because the declared field is the
sole input to the single enforcement call — no registry validator is needed to
tie them, unlike the trend grain's flag/wrapper pair.

**Registry** (`metrics/quarterly_registry.py`): bump
`interest_pct_operating_income` to version `"2"`, set
`supported_eras=frozenset({SourceEra.LEGACY})`, and state the restriction and
its reason in the `formula` string.

Value XOR reason continues to hold: restricted rows are null plus
`era_not_supported`. Expected effect: ~1,491 SimFin non-null values become
reasoned nulls; the 24,948 legacy values are untouched.

### 3.4 Cross-era audit: report agreement per SimFin family

The pooled audit is why a 0%-agreement field looked like a 42% field. Fix the
instrument, not just this one reading:

- `steps/simfin_raw_fundamentals_builder.py` retains `source_family` in the
  **SimFin staged CSV** (`_staging_simfin/raw_fundamentals_<year>.csv`).
  Staging-side provenance only — `STAGE1_OUTPUT_COLUMNS` is unchanged.
- `steps/cross_era_semantic_audit.py` groups the comparison by that column and
  reports per-family agreement alongside the pooled row. The legacy frame has
  no family concept, so family attribution comes from the SimFin side.
- Verdict logic is unchanged: it still keys off the pooled rate, so this slice
  adds evidence without silently changing any field's verdict.

## 4. Versions

| unit | change |
|---|---|
| `interest_pct_operating_income` | version `1` → `2` (computation changed) |
| `METRICS_QUARTERLY_PIPELINE_VERSION` | `metrics-quarterly-1.0` → `1.1` |
| `oiadpq` era declaration | `eras_equivalent` True → False |

A Stage 1 rebuild is required, so the warehouse and both metrics tables are
rebuilt from the CSVs.

## 5. Testing

Synthetic fixtures test mechanics; golden tests pin real hand-verified values
(S4.4). Only item 1 below is a golden test — it pins a real, published value.
Items 2 and 3 exercise the same mechanism with invented fixtures and are
synthetic mechanics tests, not golden tests, per S4.4's distinction.

1. **Golden — legacy value preserved.** KO fiscal 2019
   (`interest_pct_operating_income` = 946/10541 = 0.089744806), hand-derived
   from the published corpus with the arithmetic written into the test,
   asserted unchanged by this slice.
2. **Synthetic — SimFin restricted.** `tests/metrics/test_quarterly_builder.py`
   builds an invented ticker "A" (`xintq=10.0`, `oiadpq=500.0`, SimFin era) and
   asserts null + `era_not_supported` after the change. It proves the
   mechanism, not a real published figure.
3. **Synthetic — bank null.** `tests/simfin/test_simfin_raw_fundamentals.py`
   builds a synthetic BAC frame and asserts null `oiadpq` in Stage 1 output.
   It proves the family-branch null-out, not a real published figure.
4. **Unit — `apply_era_restriction`.** Restricts outside the set; passes
   through when `supported_eras is None`; nulls unknown (`None`) provenance;
   preserves `year`/`quarter`/`source_era` on nulled points.
5. **Property — invariants.** Value XOR reason holds across the new reason
   code; no quality flag survives on a nulled value; `era_not_supported` is a
   member of the closed set.
6. **Contract — era semantics.** `validate_field_era_semantics()` accepts the
   new `oiadpq` entry, and `eras_equivalent=False` requires its
   `divergence_note`.
7. **CLI dispatch** for any command touched (`tests/AGENTS.override.md` rule 5).

## 6. Real-corpus verification (required before merge)

Recorded in this spec and the PR body; not committed as test data.

1. **Legacy immutability — the hard gate.** Every legacy-era
   `interest_pct_operating_income` value is byte-identical to the pre-change
   build. This slice must not move a single legacy number.
2. Reason-code distribution on `metrics_quarterly`, showing ~1,491 new
   `era_not_supported` rows confined to `interest_pct_operating_income`.
3. Contradiction count drops **10 → 9**, with `oiadpq` reported
   `divergent_declared`.
4. The per-family audit table from §3.4, confirming banks 0.000 / insurance
   0.098 / general 0.446 on the pre-change data and `oiadpq` absent for
   banks/insurance after.
5. `oiadpq` null-rate change in Stage 1 output, confirming exactly the
   banks/insurance rows moved and no general-family row did.
6. Invariants across all of `metrics_quarterly`: 0 `inf`/`NaN`, 0
   value-XOR-reason violations, 0 quality flags on nulls.

## 7. Out of scope / open items

1. **The other nine contradictions.** `xsgaq` (0.288), `capxy`, `cheq`,
   `cshfdq`, `cshoq`, `dpq`, `oancfy`, `rectq`, `xrdq`. Measured here:
   `xsgaq` is a *separate* cause from `cogsq` (Spearman 0.210), contradicting
   the earlier assumption that they share a cause-class.
2. **Family restriction on metrics.** §2.4's gap — the registry cannot express
   "general family only", and legacy-era bank rows therefore carry an
   `interest_pct` the platform spec says is meaningless. Needs `source_family`
   published to Stage 1 output, which spec D5 will require anyway to
   renormalize the financials scorecard.
3. **Publishing `source_family`** beyond staging.
4. **`xintq` itself.** Its sign/basis divergence is irreducible and already
   declared; restricting the metric to the legacy era sidesteps it rather than
   resolving it. If a cross-era interest-coverage signal is ever needed, it
   requires a source that states gross interest expense in both eras.
5. **No interest-coverage signal exists for the SimFin era** after this slice.
   That is the intended outcome — an absent signal rather than a false one —
   but it is a real coverage loss and the future UI must show it as such.
6. **The per-family split this slice added immediately found more of the same
   defect class, and it is not fixed here (S4.7 disclosure).** Measured in
   `data/reports/cross_era_reconciliation_2023.csv` — not re-derived, quoted
   verbatim:

   | field | family | agreement | n | median rel. diff | note |
   |---|---|---|---|---|---|
   | `saleq` | banks | 0.000 | 43 | 0.5328 | magnitude ratio 1.374 |
   | `saleq` | insurance | 0.627 | 51 | 0.0046 | |
   | `saleq` | general | 0.906 | 1,333 | 0.0000 | |
   | `saleq` | POOLED | 0.869 | — | — | verdict `agree`: clears its declared 0.80 `min_agreement_rate` |
   | `cheq` | banks | 0.000 | — | — | pooled 0.648 |
   | `cheq` | insurance | 0.000 | — | — | |
   | `rectq` | insurance | 0.100 | — | — | pooled 0.547 |
   | `ivltq` | insurance | 0.000 | — | — | pooled 0.397 |

   `saleq` is the most consequential of the four. It passes the audit as
   `agree` on its pooled 0.869 rate against its declared 0.80 threshold, so no
   guard fires — while banks agree on 0.000 of rows at a median relative
   difference of 0.5328 and a 1.374 magnitude ratio. This is the same
   family-proxy shape as the `oiadpq` defect this slice fixed: a pooled rate
   that clears threshold hides a family with no real agreement at all. `saleq`
   feeds the shipped `net_margin` metric and every `revenue_cagr_*` trend
   metric, so bank revenue currently carries an undisclosed definitional break
   across the provider boundary in numbers that are already live.

   The `saleq` entry's `threshold_justification` in
   `contracts/field_era_semantics.py` asserts "the median relative difference
   is exactly 0.0000." That is true of the general family (0.0000, n=1,333)
   and false of banks (0.5328, n=43). It is a pooled-data claim that the
   per-family split now refutes, and it is left as-is here — this item is
   disclosure only, not a fix.

   This is deliberately **not fixed in this slice**. Each of `saleq`, `cheq`,
   `rectq`, and `ivltq` needs the same measured, per-field investigation
   `oiadpq` received in §2 before its declaration or its metric consumers can
   be changed responsibly. It is the recommended next slice.

   All figures above are measured, not expected (S4.7), and come verbatim from
   `data/reports/cross_era_reconciliation_2023.csv`.
