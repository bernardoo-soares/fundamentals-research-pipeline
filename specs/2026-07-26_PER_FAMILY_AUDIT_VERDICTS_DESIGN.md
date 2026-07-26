# Stage 1 — Enforceable Per-Family Audit Verdicts

Status: IMPLEMENTED — 2026-07-26 (branch `feature/per-family-audit-verdicts`).

**Real-corpus verification (2026-07-26).** Measured, not expected:

*Audit report, FY2023.* 144 rows — 36 pooled, 108 per-family. **Null verdicts
fall from 108 to 0**: three quarters of the report previously carried no verdict
at all. Contradiction set is **unchanged at 9 fields** (`capxy`, `cheq`,
`cshfdq`, `cshoq`, `dpq`, `oancfy`, `rectq`, `xrdq`, `xsgaq`); `saleq` does not
join, because insurance is now explicitly declared at 0.50 and measures 0.627.

Verdicts by row scope, covering the 108 rows that were previously unjudged:

| scope | agree | CONTRADICTION | divergent_declared | insufficient_overlap |
|---|---|---|---|---|
| `all` (pooled) | 12 | 9 | 9 | 6 |
| general | 12 | 9 | 9 | 6 |
| banks | 8 | 2 | 4 | 22 |
| insurance | 8 | 2 | 5 | 21 |

*Enforcement blast radius, measured before declaring the override.* With
per-family verdicts live and no override declared, the audit failed on **23 rows
across 10 fields** — the 9 pre-existing pooled contradictions plus exactly the 14
family rows predicted in §2, with `saleq/insurance` the single new field. After
declaring the insurance threshold: 22 rows, 9 fields. The prediction in §2 held
exactly.

*`saleq` after the change.* pooled `agree` 0.896, general `agree` 0.906,
insurance `agree` 0.627 against its declared 0.50, banks
`insufficient_overlap` (n=0, deliberately nulled in PR #10 — correctly raises
nothing).

*No published value moved.* The staged SimFin frame
`_staging_simfin/raw_fundamentals_2023.csv` is **byte-identical** across the
`SourceFamily` migration (md5 `4f615dd51ca801d3db8e740a165556b7` before and
after a full rebuild). Warehouse row counts and the `metrics_quarterly`
reason-code distribution are unchanged: 33,692 / 8,423 / 42,557 / 303,228, with
`missing_input` 25,784, `negative_base` 5,837, `zero_denominator` 1,797,
`era_not_supported` 1,491, `mixed_era_window` 856.

*Gate.* 268 tests pass (245 at branch point, +23), `ruff check src tests` clean,
`compileall` clean.

Closes the masking mechanism recorded as the top open item in
`2026-07-26_FAMILY_PROXY_REMEDIATION_DESIGN.md` §7.3: per-family reconciliation
rows are written with `verdict = None`, so a SimFin statement family sitting
below its field's declared `min_agreement_rate` raises nothing as long as the
pooled rate clears it. Nulling bad data in PRs #9 and #10 removed two symptoms;
it did not fix an instrument that cannot fail.

Prime Directive: **no false numbers.** Every rate quoted here was measured on
the FY2023 overlap; none is expected or inherited.

---

## 1. The defect

`steps/cross_era_semantic_audit.py::reconcile_frames` computes a full metric row
per family, then overwrites its verdict:

```python
family_row = _field_row(left[mask], right[mask], field, source_family=family)
family_row["verdict"] = None          # <-- the defect
```

and `run_cross_era_audit` collects contradictions only from the pooled row:

```python
pooled_rows = report[SOURCE_FAMILY_COLUMN] == POOLED_FAMILY
contradictions = report.loc[pooled_rows & (report["verdict"] == ...)]
```

A family can therefore disagree arbitrarily badly and the audit still exits
zero for that field. This is the exact shape that let `oiadpq` (banks 0.000)
and then `saleq` (banks 0.000 on a passing pooled 0.869) survive.

## 2. Measured blast radius of enforcement

Every per-family row on an `eras_equivalent=True` field whose agreement falls
below the field's declared threshold, FY2023 (14 rows):

