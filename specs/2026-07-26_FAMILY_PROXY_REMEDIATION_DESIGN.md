# Stage 1 — Family-Proxy Remediation (`saleq`, `cheq`, `rectq`)

Status: IMPLEMENTED — 2026-07-26 (branch `feature/family-proxy-remediation`).

**Real-corpus verification (2026-07-26 rebuild).** Measured, not expected:

*Stage 1, FY2023 staged SimFin frame.* `saleq` banks **0/47**, insurance 59/59
(kept — see §2.1), general 1,429/1,429 unchanged. `cheq` banks **0/47**,
insurance **0/59**, general 1,422/1,429 unchanged. `rectq` banks **0/47**,
insurance **0/59**, general 1,312/1,429 unchanged. Era resolution unchanged at
30,660 legacy / 3,032 SimFin.

*Audit.* Contradiction count remains **9** (`capxy`, `cheq`, `cshfdq`, `cshoq`,
`dpq`, `oancfy`, `rectq`, `xrdq`, `xsgaq`), as designed — this slice removes a
cause, not a verdict. The per-family rows now read:

| field | pooled | general | banks | insurance |
|---|---|---|---|---|
| `saleq` | 0.896 `agree` | 0.906 | n=0 | 0.627 |
| `cheq` | 0.692 CONTRADICTION | 0.692 | n=0 | n=0 |
| `rectq` | 0.566 CONTRADICTION | 0.566 | n=0 | n=0 |

The financial families no longer produce a comparable value at all, so `cheq`
and `rectq` now attribute entirely to the general-family tail rather than to two
mixed causes. `saleq`'s insurance tail (0.627) is now visible in its own row
instead of being averaged away.

*Blast radius.* 19 bank tickers and 17 insurance tickers are affected. All
**88/88** SimFin-era bank quarters lose `saleq`. Non-financial SimFin-era
`saleq` nulls are 11/2,832 — all pre-existing plausibility-gate nulls, not
caused by this slice. `net_margin` gains `missing_input` for **11 bank tickers,
and only those**. Of the 44 tickers with a missing SimFin-era `net_margin`, the
other **33 pre-date this change**: 31 general-family, plus ELV and GL, which are
insurance and therefore keep their `saleq` — their nulls are 2023Q1–Q3 only, the
TTM warm-up window before four consecutive SimFin quarters exist, with non-null
`saleq` and `niq` on every row. (An earlier draft of this block attributed those
two to this slice. It could not have caused them, since insurance `saleq` is
deliberately retained — corrected here per S4.7.)

*Denominator note.* §2's general-family rates (`cheq` 0.690, `rectq` 0.563) come
from the investigation, which inner-joined the staged frames to the raw
Compustat files to test candidate columns. The audit compares staged-against-
staged with no such join, so it reports 0.692 and 0.566 on 8 more rows —
`cheq` n=1,326 against 1,318 and `rectq` n=1,218 against 1,210. The delta is
exactly 8 on both fields, i.e. the same 8 tickers absent from the raw-file glob.
This is join coverage, not drift, and is the same artifact recorded in the
`oiadpq` spec §2.2.

*Hard gate — no general-family value moved.* Structural: the changes touch only
the `banks` and `insurance` branches, and the general branch assigns the same
expressions as before. Empirically AAPL 2023Q4 `net_margin` is unchanged at
0.2530623426432028, KO 2019Q4 `interest_pct_operating_income` at
0.08974480599563608, and BAC's legacy-era `saleq` still reads 34,926 for 2022Q4
while its SimFin-era rows are null.

*Invariants.* 0 `inf`/`NaN`; 0 value-XOR-reason violations; 0 quality flags on a
null. 245 tests pass.

Direct follow-on to `2026-07-25_OIADPQ_ERA_REMEDIATION_DESIGN.md`. That slice
added per-SimFin-family reporting to the cross-era audit, and the new instrument
immediately exposed the same defect class in three more fields — recorded as an
open item in that spec's §7 and now root-caused here.

Investigation performed 2026-07-26 against the real corpus. Every number in §2
was measured, not assumed (S4.7).

## 1. Goal

Stop publishing a SimFin family-specific aggregate under a canonical field name
that means something else. Nothing in this slice may change a general-family
value.

## 2. Root cause — measured per family (FY2023 overlap)

| field | general | banks | insurance | pooled | pooled verdict |
|---|---|---|---|---|---|
| `saleq` | 0.906 | **0.000** | 0.627 | 0.869 | `agree` (threshold 0.80) |
| `cheq` | 0.690 | **0.000** | **0.000** | 0.648 | CONTRADICTION |
| `rectq` | 0.563 | 0.000 | 0.100 | 0.547 | CONTRADICTION |

`saleq` is the reason this class is dangerous: its pooled rate clears its
declared threshold, so the audit passes it as `agree` and **no guard fires**,
while bank revenue disagrees on every single row. `saleq` feeds the shipped
`net_margin` metric and every `revenue_cagr_*` trend metric.

