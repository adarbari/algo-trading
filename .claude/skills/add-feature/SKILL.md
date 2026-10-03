---
name: add-feature
description: Add a computed feature (a documented column of a feature group, e.g. an indicator, IV rank, yield, momentum score) to the feature store and the nightly pipeline. Use whenever strategies or screeners need a new derived input.
---

# Add a feature (a column of a feature group)

Read first: ADR 0007, ADR 0023 (the feature store), `docs/data/layers.md` ("Rollups as
built"), the catalogue `docs/data/features.md` (does the feature already exist?) and an
existing group (`src/algotrade/features/rollups/price_stats.py`).

**Ownership check (ADR 0019: `rollup-computation`, `feature-metadata`,
`feature-input-loading`):** a feature is one documented column of a **feature group**. The
framework (`features/framework/`) keeps each session point in time and types the output; the
group is a pure compute module in `features/rollups/` that declares its features; inputs are
read by `data/feature_inputs.py` (asked by table name); the `rollups` ingestion task
(`tasks/derived/rollups.py`) is the single producer of every `rollups/instrument/...` table.
Never read storage or `algotrade.data` inside a group (import-linter enforces it), never add a
loader under `features/`, and never write a new task for a group. `make ownership` and
`make dupes` must pass.

0. **Where it goes:** look the kind up in the "Where does this go?" table (CLAUDE.md,
   Directory layout) and its folder in `architecture/layout.toml`. Here: a new feature of an
   existing group → that group's module (a new stored column = a new group version, step 6);
   a new group → `features/rollups/<name>.py`; a new input table's read → its owner in
   `src/algotrade/data/` plus an entry in `data/feature_inputs.py` (`INPUTS`), never a loader
   under `features/`; pure maths → `quant/`. If no folder fits, add one for the new kind
   (`.claude/skills/add-responsibility`, step 3); never park code in a neighbouring folder.
   Tests go in the mirrored folder (`tests/unit/features/rollups/test_<name>.py`; inputs:
   `tests/unit/data/`); run `make layout` and plan a split if the folder is at 8+ modules.
1. **Declare its features** in `src/algotrade/features/rollups/<name>.py`: `FEATURES = (
   Feature(name, dtype, unit, description, null_meaning, kind, valid_range=..., categories=...,
   inputs=...), ...)` (`features/framework/feature.py`): `dtype` one of `float | int | bool |
   str | date`; `unit` from `UNITS` (`decimal` 0.25 = 25%, `pct_points` 25 = 25%, `usd`,
   `usd_per_share`, `count`, `sessions`, `days`, `date`, `flag`, `category`, ...); `kind`
   `window | chain | expression | cross_section | label`; say exactly when it is null (null is
   UNKNOWN, never zero); a sane `valid_range` for numbers (values outside are kept, not
   clipped) and `categories` for a label; `inputs` as features (`price_stats.close@v1`) or raw
   fields (`bars/1d.close`). Then `COLUMNS = column_types(FEATURES)` if the compute needs it,
   and `GROUP = FeatureGroup(name, version (1), description, inputs (Input(table,
   lookback=sessions or lambda params: ..., required=True)), FEATURES, compute, params)`: the
   pure `compute(inputs, session, params) -> frame` returns ``instrument_id`` + the feature
   columns; `params` is a frozen dataclass of defaults validated in `__post_init__` (`None`
   if it takes none).
2. **Inputs** must be readable by `data/feature_inputs.py` (`bars/1d` split-adjusted as of
   each session, `events/earnings` snapshots, `events/dividend` / `events/split` by event
   date, `rates/treasury` the curve the session sees, `chains/*` partitions,
   `instruments/shares` by filing date). A new input table gets its point-in-time read in its
   `data` owner and an `INPUTS` entry. `compute` receives only rows on or before its session;
   missing history is null (UNKNOWN), never zero.
   **Another group's output** is an input like any other: `Input("rollups/instrument/
   price_stats@v1", lookback=...)` hands `compute` that group's rows (with `session_date`)
   for the session and the lookback; `None` (NO_INPUT when required) when the session has
   none. The registry orders groups by dependency and refuses cycles; never call another
   group's `compute` yourself. Test a chain with `runner.compute_in_memory` (no writes).
3. **Pure computation:** pricing and volatility maths belong in `quant/`
   (`black_scholes`, `implied_vol`, `realized_vol` (1-d or sessions x instruments),
   `rates`; ADR 0021), sessions in `core/time/calendar.py`.
4. **Register it** in `src/algotrade/features/registry.py` (`GROUPS`; the order is computed
   from the dependencies). That alone makes it computed by the `rollups` task (nightly and
   `algotrade-ingest rollups --from/--to`), after the groups it reads, selectable as
   `rollup.<name>@v1.<column>`, and listed by `feature(name)`. Run `make features-doc` and
   commit `docs/data/features.md` (a fitness test fails when it is stale).
5. **Harness, same PR:** a `[[table]]` entry for `rollups/instrument/<name>@v1` owned by
   `tasks/derived/rollups.py` in `architecture/ownership.toml`; a `["<name>@v1"]` section in
   `config/site/rollups.toml` if it has params (every key must drive code);
   `tests/architecture/test_rollups.py` and `test_features.py` check all of this (every
   column documented, inputs resolve, golden output within ranges and categories).
6. **Changing an existing group's stored columns (a new column, a changed definition or a
   window named in a column)?** Create `name@v2`; do not edit v1. Update dependents
   explicitly. Metadata-only edits (a better description) need no new version.
7. **Tests** (`tests/unit/features/rollups/`): hand-computed values on a small stored series
   (`tests/helpers/rollup_store.py`), missing history / gaps are null, a backfill equals the
   per-session compute, and anything adjustment-sensitive (splits) as of each session.
8. **Docs:** the generated catalogue (`make features-doc`), the groups table in
   `docs/data/layers.md` and the selectable fields in `docs/configuration.md`.
9. **Baseline:** if strategies or screeners use it, run `make baseline` and explain the diff.
10. Run `make check`; after merge, backfill with `algotrade-ingest rollups --from D --to D
    --only <name>@v1`.
