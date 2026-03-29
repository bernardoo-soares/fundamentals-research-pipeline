# Connectors Package Override

Applies inside `src/trading_bot/connectors/`.

## Folder Meaning
1. `connectors` is the external boundary layer.
2. It represents communication with outside data sources and external systems.
3. Keep source-facing behavior here rather than in orchestration or contracts.
