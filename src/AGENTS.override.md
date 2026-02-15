# Source Tree Override

Applies inside `src/`.

## Local Rules
1. Keep imports package-qualified under `trading_bot.*`.
2. Avoid writing business logic in CLI entrypoints; keep orchestration in `workflows`.
3. Treat `core` modules as shared infrastructure and `contracts` as schema/config contracts; avoid circular imports.
4. Keep source adapters in `connectors` and runnable pipeline units in `steps`.
5. Any schema-impacting change must update specs and related tests in the same change.
