# ExecPlan: SEC Fundamentals 2023-2025 (Current S&P 500, Code-Explicit)

Status: `in_progress`

Path migration note (2026-02-14):
1. `src/trading_bot/config/*` moved to `src/trading_bot/core/*` and `src/trading_bot/contracts/*`.
2. `src/trading_bot/services/*` moved to `src/trading_bot/connectors/*`.
3. `src/trading_bot/ingestion/*` and `src/trading_bot/normalization/*` moved to `src/trading_bot/steps/*`.
4. Historical sprint snippets below may reference pre-migration paths.

## Goal
Build SEC ingestion + normalization for 2023-2025 fundamentals for current S&P 500 tickers from `data/universe_current.csv`, with strict contract control and auditable outputs.

## Scope
In scope:
1. Sprint 0 contract freeze.
2. Sprint 1 SEC reference mapping and raw fetch.
3. Sprint 2 fact normalization to long dataset.

Out of scope:
1. Quarterly wide canonical merge.
2. Ratio computation.
3. Screening/ranking.

## Data Contracts
Fetch-only fields:
1. `saleq`
2. `niq`
3. `oiadpq`
4. `xintq`
5. `txtq`
6. `epspxq`
7. `actq`
8. `lctq`
9. `ppentq`
10. `gdwlq`
11. `ivltq`
12. `atq`
13. `ceqq`
14. `dlcq`
15. `dlttq`
16. `req`
17. `tstkq`
18. `oancfq`
19. `prstkcq`

Helper fallbacks:
1. `oancfy`
2. `prstkcy`
3. `cshopq`

Compute-only:
1. All derived ratios/metrics.

## Sprint Roadmap

## Sprint 0.1: Contract Validator
Status: `done`

Objective:
Create strict loader/validator for SEC mapping contract.

Files (max 5):
1. `src/trading_bot/config/sec_metric_contract.py` (new)

Technical Changes:
1. Add constants: fetch-only, helper, compute-only fields.
2. Add dataclasses: `MetricMapping`, `SecMetricContract`.
3. Add loader: `load_sec_metric_contract(path=None)`.
4. Add validator: `validate_contract(contract)`.
5. Enforce allowed forms/rules/types and exact canonical field set.

Code Changes (Mandatory):
```python
# src/trading_bot/config/sec_metric_contract.py
def load_sec_metric_contract(path: str | Path | None = None) -> SecMetricContract:
    mapping_path = Path(path) if path else _default_contract_path()
    raw = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))
    root = _expect_mapping(raw, context="root")
    ...
    contract = SecMetricContract(version=version, description=description, metrics=metrics)
    validate_contract(contract)
    return contract
```

```python
def validate_contract(contract: SecMetricContract) -> None:
    names = frozenset(contract.metrics)
    missing = sorted(REQUIRED_CANONICAL_FIELDS.difference(names))
    extra = sorted(names.difference(REQUIRED_CANONICAL_FIELDS))
    if missing or extra:
        raise ValueError(...)
```

Exit Criteria:
1. Contract loader rejects invalid/misaligned mappings.

Validation:
```powershell
python -m compileall src\trading_bot\config\sec_metric_contract.py
```

## Sprint 0.2: Mapping Freeze YAML
Status: `done`

Objective:
Freeze tag priority and transform policy.

Files (max 5):
1. `src/trading_bot/config/sec_metric_map.yml` (new)

Technical Changes:
1. Define `metrics` for 22 fields (19 + 3 helpers).
2. Add `fact_type`, `unit_priority`, `form_priority`, `tag_priority`, `transform_rule`, `quality_tier`.
3. `ivltq` uses broad-quality with `component_tags`.

Code Changes (Mandatory):
```yaml
saleq:
  fact_type: duration
  unit_priority: ["USD"]
  form_priority: ["10-Q", "10-K"]
  tag_priority:
    - "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    - "us-gaap:SalesRevenueNet"
    - "us-gaap:Revenues"
  transform_rule: q4_extract
  quality_tier: primary
```

```yaml
ivltq:
  fact_type: instant
  unit_priority: ["USD"]
  form_priority: ["10-Q", "10-K"]
  tag_priority:
    - "us-gaap:NoncurrentInvestments"
    - "us-gaap:LongTermInvestments"
    - "us-gaap:Investments"
  component_tags:
    - "us-gaap:AvailableForSaleSecuritiesDebtSecuritiesNoncurrent"
    - "us-gaap:HeldToMaturitySecuritiesNoncurrent"
  transform_rule: direct_or_sum_components
  quality_tier: fallback
```

