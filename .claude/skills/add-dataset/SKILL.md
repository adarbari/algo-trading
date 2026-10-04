---
name: add-dataset
description: Add a new stored dataset or data grain (e.g. intraday bars, earnings events, futures contracts, a new reference attribute). Use when changing what is stored, its schema, or how it is partitioned.
---

# Add a dataset

Read first: `docs/data/storage.md`, `docs/data/instruments.md`, ADRs 0006, 0007 and 0009.

**Ownership check (ADR 0019):** add a `[[table]]` entry with exactly **one** producing
module to `architecture/ownership.toml` (a test enforces it). Reading it for consumers goes
through the market-data read owner (`algotrade/data/`: add a function to the matching module; the folder is at the 10-module
cap, so a new module needs a **split by kind first**), with the one snapshot rule (`data.reference.snapshot`);
never add another `latest_date(` call site. Writing it goes through the
ingest loop owner, `IngestRun` in `apps/ingestion/.../tasks/framework/run.py` (run records, raw
save, stamping, id resolution), not a copy of it. New site settings for it are read by the
settings owner and must drive code (a test checks).

0. **Where it goes:** schema in `storage/tables/`, backends in `storage/backends/`, reads in `data/`, the task in `tasks/<domain>/` (`grep -n purpose architecture/layout.toml`); no fit: new folder, `add-responsibility` step 3. Tests mirror it; if a folder is at 8+ modules, plan the split (`make layout`).
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
   `derived` or `maintenance`; a new domain folder is declared in `architecture/layout.toml`
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
8. Update `docs/data/storage.md` and run `make check`.