### 2.1 `saleq` — banks are a different aggregate (irreducible)

Legacy runs systematically higher (median relative difference 0.5328, median
ratio 1.533). No candidate closes it:

| candidate | agreement | median rel. diff |
|---|---|---|
| `saleq` (current) | 0.000 | 0.5328 |
| `saleq − xintq` | 0.093 | 0.4182 |
| `tiiq` (total interest income) | 0.087 | 0.2087 |
| `revtq` | 0.000 | 0.3892 |
| `niitq` (net interest income) | 0.000 | 0.4076 |
| vs SimFin `Net Revenue after Provisions` | 0.000 | 0.6759 |

Compustat `saleq` for a bank is total revenue; SimFin's bank `Revenue` is a
narrower construction that no available Compustat column reproduces. Not a
remapping error.

**Insurance (0.627) is a different, milder problem** — median relative
difference 0.0046 and median ratio 0.999, i.e. the concept matches and only a
tail diverges. It is NOT nulled by this slice; it is disclosed in §6.

### 2.2 `cheq` — SimFin's column is family-dependent

Compustat `cheq` is Cash **and Short-Term Investments**. SimFin publishes a
column with the identical name, `Cash, Cash Equivalents & Short Term
Investments`, in all three balance-sheet files — but it means cash-only for
banks and insurance, whose short-term investments sit in separate columns
(`Short & Long Term Investments`, `Total Investments`).

Measured against Compustat `chq` (cash only):

| family | `cheq` (current) | `chq` | `chq + ivstq` |
|---|---|---|---|
| general | **0.690** | 0.613 | 0.690 |
| banks | 0.000 | **0.650** | 0.000 |
| insurance | 0.000 | **0.979** (median 0.0000, ratio 1.000) | 0.000 |

The insurance result is the signature of a correct remapping, as clean as the
`reunaq` fix (0.958). **The correct legacy source is therefore
family-dependent** — `chq` for financials, `cheq` for general — and a single
global remap fails, because `chq` is *worse* for the general family that is 97%
of the corpus.

Capturing that would require the legacy builder to know a ticker is a financial.
It cannot: the legacy extract carries no discriminator of its own (`indfmt` is
uniformly `INDL` across the corpus, including JPM). The only route would be
joining ticker→family from the SimFin staging output, creating a
legacy-depends-on-SimFin build coupling.

**Decision (2026-07-26): null `cheq` for banks and insurance** rather than build
that coupling. This is the `oiadpq` treatment and is consistent with the
precedent already merged. The cost is explicit and accepted: the reconcilable
insurance cash data that `chq` matches at 0.979 is discarded rather than
recovered. Recorded in §6 as a known, deliberate coverage loss so a later slice
can revisit it.

### 2.3 `rectq` — no candidate in any family

| family | `rectq` (current) | `rectrq` (trade) | `rectoq` (other) |
|---|---|---|---|
| general | 0.563 | 0.643 | — |
| banks | 0.000 | 0.000 | 0.000 |
| insurance | 0.100 | 0.182 | 0.000 |

Nothing reconciles anywhere. The financial families are a concept mismatch
(median 2.4485 banks, 0.6583 insurance); the general family is a tail problem
(median 0.0000).

## 3. Scope — three null-outs and one corrected claim

### 3.1 Null the family proxies

In `steps/simfin_raw_fundamentals_builder.py::_build_family_canonical`, move
these three assignments out of the shared block into the family branch, mapped
for `general` and `_empty_numeric_series` for the named families — the treatment
`oiadpq`, `xintq`, `cogsq`, `xsgaq`, `xrdq`, `actq` and `lctq` already receive.

| field | general | banks | insurance |
|---|---|---|---|
| `saleq` | mapped | **null** | mapped (see §2.1) |
| `cheq` | mapped | **null** | **null** |
| `rectq` | mapped | **null** | **null** |

Each null-out carries an inline comment recording the measured agreement that
justifies it, matching the `oiadpq` precedent.

### 3.2 Correct a false claim in the `saleq` declaration

`contracts/field_era_semantics.py`'s `saleq` entry currently asserts in its
`threshold_justification`: "the median relative difference is exactly 0.0000".
That is true for the general family and **false for banks** (0.5328). It is a
pooled claim the per-family split refutes, and S4.7 requires reporting what was
measured. Amend it to state the per-family reality and to record that banks are
now nulled.

`cheq` and `rectq` keep their current declarations: after this slice their
remaining divergence is a general-family tail (median 0.0000), which is a
different defect class and is not root-caused here.

## 4. Expected effect

- The financial families lose `cheq`/`rectq` in the SimFin era, and banks lose
  `saleq`. (Measured after implementation: 19 bank and 17 insurance tickers;
  88 SimFin-era bank quarters. The "24 tickers" figure carried over from the
  `oiadpq` slice was the FY2023 *overlap* count, not the corpus count.)
