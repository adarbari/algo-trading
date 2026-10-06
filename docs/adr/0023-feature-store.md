# ADR 0023: Feature store: per-feature definitions, feature groups, inputs through `data/`

**Status:** accepted (2026-10-03); steps 1-4 implemented; amended by [0046](0046-market-entity-features-and-non-tradable-ids.md) (`FeatureGroup.entity`: market groups in `rollups/market/<name>@vN`). Extends [0007](0007-point-in-time-data.md)
(features are `name@version`, precomputed nightly) and [0016](0016-four-data-layers.md) (rollups
are L1 / L2 data). Code: `src/algotrade/features/` (`framework/feature.py`, `framework/declaration.py`,
`registry.py`, `catalogue.py`, `rollups/*`, `expressions/*`, `site.py`),
`src/algotrade/data/feature_inputs.py`, `src/algotrade/services/features.py`. Expression
features: `config/site/features/*.toml`. Catalogue: [docs/data/features.md](../data/features.md).

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
  stored columns change. Until group features can move between groups (track step 5) a group
  feature's version is its group's, and the declaration checks it; an expression feature has
  its own.
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

### Step 3: expression features, virtual by default
Owner decisions (2026-10-03): expressions are declared in TOML; virtual by default,
`materialise = true` opts in; definitions are per feature and a group is re-versioned only
when its stored columns change; re-versioned groups store 32-bit floats.

