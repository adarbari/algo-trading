---
name: add-dataset
description: Add a new stored dataset or data grain (e.g. intraday bars, earnings events, futures contracts, a new reference attribute). Use when changing what is stored, its schema, or how it is partitioned.
---

# Add a dataset

Read first: `docs/data/storage.md`, `docs/data/instruments.md`, ADRs 0006, 0007 and 0009.

**Ownership check (ADR 0019):** add a `[[table]]` entry with exactly **one** producing
module to `architecture/tables.toml` (a test enforces it). Reading it for consumers goes
through the market-data read owner (`algotrade/data/`: add a function to the matching module; the folder is at the 10-module
cap, so a new module needs a **split by kind first**), with the one snapshot rule (`data.reference.snapshot`);
never add another `latest_date(` call site. Writing it goes through the
ingest loop owner, `IngestRun` in `apps/ingestion/.../tasks/framework/run.py` (run records, raw
save, stamping, id resolution), not a copy of it. New site settings for it are read by the
settings owner and must drive code (a test checks).

0. **Where it goes:** schema in `storage/tables/`, backends in `storage/backends/`, reads in `data/`, the task in `tasks/<domain>/` (`grep -n purpose architecture/*layout*.toml`); no fit: new folder, `add-responsibility` step 3. Tests mirror it; if a folder is at 8+ modules, plan the split (`make layout`).
1. **Pick the grain:** reference, event, bar(interval), chain snapshot, universe,
   cross-section, feature or result. New intervals of bars are **not** new datasets; add
   the `interval` value. Only create a new grain with an ADR.
2. **Schema:** add or extend it in `storage/tables/schemas.py`, including the common columns
   (`instrument_id`, `ts`, `session_date`, `knowledge_ts`, `source`, `run_id`).
   Bump the schema version; breaking changes need a migration and an ADR.
3. **Interface:** add read and write methods to the grain's `Protocol` in
   `storage/tables/interfaces.py`. Reads accept `as_of`.
4. **Backend:** implement it in every backend under `storage/backends/`. Partition by time
   and sort by `instrument_id`; never partition by ticker.
5. **Contract tests:** extend `tests/contract/storage/` (round-trip, `as_of`,
   idempotent rewrite, schema rejection). Every backend must pass.
6. **Golden fixtures:** if backtests or screeners will read it, add synthetic fixtures so
   CI exercises it.
7. **Ingestion task:** write `tasks/<domain>/<dataset>.py` (domain: `reference`, `market`,
   `derived` or `maintenance`; a new domain folder is declared in `architecture/layout*.toml`
   first) with only the task's own logic (what to
   fetch, how to combine frames, task stats) inside `with IngestRun(ctx, TASK, session) as
   run:` using `run.fetch`, `run.attempt` (per-item status), `run.resolve`, `run.write`
   (stamps + validates) and `run.partial`. Never write the loop: no `RunRecord`,
   `new_run_id`, `raw.put` or stamping in a task. Then declare it **once** in
   `tasks/framework/registry.py` (name, description, module, tables = the `[[table]]` entries,
   sources by name, settings section, params, `run(ctx, params)` applying defaults from
   settings). The CLI command (`algotrade-ingest <name>` and `run <name>`) comes from the
   declaration; add a `Step` to `workflows/nightly/nightly.py` `NIGHTLY` if it runs nightly.
   Helpers it needs stay in the same domain folder (`tests/architecture/test_layout.py`).
   `tests/architecture/test_task_registry.py` checks tables and CLI reachability.
8. **Point-in-time checklist** (the source side is in `add-data-source` step 10):
   - Readers filter `known_from <= S` and take the latest version per key.
   - Periodic snapshots are append-only per session; never overwrite an earlier session's rows.
   - A field known only later (e.g. `instrument_id`) is filled as its own later version, with
     its own `known_from`, never by rewriting the earlier row.
   - A table over a restricted-licence source says so in its `tables.toml` note and its features carry `licence` (ADR 0028).
9. Update `docs/data/storage.md`, run `make changed`, push (CI is the full gate).

## Choosing a store

Parquet or SQLite (or a file)? The rule and its triggers are `docs/data/storage.md`, "Choosing a
store": Parquet for analytical domain data, SQLite only for small, mutable or keyed operational
state and derived rebuildable indexes, TOML files for human-edited configuration; no third engine
without an ADR. Measure on a real-shaped store first (`docs/perf/page-latency-bar.md`).

## Changing a derived store

Changing a derived store's key, signature or schema (history copy, release, caches) ships its
rebuild in the same PR, or the read self-heals on first use. Add a fitness test that builds a store
in the old format and asserts the new code detects it and the rebuild task repairs it. A read that
falls back to a full scan logs and counts it. (#814 changed the history-copy signature without a
rebuild: /regime went 0.5 s -> 12.6 s on the real store.)

## Writers and the ingest lock

A writer outside the ingest lock must be crash-safe against `recover_unpublished` (ADR 0022: it
drops unpublished ingest runs; it runs on every writing command, `cli/main.py:578`, under the lock); the default is to take the lock. (The
edge-verdicts post-session step ran outside it and a CLI ingest dropped its pending rows.)
