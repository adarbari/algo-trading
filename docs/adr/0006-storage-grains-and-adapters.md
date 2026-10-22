# ADR 0006: Storage organised by data grain, Parquet + DuckDB, swappable adapters

**Status:** accepted (2026-10-02); amended 2026-10-22 (SQLite as a derived index store, below); a derived history copy per (table, year) added by [0060](0060-history-copy.md); raw retention amended by [0014](0014-cboe-options-source.md); layers added by [0016](0016-four-data-layers.md). Note: tables are plain Parquet read with pyarrow today; DuckDB as the query engine and catalog is planned, not yet used. Spec: [docs/data/storage.md](../data/storage.md).

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

## Amendment 2026-10-22: SQLite as a derived, rebuildable index beside Parquet (Ideas only)
Owner decision 2026-10-22 (`docs/decisions/log.md`, "Ideas ranking rule, store and licence
(confirmed)"). Parquet stays the store of domain facts; this adds one **derived index store**
and no second source of truth.

- **What:** the per-viewer Ideas lists (pointers and ranks with a stamp), in one SQLite file
  `<data root>/indexes/ideas.sqlite`. Only a backend builds the path.
- **Owner:** `storage/indexes/ideas.py` (Protocol `IdeasIndex`; SQLite and memory backends,
  both under a contract test in `tests/contract/storage/`).
- **Derived and rebuildable:** every row is computable from `results/screen_runs` and
  `results/screen_picks`. The file is never in the release manifest, backups or the clone. A
  missing or stale file (stamp mismatch) means the page computes the list live; it is never
  served wrong.
- **Two engines remain the rule:** Parquet for domain data and SQLite for operational state
  and this one index ("Data stores" decision, 2026-10-22); no third engine, and no other
  page gets an index without its own decision. DuckDB stays a future query engine.
