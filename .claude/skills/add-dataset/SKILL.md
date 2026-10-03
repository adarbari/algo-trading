---
name: add-dataset
description: Add a new stored dataset or data grain (e.g. intraday bars, earnings events, futures contracts, a new reference attribute). Use when changing what is stored, its schema, or how it is partitioned.
---

# Add a dataset

Read first: `docs/data/storage.md`, `docs/data/instruments.md`, ADRs 0006, 0007 and 0009.

**Ownership check (ADR 0019):** add a `[[table]]` entry with exactly **one** producing
module to `architecture/ownership.toml` (a test enforces it). Reading it for consumers goes
through the market-data read owner (`storage/readers.py` → `algotrade/data/`, R2), with the
one snapshot rule; never add another `latest_date(` call site. Writing it goes through the
ingest loop owner (run records, raw save, stamping, id resolution), not a copy of it. New
site settings for it are read by the settings owner and must drive code (a test checks).

1. **Pick the grain:** reference, event, bar(interval), chain snapshot, universe,
   cross-section, feature or result. New intervals of bars are **not** new datasets; add
   the `interval` value. Only create a new grain with an ADR.
2. **Schema:** add or extend it in `storage/schemas.py`, including the common columns
   (`instrument_id`, `ts`, `session_date`, `knowledge_ts`, `source`, `run_id`).
   Bump the schema version; breaking changes need a migration and an ADR.
3. **Interface:** add read and write methods to the grain's `Protocol` in
   `storage/interfaces.py`. Reads accept `as_of`.
4. **Backend:** implement it in every backend under `storage/backends/`. Partition by time
   and sort by `instrument_id`; never partition by ticker.
5. **Contract tests:** extend `tests/contract/storage/` (round-trip, `as_of`,
   idempotent rewrite, schema rejection). Every backend must pass.
6. **Golden fixtures:** if backtests or screeners will read it, add synthetic fixtures so
   CI exercises it.
7. Update `docs/data/storage.md` and run `make check`.
