---
name: add-feature
description: Add a computed feature to the feature store: a formula over existing features (a ratio, spread, label from thresholds) as a TOML expression feature with no code, or a new documented column of a feature group (an indicator, IV rank, momentum score) computed nightly. Use whenever strategies or screeners need a new derived input.
---

# Add a feature

**A fact a page or Ideas needs per instrument is a feature, even if only one page shows it**
(ADR 0038): the read model never computes it per request and the browser never derives it.
`rollup.nearest_expiry@v1` (DTE) and `feature.earnings_before_expiry` are the example
(read-model PR 3). Pages read it by name through GraphQL `features(names)`
(`.claude/skills/add-graphql-field`).

**First: is it a formula over features that already exist?** (`iv30 - hv30`, `close /
high_52w - 1`, a HIGH / LOW label from thresholds, `shares x close`.) Then it is an
**expression feature: a TOML entry, no code** (ADR 0023 step 3):

1. Add `[name]` to the theme file in `config/site/features/` (`price.toml`,
   `volatility.toml`, `fundamentals.toml`, `liquidity.toml`, `vrp.toml`; a new theme is a new file):
   `expr`, `dtype`, `unit`, `description`, `null_meaning`, and as needed `kind = "label"` +
   `categories`, `valid_range = [min, max]` (`inf` open; a flag, never a clip), `params = {...}`
   (thresholds as named constants), `version` (bump it when the formula changes). The language
   (names `group.column`, other expressions and params by name; `+ - * /`, comparisons,
   `and or not`, `if abs min max log sqrt clip coalesce is_null one_of exists`; null
   propagates) is in `docs/configuration.md` "Expression features".
2. Virtual by default: it is computed on read (`feature.<name>` in selections, `FeatureView`
   `expressions=`, `services.features.read_expressions` for a series). Set `materialise = true`
   only when a feature group reads it or reading it is too slow; it is then stored as
   `rollups/instrument/<name>@v<N>` by the `rollups` task (add its `[[table]]` to
   `architecture/ownership.toml`).
3. `make features-doc`; tests: a case in `tests/unit/features/test_site.py` (values, nulls,
   categories). A bad formula fails at load naming the file, the feature and the position.

**Site or user?** A formula one person wants for their own screens is a **user feature**:
the same `[name]` entry in `config/users/<id>/features/<theme>.toml` (git-ignored; ADR 0023
step 4). It is always virtual (`materialise` is rejected), visible only to that user
(`feature.<name>` in their selections and configs, Explore columns, the GraphQL `catalogue` with
`scope = "user"`), may read site features but never take a site feature's name, and its
definition joins the hash of every config that reads it. Check it with
`algotrade-backtest --user <id> config validate-features` (type, inputs, a sample on the
latest session). Promote it to `config/site/features/` (a PR, with a test and
`make features-doc`) when others need it, it must be stored, or a group reads it; give it
the same name only after the user's copy is removed (a user feature cannot shadow a site one).

Otherwise (it needs history, a chain, an input table, or maths that is not a formula over a
row), it is a **column of a feature group**:

Read first: ADR 0007, ADR 0023 (the feature store), `docs/data/layers.md` ("Rollups as
built"), the catalogue `docs/data/features.md` (does the feature already exist?) and an
existing group (`src/algotrade/features/rollups/price/price_stats.py`).

**Ownership check (ADR 0019: `rollup-computation`, `feature-metadata`,
`feature-input-loading`):** a feature is one documented column of a **feature group**. The
framework (`features/framework/`) keeps each session point in time and types the output; the
group is a pure compute module in `features/rollups/` that declares its features; inputs are
read by `data/feature_inputs.py` (asked by table name); the `rollups` ingestion task
(`tasks/derived/rollups.py`) is the single producer of every `rollups/instrument/...` table.
Never read storage or `algotrade.data` inside a group (import-linter enforces it), never add a
loader under `features/`, and never write a new task for a group. `make ownership` and
`make dupes` must pass.

0. **Where it goes:** a feature of an existing group goes in that group's module (a new stored column = a new group version, step 6); a new group in `features/rollups/<kind>/<name>.py` (`price/` daily bars, `options/` chains and implied vol, `corporate/` events and filings); a new input table's read in its owner in `src/algotrade/data/` plus an `INPUTS` entry in `data/feature_inputs.py`; pure maths in `quant/` (`grep -n purpose architecture/layout.toml`); no fit: new folder, `add-responsibility` step 3. Tests mirror it; if a folder is at 8+ modules, plan the split (`make layout`).
1. **Declare its features** in `src/algotrade/features/rollups/<kind>/<name>.py`: `FEATURES = (
   Feature(name, dtype, unit, description, null_meaning, kind, valid_range=..., categories=...,
   inputs=...), ...)` (`features/framework/feature.py`): `dtype` one of `float32 | float | int |
   bool | str | date` (new groups store floats as `float32`); `unit` from `UNITS` (`decimal` 0.25 = 25%, `pct_points` 25 = 25%, `usd`,
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
   price_stats@v2", lookback=...)` hands `compute` that group's rows (with `session_date`)
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
   window named in a column)?** Create `name@v<N+1>`; do not edit the old version. Update
   dependents explicitly, add the old key to `SUPERSEDED` in `features/registry.py` (its
   fields then fail with the field that replaced them), and after the owner's backfill retire
   the old table with `algotrade-ingest retire-features --group <name>@v<N> [--dry-run]`.
   Metadata-only edits (a better description) need no new version.
7. **Tests** (`tests/unit/features/rollups/<kind>/`): hand-computed values on a small stored series
   (`tests/helpers/rollup_store.py`), missing history / gaps are null, a backfill equals the
   per-session compute, and anything adjustment-sensitive (splits) as of each session.
8. **Docs:** the generated catalogue (`make features-doc`), the groups table in
   `docs/data/layers.md` and the selectable fields in `docs/configuration.md`.
9. **Baseline:** if strategies or screeners use it, run `make baseline` and explain the diff.
10. Run `make check`; after merge, backfill with `algotrade-ingest rollups --from D --to D
    --only <name>@v1`.
