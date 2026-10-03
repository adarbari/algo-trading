# ADR 0005: Ingestion is the only writer of market and feature data

**Status:** accepted (2026-10-02); amended 2026-10-03 by ADR 0027 (vendor SDKs, credentials
handling and source adapters now live in the shared package `libs/sources`, `algotrade_sources`)

## Context
If several apps write data, nobody owns its quality and backtests stop being reproducible.

## Decision
- `storage/` exposes separate `readers` and `writers` facades. Only `apps/ingestion` (and
  the jobs it runs) may import `writers`. import-linter enforces this.
- Vendor SDKs, credentials and source adapters live only in `apps/ingestion/sources/`.
- Results of user-triggered jobs (for example a backtest from the UI) are written to the
  `results` grain through a separate `ResultWriter` that `services/` may use. Market and
  feature data stay ingestion-only.

## Consequences
- Data lineage is simple: every market or feature row traces back to an ingestion run.
- The API and backtest apps can run with read-only storage credentials when hosted.
