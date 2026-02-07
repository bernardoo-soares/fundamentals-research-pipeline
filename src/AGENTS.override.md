# Source Tree Override

Applies inside `src/`.

## Local Rules
1. Keep imports package-qualified under `trading_bot.*`.
2. Avoid writing business logic in CLI entrypoints; keep orchestration in `pipelines`.
3. Treat `config` and `io` modules as shared infrastructure; avoid circular imports.
4. Any schema-impacting change must update specs and related tests in the same change.
