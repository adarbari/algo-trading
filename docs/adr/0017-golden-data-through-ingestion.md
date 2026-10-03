# ADR 0017: Golden datasets load through ingestion into a separate fixture store

**Status:** accepted (2026-10-03). Applies [0003](0003-golden-master-baseline.md) and [0008](0008-backtests-read-only-from-stores.md).

## Context
Backtests must read only from storage (ADR 0008), and the golden datasets must stay
reviewable and reproducible (ADR 0003).

## Decision
- The committed CSVs in `datasets/golden/` (with SHA-256 checksums) stay the source of truth.
- A `synthetic` source and a `golden` ingestion job load them through the normal writers into
  a **separate fixture store** (`datasets/golden/store`, git-ignored, `make golden-store`);
  tests use an in-memory store built the same way.
- Evaluation, CI and the backtest CLI read that store through `StoreReader`.

| Alternative | Rejected because |
|---|---|
| Commit a Parquet store | Binary diffs; not reviewable |
| Keep a CSV reader in the backtest | A second data path that production never uses |
| Load golden data into the production store | Synthetic symbols collide with real tickers (`AAA` is a real ETF) |

## Consequences
- The golden suite exercises the production read path end to end.
- `golden build|verify|load` are ingestion commands, because only ingestion writes data.
