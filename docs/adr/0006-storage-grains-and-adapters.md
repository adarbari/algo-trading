# ADR 0006: Storage organised by data grain, Parquet + DuckDB, swappable adapters

**Status:** accepted (2026-10-02); raw retention amended by [0014](0014-cboe-options-source.md). Spec: [docs/data/storage.md](../data/storage.md).

## Context
We need ticker-level, ticker-day and ticker-day-time data (and more), stored for free now,
with the freedom to move to object storage or a database later.

## Decision
- Model data by **grain**: reference, event, bar(interval), chain snapshot, tick (reserved),
  universe, cross-section, feature, result. Daily and intraday bars are one grain
  with an `interval` column.
- Tiers: `raw/` (as received, kept forever) → `normalized/` → `features/` → `results/`,
  plus a DuckDB catalog.
- Local backend: **Parquet** files partitioned by time and sorted by `instrument_id`,
  queried with **DuckDB**. Default `ALGOTRADE_DATA_URL=file://./var/data`.
- Callers use `Protocol` interfaces per grain (`BarStore`, `ChainStore`, …). Only
  `storage/backends/` knows about paths and files.
- Every backend must pass the shared contract test suite in `tests/contract/storage/`.

## Consequences
- Moving to S3-compatible storage is a new backend plus a URL change; DuckDB reads the
  same Parquet files there.
- Partitioning by ticker is explicitly rejected: around 10k instruments would create a
  huge number of tiny files.
