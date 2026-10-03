---
name: add-feature
description: Add a computed feature (a rollup: indicator, IV rank, yield, momentum score) to the rollup framework and the nightly pipeline. Use whenever strategies or screeners need a new derived input.
---

# Add a feature (a rollup)

Read first: ADR 0007, `docs/data/layers.md` ("Rollups as built") and an existing rollup
(`src/algotrade/features/rollups/price_stats.py`).

**Ownership check (ADR 0019, `rollup-computation`):** the framework
(`features/framework/`) loads inputs, keeps each session point in time and types the output;
the definition is a pure compute module in `features/rollups/`; the `rollups` ingestion task
(`tasks/derived/rollups.py`) is the single producer of every `rollups/instrument/...` table.
Never read storage or `algotrade.data` inside a definition (import-linter enforces it), and
never write a new task for a rollup. `make ownership` and `make dupes` must pass.

0. **Where it goes:** look the kind up in the "Where does this go?" table (CLAUDE.md,
   Directory layout) and its folder in `architecture/layout.toml`. Here:
   `features/rollups/<name>.py`; a new input loader in `features/framework/`. If no folder
   fits, add one for the new kind (`.claude/skills/add-responsibility`, step 3); never park
   code in a neighbouring folder. Tests go in the mirrored folder; run `make layout` and
   plan a split if the folder is at 8+ modules.
1. **Declare it** in `src/algotrade/features/rollups/<name>.py` as `ROLLUP = Rollup(...)`:
   `name`, `version` (1), a description, `inputs` (`Input(table, lookback=sessions or
   lambda params: ..., required=True)`), `columns` (`{"col": "float" | "int" | "bool" | "str"
   | "date"}`), the pure `compute(inputs, session, params) -> frame` (``instrument_id`` + the
   declared columns), and `params` (a frozen dataclass of defaults, validated in
   `__post_init__`; `None` if it takes none).
2. **Inputs** must have a loader in `features/framework/inputs.py` (`bars/1d` split-adjusted
   as of each session, `events/earnings` snapshots, `events/dividend` / `events/split` by
   event date, `rates/treasury` the curve the session sees, `chains/*` partitions). A new
   input table gets a loader there that reads through `algotrade.data` (extend the data
   owner if needed). `compute` receives only rows on or before its session; missing history
   is null (UNKNOWN), never zero.
   **Another rollup's output** is an input like any other: `Input("rollups/instrument/
   price_stats@v1", lookback=...)` hands `compute` that rollup's rows (with `session_date`)
   for the session and the lookback; `None` (NO_INPUT when required) when the session has
   none. The registry orders rollups by dependency and refuses cycles; never call another
   rollup's `compute` yourself. Test a chain with `runner.compute_in_memory` (no writes).
3. **Pure computation:** pricing and volatility maths belong in `quant/`
   (`black_scholes`, `implied_vol`, `realized_vol` (1-d or sessions x instruments),
   `rates`; ADR 0021), sessions in `core/time/calendar.py`.
4. **Register it** in `src/algotrade/features/registry.py` (`ROLLUPS`; the order is computed
   from the dependencies). That alone makes it computed by the `rollups` task (nightly and
   `algotrade-ingest rollups --from/--to`), after the rollups it reads, and selectable as
   `rollup.<name>@v1.<column>`.
5. **Harness, same PR:** a `[[table]]` entry for `rollups/instrument/<name>@v1` owned by
   `tasks/derived/rollups.py` in `architecture/ownership.toml`; a `["<name>@v1"]` section in
   `config/site/rollups.toml` if it has params (every key must drive code);
   `tests/architecture/test_rollups.py` checks all of this.
6. **Changing an existing rollup's logic or a window named in a column?** Create
   `name@v2`; do not edit v1. Update dependents explicitly.
7. **Tests** (`tests/unit/features/rollups/`): hand-computed values on a small stored series
   (`tests/helpers/rollup_store.py`), missing history / gaps are null, a backfill equals the
   per-session compute, and anything adjustment-sensitive (splits) as of each session.
8. **Docs:** the rollups table in `docs/data/layers.md` and the selectable fields in
   `docs/configuration.md`.
9. **Baseline:** if strategies or screeners use it, run `make baseline` and explain the diff.
10. Run `make check`; after merge, backfill with `algotrade-ingest rollups --from D --to D
    --only <name>@v1`.