| field | family | rate | threshold | n | pooled verdict |
|---|---|---|---|---|---|
| `capxy` | general | 0.544 | 0.90 | 327 | CONTRADICTION |
| `cheq` | general | 0.692 | 0.90 | 1326 | CONTRADICTION |
| `cshfdq` | general | 0.867 | 0.90 | 1333 | CONTRADICTION |
| `cshfdq` | insurance | 0.863 | 0.90 | 51 | CONTRADICTION |
| `cshoq` | banks | 0.721 | 0.90 | 43 | CONTRADICTION |
| `cshoq` | general | 0.773 | 0.90 | 1333 | CONTRADICTION |
| `cshoq` | insurance | 0.667 | 0.90 | 51 | CONTRADICTION |
| `dpq` | banks | 0.724 | 0.90 | 29 | CONTRADICTION |
| `dpq` | general | 0.781 | 0.90 | 1244 | CONTRADICTION |
| `oancfy` | general | 0.876 | 0.90 | 331 | CONTRADICTION |
| `rectq` | general | 0.566 | 0.90 | 1218 | CONTRADICTION |
| **`saleq`** | **insurance** | **0.627** | **0.80** | **51** | **`agree` (0.896)** |
| `xrdq` | general | 0.860 | 0.90 | 499 | CONTRADICTION |
| `xsgaq` | general | 0.288 | 0.90 | 1162 | CONTRADICTION |

**Enforcement adds exactly one new contradicting field: `saleq`.** The other 13
rows belong to fields whose pooled row already raises, so they add diagnostic
attribution, not new failures. That is what makes this slice tractable.

### 2.1 Small-n breaches are not noise — measured, not assumed

The design of this slice initially assumed that small families (banks n=29–43,
insurance n=21–51) would breach a 0.90 threshold on sampling noise alone, and
that the gate would therefore need to be statistical. **That assumption was
refuted by measurement.** Binomial one-sided probability of observing the
measured agreement or worse, given a true rate equal to the threshold:

| row | n | observed | threshold | P(≤observed \| true=threshold) | |
|---|---|---|---|---|---|
| `dpq` banks | 29 | 0.724 | 0.90 | 6.3e-03 | significant |
| `cshoq` banks | 43 | 0.721 | 0.90 | 7.9e-04 | significant |
| `cshoq` insurance | 51 | 0.667 | 0.90 | 5.2e-06 | significant |
| `saleq` insurance | 51 | 0.627 | 0.80 | 3.3e-03 | significant |
| `cshfdq` insurance | 51 | 0.863 | 0.90 | 2.5e-01 | noise-compatible |
| `oancfy` general | 331 | 0.876 | 0.90 | 9.0e-02 | noise-compatible |

12 of the 14 breaches are significant at p<0.05, most overwhelmingly so: the
observed rates sit far below threshold, not marginally below. Only `cshfdq`
insurance and `oancfy` general are not statistically separable from their
threshold, and both belong to fields whose pooled row already raises, so neither
produces a new failure.

**Consequence for the design: a plain declarative threshold comparison is
sufficient and correct.** No statistical gate, no distributional assumption, and
no `scipy` in the derivation path — the binomial arithmetic above is evidence for
this document, never runtime code (S3.2: no distributional machinery inside
derivation logic).

## 3. Insurance `saleq` — investigated, and a prior assumption reversed

Enforcement forces a decision on the one genuinely masked row. It was
investigated rather than inherited from PR #10's judgement.

### 3.1 It is not a tolerance problem

Agreement by tolerance and the per-ticker breakdown, FY2023 (n=51, 13 tickers):

| tolerance | agreement | | ticker | median rel | max rel | quarters within 1% |
|---|---|---|---|---|---|
| 0.010 | 0.627 | | AIG | 0.0246 | **0.3924** | 2/4 |
| 0.015 | 0.745 | | AFL | **0.1336** | 0.2195 | **0/4** |
| 0.020 | 0.824 | | L | 0.0178 | 0.0257 | 1/4 |
| 0.025 | 0.863 | | ACGL | 0.0198 | 0.0257 | 0/4 |
| 0.030 | 0.902 | | CB | 0.0100 | 0.0155 | 1/3 |
| 0.050 | 0.922 | | ERIE | 0.0127 | 0.0141 | 1/4 |
| 0.100 | 0.941 | | HIG | 0.0065 | 0.0127 | 3/4 |
| | | | TRV, WRB, HUM, CI, CINF, MET | ≤0.0043 | ≤0.0055 | **4/4** |