Exit Criteria:
1. YAML defines all required fields and no compute-only fields.

Validation:
```powershell
python -c "import sys; sys.path.insert(0,'src'); from trading_bot.config.sec_metric_contract import load_sec_metric_contract; print(load_sec_metric_contract().version)"
```

## Sprint 0.3: Canonical Schema Spec
Status: `done`

Objective:
Document canonical grain and column contract.

Files (max 5):
1. `specs/CANONICAL_SCHEMA.md` (new)

Technical Changes:
1. Define row grain and key columns.
2. Define fetch-only and compute-only boundaries.
3. Define traceability columns.

Code Changes (Mandatory):
```md
## Required Key Columns
1. ticker
2. fyearq
3. fqtr
```

```md
## Fetch-Only Raw Fields
1. saleq
2. niq
...
```

Exit Criteria:
1. Schema doc matches contract loader + YAML.

Validation:
```powershell
python -m compileall src
```

## Sprint 0.4: Schema Tests
Status: `done`

Objective:
Enforce contract freeze via tests.

Files (max 5):
1. `tests/schema/test_sec_metric_contract.py` (new)

Technical Changes:
1. Tests for load success.
2. Tests for exact field set.
3. Tests for compute-only exclusion.
4. Tests for helper/component validity.

Code Changes (Mandatory):
```python
def test_contract_exactly_matches_required_fields() -> None:
    contract = load_sec_metric_contract()
    assert set(contract.metrics) == REQUIRED_CANONICAL_FIELDS
```

```python
def test_contract_does_not_include_compute_only_fields() -> None:
    contract = load_sec_metric_contract()
    leaked = set(contract.metrics).intersection(COMPUTE_ONLY_FIELDS)
    assert not leaked
```

Exit Criteria:
1. Invalid contract shape is caught.

Validation:
```powershell
python -m pytest tests/schema/test_sec_metric_contract.py -q
```

## Sprint 1.1: SEC Reference Adapter
Status: `done (code complete; pytest unavailable in local env)`

Objective:
Fetch SEC ticker reference and build normalized ticker->CIK index.

Files (max 5):
1. `src/trading_bot/services/sec_reference.py` (new)
2. `src/trading_bot/config/settings.py` (modify)
3. `tests/sec/test_sec_reference.py` (new)

Technical Changes:
1. Add SEC settings to `AppSettings`.
2. Add normalization function for ticker keys.
3. Add fetch + index builder.

Code Changes (Mandatory):
```python
# src/trading_bot/services/sec_reference.py
def normalize_ticker(symbol: str) -> str:
    return str(symbol).strip().upper().replace(" ", "")

def fetch_sec_ticker_reference(
    session: requests.Session,
    url: str,
    timeout: int,
) -> list[dict[str, str]]:
    resp = session.get(url, timeout=timeout)
    resp.raise_for_status()
    payload = resp.json()
    # payload keys are numeric strings
    return [payload[k] for k in sorted(payload.keys(), key=int)]
```

```python
def build_ticker_to_cik_index(rows: list[dict[str, str]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in rows:
        ticker = normalize_ticker(row.get("ticker", ""))
        cik = str(row.get("cik_str", "")).zfill(10)
        if ticker and cik:
            out[ticker] = cik
    return out
```

Exit Criteria:
1. Deterministic ticker->CIK map from SEC reference.

Validation:
```powershell
python -m pytest tests/sec/test_sec_reference.py -q
```

## Sprint 1.2: Universe-to-CIK Pipeline
Status: `done (code complete; pytest unavailable in local env)`

Objective:
Create `data/reports/sec_cik_mapping.csv`.

Files (max 5):
1. `src/trading_bot/ingestion/sec_cik_mapping.py` (new)
2. `src/trading_bot/services/sec_reference.py` (modify)
3. `tests/sec/test_sec_cik_mapping.py` (new)

Technical Changes:
1. Read universe file.
2. Join with SEC index.
3. Write mapping report with statuses.