- **The language** (`features/expressions/`; [configuration.md](../configuration.md#expression-features)):
  a small, typed formula language, parsed and evaluated by our own code (never Python `eval`):
  literals, `group.column` references to stored features (the registered version), other
  expression features and the feature's own `params` by name, `+ - * /`, comparisons,
  `and or not`, `if`, `abs min max log sqrt clip coalesce is_null one_of exists`. Types (number,
  bool, string / category, date) are checked at load against the catalogue; a string compared
  with a label must be one of its categories. Null is UNKNOWN and propagates (Kleene `and` /
  `or`; division by zero, `log` of a value <= 0 and non-finite results are null);
  `exists(group)` tells "no row for this instrument" (false) from "no rows for the session"
  (null). Evaluation is vectorised over a frame of stored columns: one session or a range.
- **Definitions** live in `config/site/features/<theme>.toml` (`expr`, `dtype`, `unit`,
  `description`, `null_meaning`, `kind` (`expression` / `label`), `valid_range`, `categories`,
  `params`, `materialise`, `version`), typed by the one settings loader. An expression feature is
  `<name>@v<N>`, selectable as `feature.<name>`; names are unique across groups and expressions.
  The dependency graph is checked at load (a cycle names its path). The site's `FeatureSet`
  (`features/site.py`) joins the code groups and the expressions.
- **Virtual by default**: `services/features.py` reads only the stored columns a formula needs
  (column-pruned reads) and evaluates on read, for selections (`feature.<name>` fields),
  `FeatureView` (`expressions=`) and series over a date range.
- **Materialised**: `materialise = true` makes the expression a one-feature group
  `rollups/instrument/<name>@v<N>` (one table per materialised feature, so a new expression
  version is a new table without re-versioning anything else), computed by the `rollups` task
  after its inputs. Used when a group reads the expression: `div_yield` feeds `iv30@v1`.
- **Moved to expressions**: `liquidity_class` (the `liquidity_class@v1` group is dropped; its
  thresholds are params; `option_tier`, `option_chain_oi`, `option_chain_volume`,
  `liquidity_high`, `liquidity_medium` are expression features too), `div_yield`,
  `market_cap` (its status needs the count's period end against the session, so
  `market_cap_status` stays in `fundamentals`), `pct_from_high_52w`, `pct_from_low_52w`,
  `iv_hv_spread`, `iv_hv_ratio`; new `near_52w` (HIGH / LOW / BOTH / NONE within `within` = 10%).
- **Slimmer groups**: `price_stats@v2`, `dividends@v2`, `fundamentals@v2`, `iv_history@v2` store
  the remaining float columns as `float32` (a field type end to end: `Feature.dtype`, column
  typing, table schemas, the selection catalogue). The v1 tables stay readable until
  `algotrade-ingest retire-features --group <name>@v1` deletes them; it checks first that the
  replacement covers every stored session (`--dry-run` reports sizes). Stale selection fields
  (`rollup.price_stats@v1.pct_from_high_52w`) fail with the field that replaced them; site
  configs reference none (migration, not a deprecation cycle).
- **Ranges stay flags**: real data has realised vols up to 12.3 and yields up to 8.3 (data
  glitches or extreme names); values outside a `valid_range` are kept and reported by the
  feature-quality checks (step 7 of the track below).

### Step 4: user expression features (L4)
Owner-approved (2026-10-03). Users declare expression features in
`config/users/<id>/features/<theme>.toml` ([configuration.md](../configuration.md#user-features)):

- **Same schema, same loader**: `feature_definitions(docs, owner)` types them exactly like the
  site's (secret-looking keys rejected); `materialise` is not allowed in v1: a user feature is
  always virtual (a stored table per user feature would be per-user market data).
- **Namespacing**: `feature.<name>` resolves in the user's catalogue (the site's plus their
  own), like their selections and presets. A user feature may not shadow a site feature's
  name (the error names both files), so a field means the same for everyone who sees it.
  They are built on top of the built site set (`build_expressions(..., base=site)`;
  `FeatureSet.with_user`): user formulas read stored features, site expressions and the user's
  own; site formulas never see user ones, so a cycle can only run through user features.
- **Catalogue and runs**: `services.features.catalogue(store, user)` is what the selection
  catalogue, `GET /features` (`scope = "user"`, `owner`) and the Explore ticker table /
  compare use for the caller (`ALGOTRADE_USER`); another user's features are never in it. A
  resolved config carries the definitions of the user features its selection reads
  (transitively, `ResolvedConfig.features`); they join its hash, and screens and backtests
  evaluate the selection with them (`config_features`).
- **Read-only API now**: write / edit endpoints come with the screener builder UI.
  `algotrade-backtest config validate-features` checks a user's files and prints each
  feature's type, inputs and a sample on the latest session.

### The track
1. **Feature definitions + groups + catalogue** (done).
2. **Inputs through `data/`** (done).
3. **Expression features, virtual by default; slimmer float32 groups** (done; above).
4. **User expression features** (L4, `config/users/<id>/features/*.toml`; done, above).
5. **Features by name for group features**: unique, group-independent names; copies become
   references to the source feature; features can move between groups without a new name
   (expression features already have such names).
6. **Cross-sections**: `cross_section` features (ranks, z-scores within the universe or a
   sector).
7. **Quality**: nightly checks of null rates and `valid_range` per feature (out-of-range
   values are reported, never clipped).
8. **New grains**: `market`, `contract`, `sector` entities and their tables, only when a feature
   needs one.

## Consequences
- Adding a column means writing its meaning, unit and null meaning next to the compute; the
  catalogue and the selection catalogue follow from the registry.
- `Rollup` is now `FeatureGroup` (`ROLLUPS` → `GROUPS`, a module's `ROLLUP` → `GROUP`); tables,
  field names, versions, the `rollups` task and `rollups.toml` are unchanged.
- A new input table gets its read in its `data` owner and an entry in `data/feature_inputs.py`,
  never a loader in `features/`.
- Real data already exceeds some ranges (a realised vol above 5, a yield above 1 on 2026-10-02):
  ranges flag implausible values for the quality checks of step 7; they never change stored data.
- Step 3: a formula over existing features is a TOML entry, not code. Measured on the real
  store (2026-10-03): the moved features reproduce v1 on 10 sessions from 2024-10-03 to
  2026-10-02 (116k rows: every liquidity class and option tier identical; numbers within
  float32 rounding, relative error <= 1.5e-7 away from zero); two years of v1 tables
  (822 MB) become 489 MB of v2 tables plus `div_yield@v1`; evaluating every expression for all
  12.6k instruments of a session takes ~0.1 s, a two-year series of one feature 4-9 s.
