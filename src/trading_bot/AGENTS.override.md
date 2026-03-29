# Trading Bot Package Override

Applies inside `src/trading_bot/`.

## Package Meaning
1. `trading_bot` is the main application package boundary.
2. It organizes the system into infrastructure, external adapters, contracts, pipeline stages, and orchestration.
3. Prefer placing code in the most specific subpackage instead of growing package-root modules.