Code Changes (Mandatory):
```python
# src/trading_bot/ingestion/sec_cik_mapping.py
def build_sec_cik_mapping(
    universe_path: str | Path,
    output_path: str | Path,
) -> pd.DataFrame:
    universe = pd.read_csv(universe_path, dtype=str)
    tickers = universe["ticker"].astype(str).str.strip().str.upper()
    ...
    df = pd.DataFrame(rows).sort_values("ticker").reset_index(drop=True)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    return df
```

```python
# produced columns
{
  "ticker": ticker,
  "cik": cik_or_none,
  "sec_ticker": sec_ticker_or_none,
  "sec_name": sec_name_or_none,
  "mapping_status": "mapped|missing|ambiguous",
  "mapped_at_utc": now_iso,
}
```

Exit Criteria:
1. All universe tickers appear once in mapping report.

Validation:
```powershell
python -m pytest tests/sec/test_sec_cik_mapping.py -q
```

## Sprint 1.3: SEC Client (Retry + Throttle)
Status: `done (code complete; pytest unavailable in local env)`

Objective:
Create robust SEC client for raw companyfacts retrieval.

Files (max 5):
1. `src/trading_bot/services/sec_client.py` (new)
2. `src/trading_bot/io/exceptions.py` (modify)
3. `tests/sec/test_sec_client.py` (new)

Technical Changes:
1. Add typed SEC exceptions.
2. Add `SecClient` with throttling and retry.
3. Add `fetch_companyfacts(cik)`.

Code Changes (Mandatory):
```python
class SecClient:
    def __init__(self, base_url: str, user_agent: str, timeout_seconds: int, rate_limit_per_second: float, max_retries: int) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": user_agent, "Accept": "application/json"})
        self.timeout_seconds = timeout_seconds
        self.rate_limit_per_second = rate_limit_per_second
        self.max_retries = max_retries
        self._next_allowed_ts = 0.0
```

```python
def fetch_companyfacts(self, cik: str) -> dict[str, Any]:
    cik10 = str(cik).zfill(10)
    url = f"{self.base_url}/api/xbrl/companyfacts/CIK{cik10}.json"
    return self._request_json(url)
```

Exit Criteria:
1. Retry/backoff/429 handling works and is tested.

Validation:
```powershell
python -m pytest tests/sec/test_sec_client.py -q
```

## Sprint 1.4: Raw Ingestion Pipeline
Status: `done (code complete; pytest unavailable in local env)`

Objective:
Fetch JSON and write ingestion log.

Files (max 5):
1. `src/trading_bot/ingestion/sec_raw.py` (new)
2. `src/trading_bot/services/sec_client.py` (modify)
3. `src/trading_bot/io/logging.py` (modify)
4. `tests/sec/test_sec_ingest_raw.py` (new)

Technical Changes:
1. Iterate mapped tickers from `sec_cik_mapping.csv`.
2. Fetch `companyfacts`.
3. Write JSON per ticker.
4. Write ingestion log CSV.

Code Changes (Mandatory):
```python
def run_sec_raw_ingestion(mapping_path: str | Path, raw_dir: str | Path, log_path: str | Path) -> pd.DataFrame:
    mapping = pd.read_csv(mapping_path, dtype=str)
    mapped = mapping[mapping["mapping_status"] == "mapped"].copy()
    rows: list[dict[str, Any]] = []
    for _, rec in mapped.iterrows():
        ticker = rec["ticker"]
        cik = rec["cik"]
        started = time.perf_counter()
        try:
            payload = client.fetch_companyfacts(cik)
            out_path = Path(raw_dir) / f"{ticker}_{cik}.json"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(json.dumps(payload), encoding="utf-8")
            status = "ok"
            error = ""
            code = 200
        except Exception as exc:
            status = "error"
            error = str(exc)
            code = None
            out_path = None
        rows.append({...})
```

```python
# log row schema
{
  "run_id": run_id,
  "ticker": ticker,
  "cik": cik,
  "status": status,
  "http_code": code,
  "latency_ms": round((time.perf_counter() - started) * 1000, 2),
  "file_path": str(out_path) if out_path else "",
  "error": error,
  "fetched_at_utc": now_iso,
}
```

Exit Criteria:
1. `data/raw/sec/companyfacts/*.json` and `data/reports/sec_ingestion_log.csv` produced.

Validation:
```powershell
python -m pytest tests/sec/test_sec_ingest_raw.py -q
```