Raising the tolerance to 3% would clear a 0.90 rate, and that is precisely why it
is the wrong fix: it would pass the gate while AIG (39%) and AFL (22%) keep
publishing materially divergent revenue, and it would assert "insurance revenue
agrees within 3%" — false for AFL, whose *median* gap is 13.4%. The distribution
is not a smooth tail (p90 0.0257, p95 0.1336, max 0.3924): it is 6 exact
tickers, 5 within 2.6%, and 2 genuinely divergent.

### 3.2 SimFin holds the as-reported figure; Compustat is the adjusted one

Hand-verified against Aflac's published FY2023 results:

| | Q1 | Q2 | Q3 | Q4 | FY2023 sum | published |
|---|---|---|---|---|---|---|
| SimFin `Revenue` | 4800 | 5172 | 4950 | 3778 | **18,700** | **$18.7B** ✓ |
| Compustat `saleq` | 4718 | 4037 | 4517 | 4457 | 17,729 | −971 (−5.2%) |
| SimFin `Net Income` | 1188 | 1634 | 1569 | 268 | **4,659** | **$4.66B** ✓ |
| Compustat `niq` | 1188 | 1634 | 1569 | 268 | **4,659** | identical ✓ |

The providers agree **exactly** on AFL net income, quarter by quarter, and
diverge only on the revenue line. That isolates the cause to the revenue
definition — it is not a fiscal-calendar misalignment, not a unit error, and not
a restatement, all of which would have moved net income too.

This **reverses the working assumption** that legacy Compustat is the reference
and SimFin the deviation. For insurance revenue, SimFin reproduces the
as-reported total and Compustat publishes a different construction.

### 3.3 Irreducible: no remap exists on either side

- **SimFin side:** `us-income-insurance-quarterly` publishes a single `Revenue`
  column. There is no premiums / net-investment-income / realized-gains
  decomposition to recombine.
- **Compustat side:** for AFL, `saleq == revtq` exactly on all four quarters, and
  `tiiq` and `finrevq` are null. No candidate revenue column exists.
- **Special items rejected as the cause:** `spiq` sums to 38 against a 971 gap.
- Quarterly gaps swing both directions (Q2 −1135, Q4 +679, net −971), consistent
  with realized investment gains/losses — which swing sign quarterly and are
  large for AFL and AIG relative to premiums, and small for CINF/MET/TRV/HUM/CI/WRB.
  The exact Compustat adjustment cannot be pinned without a decomposition column,
  so **this attribution is stated as consistent-with, not confirmed** (S4.7).

### 3.4 Decision: keep it mapped, declare the threshold

Nulling insurance `saleq` was considered and **rejected**: SimFin's value is the
figure that matches the 10-K, so nulling would delete the more accurate number
and cost 13 insurers their revenue — including 6 that agree exactly — to
suppress 2 that diverge for a declared reason. That is not the banks case, where
agreement was 0.000, the concept was structurally different, and nothing of value
was lost.

Instead `saleq` carries a **declared per-family threshold of 0.50 for
insurance**, with the justification above. 0.50 is chosen to be the weakest
statement that still does real work — a majority of rows must agree exactly — and
retains 0.13 headroom below the measured 0.627 so it is not curve-fitted to it.
It fails a banks-style concept mismatch (0.000) and fails a material degradation
on refresh.

**Disclosed consequence.** `net_margin` for insurers with material realized
investment gains carries a level shift across the 2022/2023 boundary (AFL 5.2%
of revenue at the FY2023 annual grain, AIG 16.7%). Each era's value is
internally consistent and each is defensible in its own era, but they are not the
same quantity. `revenue_cagr_*` is already protected: `windows.require_single_era`
nulls any multi-year window spanning the boundary as `mixed_era_window`.

## 4. Design

### 4.1 A declared family vocabulary (`contracts/source_families.py`, new)

Family names are currently string literals in `steps/` (`"general"`, `"banks"`,
`"insurance"` in the SimFin builder; `POOLED_FAMILY = "all"` in the audit). They
are logic-bearing values and belong in `contracts/` per S1.1, and a declared
vocabulary is required to validate per-family threshold keys.

