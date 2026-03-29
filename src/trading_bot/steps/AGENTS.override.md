# Steps Package Override

Applies inside `src/trading_bot/steps/`.

## Folder Meaning
1. `steps` is the pipeline execution layer.
2. It contains discrete units of work that transform inputs into normalized artifacts or reports.
3. Treat modules here as runnable processing stages, not generic infrastructure.
