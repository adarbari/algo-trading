# ADR 0023: Feature store: per-feature definitions, feature groups, inputs through `data/`

**Status:** accepted (2026-10-03); steps 1-2 implemented. Extends [0007](0007-point-in-time-data.md)
(features are `name@version`, precomputed nightly) and [0016](0016-four-data-layers.md) (rollups
are L1 / L2 data). Code: `src/algotrade/features/` (`framework/feature.py`, `framework/declaration.py`,
`registry.py`, `catalogue.py`, `rollups/*`), `src/algotrade/data/feature_inputs.py`. Catalogue:
[docs/data/features.md](../data/features.md).

## Context
Phase 2b built eight rollups. Each declared a bare `{column: type}` mapping: nothing said what a
column means, its unit (is `iv30` 0.25 or 25?), why it can be null, or what it is computed from,
so a selection author, a UI label or a nightly email had to read the compute. Inputs were read
by hand-written loaders in `features/framework/inputs.py`, which called seven `data` modules: the
knowledge of how each table is read point in time for features lived outside its owner. Next come
user-defined expressions (an IV-HV spread a user writes in a config), more groups, and features
at other grains; they need one model of what a feature is.

## Decision
- **A feature** is one named, typed column: `<group>.<column>@v<N>` (selectable, unchanged, as
  `rollup.<group>@v<N>.<column>`). It declares `entity` (`instrument`; `market`, `contract`,
  `sector` are reserved and added only when a feature needs that grain), `kind` (`window`: one
  entity's history up to the session; `chain`: one session's option chain; `expression`:
  arithmetic or logic over other features of the row; `cross_section`: across entities on one
  session; `label`: a status, tier or class), `dtype`, `unit` (`decimal` 0.25 = 25%,
  `pct_points` 25 = 25%, `ratio`, `usd`, `usd_per_share`, `shares`, `count`, `sessions`, `days`,
  `date`, `flag`, `category`, `text`), `description`, `null_meaning` (null is UNKNOWN, never
  zero), an optional `valid_range` (a sanity bound: values outside are kept, never clipped) and
  `categories` (a label's closed set), `inputs` (other features or raw `table.column` fields) and
  a `version`. Names are qualified by their group while columns repeat across groups (`close`,
  `iv30`, `div_yield` are copies today).
- **A feature group** is how features are computed and stored together: `FeatureGroup`
  (`name@vN`, table `rollups/instrument/<name>@vN`, params from `rollups.toml`, inputs + lookback,
  a pure compute) declaring its `FEATURES`; the stored types and column order come from them. The
  eight rollups are the first groups, with byte-identical output.
- **Versioning.** Definitions are versioned per feature; a group is re-versioned only when its
  stored columns change. Until features can move between groups (step 3) a feature's version is
  its group's, and the declaration checks it.
- **One registry** (`features/registry.py`): `GROUPS` in dependency order, `FEATURES` by key, and
  `feature(name)` by key or selection field (descriptions and units for the UI and email). The
  **feature catalogue** `docs/data/features.md` is generated from it (`make features-doc`); a
  fitness test fails when it is stale, and others check every stored column is documented, its
  inputs resolve and golden output has the declared types, ranges and categories.

### Step 2: inputs through data
- Features ask `algotrade.data` for an input **by table name**: `data.feature_inputs.load_input`
  (`INPUTS`: bars, earnings snapshots, chain partitions, events by event date, the Treasury curve,
  share facts; any group table through the generic stored-group reader, with this run's rows
  winning). Each table's read lives in its owner (`prices.session_bars`,
  `events.events_by_event_date`, `rates.curve_as_rows`, ...). `features/` never imports storage
  or a domain reader (import-linter; ownership `feature-input-loading`).

### The track (steps 3-7 are direction, not built)
1. **Feature definitions + groups + catalogue** (done).
2. **Inputs through `data/`** (done).
3. **Features by name**: unique, group-independent names; copies become references to the source
   feature; selections, `FeatureView` and screeners may name a feature directly (the `rollup.`
   field names keep working); features can move between groups without a new name.
4. **Expression features in config**: a small typed expression language over features
   (`iv30 - hv30`), validated against the catalogue, in `config/site/features.toml` and then per
   user (L4, `config/users/<id>/features.toml`), versioned per feature.
5. **Virtual by default**: expression features are computed at read time (`FeatureView`, the
   selection engine) from stored features; a group materialises one only when reading it is too
   slow or it feeds another group.
6. **Quality and cross-sections**: nightly checks of null rates and `valid_range` per feature;
   `cross_section` features (ranks, z-scores within the universe or a sector).
7. **New grains**: `market`, `contract`, `sector` entities and their tables, only when a feature
   needs one.

## Consequences
- Adding a column means writing its meaning, unit and null meaning next to the compute; the
  catalogue and the selection catalogue follow from the registry.
- `Rollup` is now `FeatureGroup` (`ROLLUPS` → `GROUPS`, a module's `ROLLUP` → `GROUP`); tables,
  field names, versions, the `rollups` task and `rollups.toml` are unchanged.
- A new input table gets its read in its `data` owner and an entry in `data/feature_inputs.py`,
  never a loader in `features/`.
- Real data already exceeds some ranges (a realised vol above 5, a yield above 1 on 2026-10-02):
  ranges flag implausible values for the quality checks of step 6; they never change stored data.
