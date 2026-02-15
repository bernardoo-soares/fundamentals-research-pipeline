# ExecPlan: Source-Wide Comment and Docstring Expansion

Status: `done`

## Goal
Add explicit, detailed comments across `src/trading_bot/**` so each module, class,
function, and non-trivial logic block is easy to follow during maintenance.

## Scope
In scope:
1. Module docstrings for all Python modules in `src/trading_bot`.
2. Detailed docstrings for every class/function/method in those modules.
3. Targeted inline comments for non-obvious logic paths.
4. Explanatory comments in `src/trading_bot/contracts/sec_metric_map.yml`.

Out of scope:
1. Behavioral changes to pipeline logic.
2. Schema or contract changes.
3. CLI argument changes.

## Assumptions
1. "Every file and method" applies to files under `src/` with priority on
   `src/trading_bot/**`.
2. Existing tests should remain behaviorally valid because only comments/docstrings
   are added.

## Data Contracts
1. No output columns, file paths, or key semantics change.
2. No changes to SEC mapping keys/values; only YAML comments are added.

## Sprint Roadmap

## Sprint 1: Package and Core Modules
Status: `done`

Objective:
- Document package boundaries and shared infrastructure modules.

Files (max 5):
1. `src/trading_bot/__init__.py` (modify)
2. `src/trading_bot/core/__init__.py` (modify)
3. `src/trading_bot/core/settings.py` (modify)
4. `src/trading_bot/core/logging.py` (modify)
5. `src/trading_bot/core/exceptions.py` (modify)

Technical Changes:
1. Add module-level docstrings explaining purpose and usage.
2. Add docstrings for settings helpers and error types.
3. Add inline comments around logging initialization and JSON structure.

Code Changes (Mandatory):
```python
"""Centralized runtime settings sourced from environment variables."""

def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with fallback to a default value."""
```

Output Artifacts:
1. None (documentation-only change).

Exit Criteria:
1. All Sprint 1 files contain module docstrings.
2. All Sprint 1 functions/classes have explicit docstrings.

Validation:
```powershell
python -m compileall src
```

## Sprint 2: Connectors and Workflow Modules
Status: `done`

Objective:
- Document external adapters and top-level orchestration behavior.

Files (max 5):
1. `src/trading_bot/connectors/__init__.py` (modify)
2. `src/trading_bot/connectors/sp500.py` (modify)
3. `src/trading_bot/connectors/sec.py` (modify)
4. `src/trading_bot/workflows/__init__.py` (modify)
5. `src/trading_bot/workflows/full_run.py` (modify)

Technical Changes:
1. Explain request/retry/throttle responsibilities and output contracts.
2. Document workflow summary semantics and year derivation logic.

Code Changes (Mandatory):
```python
class SecClient:
    """HTTP client for SEC endpoints with request throttling and retry semantics."""
```

Output Artifacts:
1. None (documentation-only change).

Exit Criteria:
1. Connector modules clearly document adapter responsibilities.
2. Workflow module documents orchestration boundaries.

Validation:
```powershell
python -m compileall src
```

## Sprint 3: Pipeline Steps and CLI
Status: `done`

Objective:
- Document operational pipeline units and CLI routing clearly.

Files (max 5):
1. `src/trading_bot/__main__.py` (modify)
2. `src/trading_bot/steps/__init__.py` (modify)
3. `src/trading_bot/steps/universe.py` (modify)
4. `src/trading_bot/steps/legacy_fundamentals.py` (modify)
5. `src/trading_bot/steps/sec_fundamentals.py` (modify)

Technical Changes:
1. Describe command intent, stage I/O, and branch behavior in CLI.
2. Add function-level docs for filtering, dedupe, and normalization internals.
3. Add inline comments for non-trivial transformation paths.

Code Changes (Mandatory):
```python
def normalize_sec_facts_long(...):
    """Convert raw SEC companyfacts payloads into a deterministic long-form table."""
```

Output Artifacts:
1. None (documentation-only change).

Exit Criteria:
1. Every step function includes an explicit docstring.
2. CLI command handlers are documented for intent and outputs.

Validation:
```powershell
python -m compileall src
```

## Sprint 4: Contract Package and YAML Comments
Status: `done`

Objective:
- Document SEC contract modules and annotate YAML mapping structure.

Files (max 5):
1. `src/trading_bot/contracts/__init__.py` (modify)
2. `src/trading_bot/contracts/sec_metric_contract.py` (modify)
3. `src/trading_bot/contracts/sec_metric_map.yml` (modify)

Technical Changes:
1. Add module and function docstrings for contract loader/validator internals.
2. Add section comments in YAML clarifying required keys and metric grouping.

Code Changes (Mandatory):
```yaml
# Mapping contract for SEC companyfacts tags to canonical raw fundamentals fields.
# Each metric entry must define fact_type, unit_priority, form_priority,
# tag_priority, transform_rule, and quality_tier.
```

Output Artifacts:
1. None (documentation-only change).

Exit Criteria:
1. Contract loader/validator methods have detailed docstrings.
2. YAML has clear explanatory comments without value changes.

Validation:
```powershell
python -m compileall src
```

## Risks and Mitigations
1. Risk: Excessive comments reduce readability.
   Mitigation: Keep comments focused on intent, edge cases, and data contracts.
2. Risk: Accidental behavioral edits during broad refactor.
   Mitigation: Limit edits to comments/docstrings and run compile validation.

## Validation Matrix
1. Syntax validation:
```powershell
python -m compileall src
```

## Change Log
1. 2026-02-15: Created ExecPlan for source-wide comment/docstring expansion.
2. 2026-02-15: Completed all four sprints; added detailed comments/docstrings across `src/trading_bot/**` and explanatory YAML comments.