## Sprint 2.1: Fact Parser
Status: `done`

Objective:
Flatten SEC payloads into long rows.

Files (max 5):
1. `src/trading_bot/services/sec_fact_parser.py` (new)
2. `tests/sec/test_sec_fact_parser.py` (new)

Technical Changes:
1. Iterate `facts -> taxonomy -> tag -> units -> observations`.
2. Emit normalized long rows.

Code Changes (Mandatory):
```python
def iter_companyfacts_rows(payload: dict[str, Any], ticker: str, cik: str) -> Iterable[dict[str, Any]]:
    facts = payload.get("facts", {})
    for taxonomy, taxonomy_block in facts.items():
        for tag, tag_block in taxonomy_block.items():
            units = tag_block.get("units", {})
            for unit, obs_list in units.items():
                for obs in obs_list:
                    yield {
                        "ticker": ticker,
                        "cik": str(cik).zfill(10),
                        "taxonomy": taxonomy,
                        "tag": tag,
                        "unit": unit,
                        "value": obs.get("val"),
                        "start": obs.get("start"),
                        "end": obs.get("end"),
                        "fy": obs.get("fy"),
                        "fp": obs.get("fp"),
                        "form": obs.get("form"),
                        "filed": obs.get("filed"),
                        "accn": obs.get("accn"),
                        "frame": obs.get("frame"),
                    }
```

Exit Criteria:
1. Parser yields stable schema rows for each observation.

Validation:
```powershell
python -m pytest tests/sec/test_sec_fact_parser.py -q
```

## Sprint 2.2: Contract-Driven Normalization
Status: `done`

Objective:
Map flattened rows into contract fields and filter forms/units.

Files (max 5):
1. `src/trading_bot/normalization/sec_facts.py` (new)
2. `src/trading_bot/services/sec_fact_parser.py` (modify)
3. `src/trading_bot/config/sec_metric_contract.py` (modify)
4. `tests/sec/test_sec_normalize_facts.py` (new)

Technical Changes:
1. Read all raw JSON files.
2. Parse all fact rows.
3. Resolve `canonical_field` by tag priority.
4. Keep only allowed forms and unit priorities.
5. Keep 2023-2025-relevant rows.

Code Changes (Mandatory):
```python
def _resolve_canonical_field(tag_full: str, mapping: dict[str, MetricMapping]) -> str | None:
    for canonical_name, cfg in mapping.items():
        if tag_full in cfg.tag_priority or tag_full in cfg.component_tags:
            return canonical_name
    return None
```

```python
def normalize_sec_facts_long(raw_dir: str | Path, mapping_path: str | Path, output_path: str | Path) -> pd.DataFrame:
    mapping = get_metric_mapping(mapping_path)
    rows: list[dict[str, Any]] = []
    for json_path in Path(raw_dir).glob("*.json"):
        payload = json.loads(json_path.read_text(encoding="utf-8"))
        ticker, cik = _parse_file_name(json_path)
        for r in iter_companyfacts_rows(payload, ticker=ticker, cik=cik):
            tag_full = f"{r['taxonomy']}:{r['tag']}"
            canonical = _resolve_canonical_field(tag_full, mapping)
            if not canonical:
                continue
            if r["form"] not in mapping[canonical].form_priority:
                continue
            if r["unit"] not in mapping[canonical].unit_priority:
                continue
            if not _is_relevant_year(r["fy"]):
                continue
            rows.append({...})
    df = pd.DataFrame(rows)
    ...
```

Exit Criteria:
1. Output rows contain only mapped canonical fields.

Validation:
```powershell
python -m pytest tests/sec/test_sec_normalize_facts.py -q
```

## Sprint 2.3: Persist + Dedupe Long Facts
Status: `done`

Objective:
Persist deterministic `sec_facts_long_2023_2025.csv`.

Files (max 5):
1. `src/trading_bot/normalization/sec_facts.py` (modify)
2. `src/trading_bot/io/logging.py` (modify)
3. `tests/sec/test_sec_normalize_output.py` (new)

Technical Changes:
1. Dedupe by deterministic key.
2. Tie-break by latest `filed_date`, then `accn`.
3. Save output CSV.

