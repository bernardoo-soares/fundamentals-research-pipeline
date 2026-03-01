# Tests Tree Override

Applies inside `tests/`.

## Local Rules
1. Prefer behavior-focused tests over implementation-detail assertions.
2. Keep tests deterministic: no live network calls, no reliance on wall-clock time.
3. Reuse fixtures/helpers before introducing new test setup duplication.
4. For pipeline outputs, assert key columns, row-grain, and deterministic keys (`ticker`, `fyearq`, `fqtr`) when relevant.
5. When adding or changing a CLI stage, add or update at least one CLI dispatch test.
6. Keep test data minimal and auditable (small inline payloads or tiny fixture files).