- `saleq` pooled rises from 0.869 toward the general+insurance rate; it remains
  `agree`, but the per-family rows now show the insurance tail rather than
  hiding a 0.000 family.
- `cheq` pooled becomes the general-family rate 0.690, and `rectq` 0.563. Both
  remain CONTRADICTIONs — correctly, and now attributable to a single cause
  rather than two. The contradiction count stays at **9**.
- No general-family value changes anywhere.
- `net_margin` and `revenue_cagr_*` become null for the 11 bank tickers in the
  SimFin era rather than carrying a definitional break. This is the intended
  trade: an absent signal rather than a false one.

## 5. Testing

1. **Synthetic mechanics tests** (per S4.4 these are NOT golden tests): each of
   `saleq`/`cheq`/`rectq` is null for the families named in §3.1 and unchanged
   for `general`.
2. **Contract test** that the `saleq` `threshold_justification` no longer makes
   the refuted pooled claim.
3. Existing suite must pass unchanged — no general-family behaviour moves.

## 6. Real-corpus verification (required before merge)

1. Per-family null counts for the three fields in the FY2023 staged SimFin frame.
2. General-family values byte-identical before and after — the hard gate for
   this slice. Verified structurally: the changes touch only the `banks` and
   `insurance` branches.
3. Contradiction count remains 9, with the per-family rows showing the financial
   families now absent rather than at 0.000.
4. `net_margin` / `revenue_cagr_*` coverage change confined to bank tickers.

## 7. Out of scope / open items

1. **The general-family tails.** `cheq` 0.690 and `rectq` 0.563 with median
   0.0000 — the typical company matches exactly and a tail diverges. Same class
   as the other tail contradictions (`capxy`, `cshfdq`, `cshoq`, `dpq`,
   `oancfy`, `xrdq`). Not root-caused.
2. **`saleq` insurance (0.627).** Concept matches (median 0.0046, ratio 0.999);
   a tail problem, deliberately not nulled.

3. **Per-family rows are evidence, not a gate — and this is now the binding
   limitation.** Only the pooled row carries a verdict; every per-family row is
   written with `verdict = None` by design (`oiadpq` spec §3.4). So a family
   sitting below its field's declared `min_agreement_rate` cannot raise a
   contradiction as long as the pooled rate clears it. That is precisely the
   masking mechanism §2 calls dangerous, and this slice only removes it for the
   families whose data was deleted. It remains structurally live for at least:

   | field | family | agreement | declared threshold | pooled verdict |
   |---|---|---|---|---|
   | `saleq` | insurance | 0.627 | 0.80 | `agree` (0.896) |
   | `cshoq` | banks | 0.721 | 0.90 | CONTRADICTION |
   | `cshoq` | insurance | 0.667 | 0.90 | CONTRADICTION |
   | `dpq` | banks | 0.724 | 0.90 | CONTRADICTION |

   For `cshoq`/`dpq` the pooled row already fails, so nothing is hidden. For
   `saleq` insurance it is hidden: the field reads `agree` while a whole family
   sits 0.17 below its threshold. Making per-family rows enforceable — or
   declaring a per-family threshold — is the natural next hardening step, and
   is deliberately out of scope here because it changes audit *policy*, not
   just reporting.

   **RESOLVED 2026-07-26** by `2026-07-26_PER_FAMILY_AUDIT_VERDICTS_DESIGN`.
   Per-family rows now carry enforceable verdicts and a contradiction on any row
   raises; null verdicts in the FY2023 report fell from 108 to 0. Two findings
   from that slice correct the assessment above:

   - The `saleq` insurance row was **not** a tail problem, as characterised here.
     Measured per-ticker, it is 6 tickers agreeing exactly, 5 within 2.6%, and 2
     genuinely divergent (AIG max 39.2%, AFL median 13.4% with 0/4 quarters
     within 1%) — a per-company definitional spectrum, the `oiadpq` shape.
   - **SimFin holds the as-reported figure here, not Compustat.** AFL FY2023
     SimFin revenue sums to 18,700 against Aflac's published $18.7B, while
     Compustat `saleq` sums to 17,729. Both providers agree exactly on AFL net
     income, isolating the divergence to the revenue line. Insurance `saleq` was
     therefore kept and declared at a 0.50 threshold rather than nulled — nulling
     would have deleted the more accurate value.
3. **Deliberate coverage loss on `cheq`.** The `chq` remap would recover
   insurance at 0.979 and banks at 0.650 but needs a family-aware legacy
   builder. Revisit if a ticker→family classification is ever published to
   Stage 1 (platform spec D5 will need one anyway to renormalize the financials
   scorecard).
4. **`xsgaq` (0.288)** remains the largest un-investigated contradiction, and is
   a separate cause-class from `cogsq` (Spearman 0.210).