Code Changes (Mandatory):
```python
dedupe_key = [
    "ticker", "canonical_field", "period_end", "form", "accn", "source_tag", "unit"
]
df["filed_date"] = pd.to_datetime(df["filed_date"], errors="coerce")
df = df.sort_values(["filed_date", "accn"]).drop_duplicates(subset=dedupe_key, keep="last")
df.to_csv(output_path, index=False)
```

Exit Criteria:
1. Repeated run with same raw input yields same output rows.

Validation:
```powershell
python -m pytest tests/sec/test_sec_normalize_output.py -q
```

## Sprint 2.4: CLI Commands
Status: `done`

Objective:
Expose stages as reproducible commands.

Files (max 5):
1. `src/trading_bot/__main__.py` (modify)
2. `src/trading_bot/ingestion/sec_cik_mapping.py` (modify)
3. `src/trading_bot/ingestion/sec_raw.py` (modify)
4. `src/trading_bot/normalization/sec_facts.py` (modify)
5. `tests/sec/test_sec_cli.py` (new)

Technical Changes:
1. Add subcommands:
   - `sec-map-cik`
   - `sec-ingest-raw`
   - `sec-normalize-long`

Code Changes (Mandatory):
```python
# src/trading_bot/__main__.py
sec_map = subparsers.add_parser("sec-map-cik")
sec_map.add_argument("--universe-path", default="data/universe_current.csv")
sec_map.add_argument("--output-path", default="data/reports/sec_cik_mapping.csv")

sec_ingest = subparsers.add_parser("sec-ingest-raw")
sec_ingest.add_argument("--mapping-path", default="data/reports/sec_cik_mapping.csv")
sec_ingest.add_argument("--raw-dir", default="data/raw/sec/companyfacts")
sec_ingest.add_argument("--log-path", default="data/reports/sec_ingestion_log.csv")
```

Exit Criteria:
1. Each stage runnable independently via CLI.

Validation:
```powershell
python -m pytest tests/sec/test_sec_cli.py -q
```

## Sprint 2.5: QA Reports for Stage 1-2
Status: `not_started`

Objective:
Generate coverage reports for mapping and normalized facts.

Files (max 5):
1. `src/trading_bot/reports/sec_quality.py` (new)
2. `src/trading_bot/normalization/sec_facts.py` (modify)
3. `tests/sec/test_sec_quality_reports.py` (new)

Technical Changes:
1. Add ticker coverage report.
2. Add canonical-field/year/quality coverage report.

Code Changes (Mandatory):
```python
def build_long_fact_coverage_report(df: pd.DataFrame, output_path: str | Path) -> pd.DataFrame:
    rep = (
        df.groupby(["canonical_field", "fy", "quality_tier"], dropna=False)
        .size()
        .reset_index(name="row_count")
        .sort_values(["canonical_field", "fy", "quality_tier"])
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    rep.to_csv(output_path, index=False)
    return rep
```

Exit Criteria:
1. Reports are generated with stable schema.

Validation:
```powershell
python -m pytest tests/sec/test_sec_quality_reports.py -q
```

## Risks and Mitigations
1. Ticker mapping misses:
   - keep explicit `mapping_status` and unresolved list.
2. SEC tag variability:
   - ordered tag priority + helper fallback in YAML.
3. Rate-limit instability:
   - bounded retry + throttle in `SecClient`.
4. Non-determinism:
   - fixed dedupe key + tie-break rule.

## Validation Matrix
1. Contract compile/load:
```powershell
python -m compileall src
python -c "import sys; sys.path.insert(0,'src'); from trading_bot.config.sec_metric_contract import load_sec_metric_contract; print(load_sec_metric_contract().version)"
```
2. Contract tests:
```powershell
python -m pytest tests/schema/test_sec_metric_contract.py -q
```
3. Stage tests:
```powershell
python -m pytest tests/sec -q
```

## Change Log
1. 2026-02-07: Initial Sprint 0-2 plan created.
2. 2026-02-07: Rewritten with micro-sprints.
3. 2026-02-07: Rewritten again with explicit code snippets per sprint (mandatory code-first format).
4. 2026-02-07: Sprint 1.1-1.4 code implemented; validation command blocked locally because `pytest` is not installed.
5. 2026-02-08: Sprint 2.1-2.4 implemented with parser, normalization, deterministic dedupe, and CLI stage commands.
6. 2026-02-14: Source tree simplified to `core/contracts/connectors/steps/workflows`; old overlapping folders removed.
