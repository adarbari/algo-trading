# ADR 0005: Ingestion is the only writer of market and feature data

**Status:** accepted (2026-10-02); amended 2026-10-03 by ADR 0027 (vendor SDKs, credentials
handling and source adapters now live in the shared package `libs/sources`, `algotrade_sources`); amended by ADR 0028 (the API's one write: its live-quote log, `live/option_quotes`)

## Context
If several apps write data, nobody owns its quality and backtests stop being reproducible.

## Decision
- `storage/` exposes separate `readers` and `writers` facades. Only `apps/ingestion` (and
  the jobs it runs) may import `writers`. import-linter enforces this.
- Vendor SDKs, credentials and source adapters live only in `apps/ingestion/sources/`.
- Results of user-triggered jobs (for example a backtest from the UI) are written to the
  `results` grain through a separate `ResultWriter` that `services/` may use. Market and
  feature data stay ingestion-only. Job-written results include `results/edge_eval` (an edge's
  evaluation, ADR 0053), `results/winners_study` and `results/edge_paper` (the forward paper
  record of the edges a user follows, written by the nightly `edge-signals` job, ADR 0053
  amendment 2026-10-09).

## Consequences
- Data lineage is simple: every market or feature row traces back to an ingestion run.
- The API and backtest apps can run with read-only storage credentials when hosted.