```python
class SourceFamily(StrEnum):
    GENERAL = "general"
    BANKS = "banks"
    INSURANCE = "insurance"

POOLED_FAMILY = "all"          # the row spanning every family
SOURCE_FAMILY_COLUMN = "source_family"
```

`SourceFamily` is a `StrEnum`, so every emitted value is byte-identical to the
literal it replaces; no published output changes.

### 4.2 Per-family thresholds (`contracts/field_era_semantics.py`)

```python
@dataclass(frozen=True)
class FamilyAgreementThreshold:
    family: SourceFamily
    min_agreement_rate: float
    justification: str          # mandatory; validated non-empty
```

`FieldEraSemantics` gains `family_thresholds: tuple[FamilyAgreementThreshold, ...] = ()`
and one accessor:

```python
def min_agreement_rate_for(self, source_family: str) -> float:
    """Threshold for one family: its override, else the field-level rate."""
```

Each override carries its **own mandatory justification** rather than reusing the
field-level `threshold_justification`, so a per-family relaxation cannot be
smuggled in under prose written about the pooled rate — the failure mode that
produced the false "median is exactly 0.0000" claim corrected in PR #10.

Validation added to `validate_field_era_semantics`, each rejecting a declaration
that would be silently inert or unjustified:

1. duplicate family within one field's overrides;
2. empty `justification`;
3. `min_agreement_rate` outside `(0, 1]`;
4. an override for `POOLED_FAMILY` — that is what the field-level rate is for;
5. overrides on an `eras_equivalent=False` field — the verdict is
   `divergent_declared` regardless of rate, so the override could never fire.

### 4.3 Enforcement (`steps/cross_era_semantic_audit.py`)

1. `_field_row` resolves its threshold via
   `declaration.min_agreement_rate_for(source_family)`. The pooled row passes
   `POOLED_FAMILY`, which has no override and so resolves to the field-level
   rate — pooled behaviour is unchanged by construction.
2. Delete `family_row["verdict"] = None`. Per-family rows carry real verdicts.
3. `run_cross_era_audit` collects contradictions from **every** row.
   `contradiction_fields` stays a deduplicated sorted tuple of field names, so
   the CLI contract (`contradiction_fields=` line, `error.fields`) is unchanged.
   A new `contradiction_details` tuple of `"field/family"` strings makes
   attribution diagnosable.

`insufficient_overlap` continues to carry no failure, so a family whose data was
deliberately nulled (banks `saleq`, n=0) raises nothing — the correct outcome.

### 4.4 What this does not do

It does not lower any existing threshold, change any published value, or alter
any metric. `metrics_quarterly` and `metrics_trend` are untouched; a rebuild must
be byte-identical.

## 5. Outcome

Measured results are recorded in the verification block at the head of this
document. In summary: the contradiction set is unchanged at 9 fields, 108
previously-unjudged rows now carry verdicts, no published value moved, and the
gate can now fail on a family. The audit continues to exit non-zero on the 9
pre-existing contradictions — expected state, not a regression.

What changes operationally: a future provider refresh that breaks a single
family — the `saleq`-banks shape, which passed a pooled 0.869 while every bank
row disagreed at 0.000 — now raises instead of reaching the warehouse.

## 6. Risks

1. **A future refresh yields a small family with a noise breach.** Mitigation:
   `MIN_OVERLAP_ROWS = 20` already reports the unmeasurable as
   `insufficient_overlap`. If a spurious small-n raise appears, the response is a
   *declared per-family threshold with measured justification* — auditable and
   visible — never raising `MIN_OVERLAP_ROWS` globally, which would blind the gate
   to real family mismatches.
2. **Threshold overrides become a muting tool.** Mitigation: mandatory
   per-override justification, plus validation rejecting inert overrides. The
   declaration is code-reviewed; a relaxation cannot be silent.
3. **New contradictions on a future provider refresh block the pipeline.** That
   is the intended behaviour, not a risk to mitigate.

## 7. Out of scope

1. Root-causing the 9 existing contradictions — `xsgaq` (0.288) remains the
   largest genuine divergence, and the seven-field median≈0.0000 tail cluster
   remains one shared calibration question.
2. The `cheq`→`chq` remap, still blocked on publishing `source_family` to Stage 1
   output.
3. Per-family *tolerance* overrides. Deliberately not built: §3.1 shows the rate
   override is the honest instrument, and an unused tolerance knob would be
   speculative generality.
