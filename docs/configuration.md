# Configuration: configs, selections and users

The **universe is coverage** (every instrument we ingest). Each strategy or screener works on
its own subset, chosen by a **selection** in a **config**. Configs exist at the site level
(L3, shared) and per user (L4). Decision record: [ADR 0015](adr/0015-configs-selections-users.md).
Where configs sit among the data layers: [data/layers.md](data/layers.md).

## Where configs live

```
config/site/                        L3: reviewed via PR, versioned by git
  defaults.toml                     [screening] and [backtest] defaults
  presets/selections/<id>.toml      shared selections
  presets/strategies/<id>.toml      shared strategy / screener configs
config/users/<user_id>/             L4: git-ignored locally; a DB behind ConfigStore later
  selections/<id>.toml
  strategies/<id>.toml
  features/<theme>.toml             the user's expression features (always virtual)
```

The location comes from `ALGOTRADE_CONFIG_DIR` (default `./config`) or `--config-dir`. Only
`storage/configs/files.py` knows this layout; everything else uses the `ConfigStore`
protocol (`load(scope, kind, name)`, `names`, `users`).

## Objects (`src/algotrade/config/`, pure, no I/O)

```text
Rule           { field, op: eq|ne|in|not_in|gt|gte|lt|lte|between|is_null|not_null, value }
Group          { all: [Rule|Group] } | { any: [Rule|Group] } | { not: Rule|Group }
Selection      { name, where: Group, max_instruments?, order_by? }   # top-N by a field
StrategyConfig { id, kind: screener|strategy, impl, params, selection (preset name or inline),
                 selection_overrides?, schedule?: nightly, exports?: [...],
                 screening?: {...}, backtest?: {...}, extends? (user configs) }
ResolvedConfig { config, selection, settings, user, layers, hash }
UserContext    { user_id }   # a validated label: [a-z0-9_-]{1,64}
```

Parsing errors name the exact path, e.g. `users/alice/strategies/x.selection.where.all[2]: op
must be one of [...]`. A bad config never runs (fail closed).

## Resolution

```
built-in defaults  <  L3 site (defaults.toml + preset)  <  L4 user config  <  run-time overrides
```

- **Find the document.** A user config with the same id overrides the site preset of that id;
  `extends = "<preset id>"` builds a new id on top of a preset; a user-only config needs no
  preset. The `site` user (scheduled site presets) never reads user documents.
- **Merge.** Tables merge deeply; lists are replaced.
- **Selection.** A preset name resolves user-first, then site. A user either **narrows** the
  preset with `selection_overrides` (AND-ed with the preset's rules, so later preset fixes
  still apply) or **replaces** it with its own `selection`. A user can never widen coverage:
  covering a new instrument is a site change.
- **Settings.** `[screening]` and `[backtest]` come from defaults, overridden by the config,
  and are typed at resolve time (`ResolvedConfig.screening`, `.backtest`; see
  [site settings](#site-settings-typed-one-loader)): an unknown key or a bad value fails
  with its path, e.g. `sma_trend [backtest.costs]: unknown keys ['fee']`.
- **Hash.** SHA-256 of everything that affects results (impl, params, selection, schedule,
  exports, settings), not of provenance. Every result row and run record carries `user_id`,
  `config_id` and `config_hash`; `layers` records which files were used.

## Selections

Fields come from a catalogue built from the code, so a typo or a type mismatch fails at load:

| Field | Source table | Example |
|---|---|---|
| `instrument.<column>` | L1 `instruments/reference`; company columns from `instruments/company` | `instrument.security_type`, `instrument.is_leveraged`, `instrument.sector` |
| `rollup.<name>@v<N>.<column>` | `rollups/instrument/<name>@v<N>` (each column a declared feature of the group, `features/registry.py`) | `rollup.option_liquidity@v1.put_tier`, `rollup.price_stats@v2.hv30`, `rollup.price_stats@v2.adv_usd_20d`, `rollup.earnings@v1.days_to_earnings`, `rollup.fundamentals@v2.market_cap_status` |
| `feature.<name>` | an expression feature (`config/site/features/*.toml`, [below](#expression-features)), computed on read from the stored features it names | `feature.liquidity_class`, `feature.near_52w`, `feature.market_cap`, `feature.iv_hv_spread` |

Selectable rollup fields today ([data/layers.md](data/layers.md#rollups-as-built) has the rules;
[data/features.md](data/features.md) gives each one's meaning, unit, valid values and when it is null):

| Rollup | Fields (type) |
|---|---|
| `option_liquidity@v1` | `liq_status`, `put_tier`, `call_tier` (str); `short_put_ok`, `short_call_ok` (bool); `chain_oi`, `chain_volume`, `target_dte`, `expiries_within_60d` (int); `underlying_price`, `iv30`, spreads… (float); `target_expiry`, `chain_asof` (date) |
| `price_stats@v2` | `close`, `sma_20`, `sma_50`, `sma_200`, `ret_20d`, `ret_60d`, `high_52w`, `low_52w`, `hv20`, `hv30`, `hv20_yz`, `adv_usd_20d` (float32); `history_days` (int) |
| `earnings@v1` | `next_earnings_date`, `last_earnings_date` (date); `earnings_time` (str: pre / post / unknown); `days_to_earnings` (int); `date_confirmed` (bool, null today) |
| `dividends@v2` | `div_ttm` (float32); `div_count_ttm` (int); `last_ex_date` (date) |
| `iv30@v1` | `iv30`, `iv30_cboe`, `atm_strike_near`, `spot`, `rate`, `div_yield` (float); `iv30_status` (str); `near_expiry`, `far_expiry` (date); `n_quotes_used` (int) |
| `iv_history@v2` | `iv30`, `iv_rank_252d`, `iv_percentile_252d` (float32); `history_days` (int); `rank_status` (str: UNKNOWN / PROVISIONAL / FULL) |
| `fundamentals@v2` | `shares_outstanding` (float32); `shares_as_of`, `shares_filed` (date); `shares_source`, `market_cap_status` (str) |

Expression features (`feature.<name>`): `liquidity_class` (str: HIGH / MEDIUM / LOW /
UNKNOWN), `option_tier` (str: A-D), `option_chain_known`, `liquidity_high`,
`liquidity_medium` (bool), `option_chain_oi`, `option_chain_volume` (int), `div_yield`
(float32, materialised), `market_cap`, `pct_from_high_52w`, `pct_from_low_52w`,
`iv_hv_spread`, `iv_hv_ratio` (float), `near_52w` (str: HIGH / LOW / BOTH / NONE).

**Superseded fields.** ADR 0023 step 3 replaced `price_stats@v1`, `dividends@v1`,
`fundamentals@v1`, `iv_history@v1` and `liquidity_class@v1`. A selection naming one of their
fields fails at load with the field that replaced it, e.g.
`rollup.price_stats@v1.pct_from_high_52w` -> `feature.pct_from_high_52w`,
`rollup.price_stats@v1.hv30` -> `rollup.price_stats@v2.hv30`,
`rollup.liquidity_class@v1.liquidity_class` -> `feature.liquidity_class`,
`rollup.liquidity_class@v1.chain_oi` -> `feature.option_chain_oi` (`rule_hash` is retired: the
thresholds are the expression's params). Site presets reference none of them.

A rollup with no row for an instrument, or no partition for the session, is UNKNOWN (so is an
expression feature computed from it, unless its formula handles the null): e.g.
`{ field = "rollup.earnings@v1.days_to_earnings", op = "gt", value = 5 }` never selects an
instrument whose next earnings date is unknown.

Evaluation (`engines/selection/`) uses **three-valued logic**: a missing value is UNKNOWN,
UNKNOWN propagates through `all`/`any`/`not`, and only TRUE selects. Missing data therefore
excludes an instrument and is counted, never passed. The audit saved with every run has, per
top-level rule, the counts passed / failed / unknown and the funnel remaining after each rule
(for `all`). Selection is evaluated **as of the run's session** (a backtest's start date, and
each rebalance session with `rebalance_selection`), so backtests never use today's universe.

Example site preset (`config/site/presets/selections/liquid_optionable.toml`):

```toml
name = "liquid_optionable"
[where]
all = [
  { field = "instrument.security_type", op = "in", value = ["COMMON_STOCK", "ADR", "ETF"] },
  { field = "instrument.status", op = "eq", value = "ACTIVE" },
  { field = "instrument.optionable", op = "eq", value = true },
]
```

Example user config narrowing a preset (`config/users/abhinav/strategies/short_premium.toml`):

```toml
extends = "short_premium_liquidity"
schedule = "nightly"
[selection_overrides]
all = [ { field = "instrument.is_leveraged", op = "eq", value = false } ]
```

`[backtest] price_adjustment` (`none` / `splits` / `total_return`, default `splits`) chooses
how stored unadjusted bars are adjusted for corporate actions when a backtest reads them.

### Rebalancing selections

By default a backtest evaluates its selection once, on `start`, and trades that set throughout.
`[backtest] rebalance_selection` re-evaluates it over time (opt-in; follow-up F7):

```toml
[backtest]
rebalance_selection = "monthly"   # none (default) | monthly | weekly | "<N>d"
selection_lag_sessions = 1        # default 1; an integer >= 1
```

| Value | Evaluated on |
|---|---|
| `none` | `start` only (the behaviour without rebalancing) |
| `monthly` | `start`, then the first session of every later calendar month |
| `weekly` | `start`, then the first session of every later ISO week |
| `"<N>d"` | `start`, then every N-th **session** after it (`"21d"`: about monthly) |

Rules (`engines/selection/schedule.py`, `services/backtests/rebalance.py`,
`engines/backtest/universe.py`):

- **Point in time.** Each evaluation is the ordinary selection (`services.selection.select`) on
  that session: the reference snapshot for the session and rollups *for* the session, read as
  of the launch. A rebalance session with no partition of a rollup the selection uses is an
  error (`MissingDataError`), never an empty set that would close every position.
- **Lag.** A set evaluated on session D trades from the bar `selection_lag_sessions` bars after
  D (default: D+1), so a rollup computed after D's close never drives a trade on D. The set
  evaluated on `start` trades from the first bar, as without rebalancing.
- **Exits.** An instrument that leaves the set is closed at the **open** of the effective bar
  (ADR 0002: decisions fill at the next open); open orders for it are cancelled. New members
  join the strategy's `MarketView` from the effective bar's close, so they are bought at the
  next open. Strategies still see only `MarketView` (core): just the eligible instruments.
- **Eligible.** In the set in force AND with a bar on each of the strategy's last
  `max(1, warmup_bars)` bars (no gaps in a warm-up window). Bars are loaded once for the union
  of every instrument ever selected and put on one timeline; an order for an instrument with
  no bar that session waits for its next bar (or a newer order replaces it), and positions are
  marked at their last close. A delisted holding stays marked at its last close (no delisting
  proceeds model yet).
- **Audit.** The run record's `rebalance` holds the frequency, lag, instruments ever selected,
  mean turnover (share of the set added per re-evaluation) and, per evaluation: `evaluated`,
  `effective`, `selected`, `added` / `removed` (listed up to 25, always counted),
  `members_hash`, `survivorship_bias` (reference snapshot after the session) and the selection
  `funnel` (the per-rule audit). `survivorship_bias` of the run is set if any evaluation has it.
- **Hash.** Both keys are part of the config hash when set; a config that does not set them
  keeps its previous hash (they are not written into the defaults).

## Site settings (typed, one loader)

Every `config/site/*.toml` is loaded and validated by `src/algotrade/config/site/settings.py`
alone (ADR 0019 `site-settings`); apps receive frozen dataclasses, never dicts:

| File | Type | Holds |
|---|---|---|
| `defaults.toml` | `ScreeningSettings`, `BacktestSettings` (`CostSettings`, `LimitSettings`) | run defaults, layered per config |
| `sources.toml` | `SourcesSettings` (`VendorSettings` per section) | per-vendor `enabled` and pacing (`min_interval_s`, `max_interval_s`, `start_interval_s`; see [Vendor pacing](#vendor-pacing)), chain workers and `[cboe] priority_symbols`, earnings days, corporate-actions window, SEC refresh days (`[sec_edgar] refresh_days` company details, `facts_refresh_days` share counts; spread over the window by CIK); `[http]` retry cap, circuit breaker, limiter directory and adaptive-pacing rules; raw and staging retention (a vendor section's `raw_retention_days` overrides the global raw window for every raw source in that section: `[sec_edgar]` keeps 7 days; see [storage.md](data/storage.md#retention)); `[quality]` thresholds of the nightly data-quality checks (`max_bar_count_drop`, `max_universe_change`; option chains: `max_chain_fetch_failures` = share of optionable names whose fetch failed (`FETCH_ERROR`, including an open circuit, or `NOT_ATTEMPTED`) above which `chains_fetch` FAILs, default 0.05; `max_chain_stale_share` = share of `STALE_DATA` chains above which `chains_stale` WARNs, default 0.20; both details list the OK / STALE_DATA / NO_CHAIN / NO_STANDARD_SERIES counts. `min_chain_coverage` was replaced by these two and is now rejected) |
| `sources.toml [ibkr]` | `IbkrSettings` (`SourcesSettings.ibkr`) | IB Gateway for the read-only `verify` task (ADR 0026): `enabled` (off by default: a missing section is disabled too), `min_interval_s` (every message, 0.02 = 50/s), `historical_min_interval_s` (10: 60 historical requests per 10 minutes), `market_data_type` (1 live, 3 delayed), `connect_timeout_s`, `request_timeout_s`, `stream_wait_s` (IB dividends tick), `raw_retention_days` (30); `[quality] max_verify_failures` (0.10): the `verification` check FAILs above that share of failing graded checks and WARNs on any |
| `verification.toml` | `VerificationSettings` | the live verification vs IBKR: `[sample]` `core_symbols` (always verified), `rotating` (more per session, by a hash of the session), `option_symbols` + `options_per_symbol` (option quotes compared with our chain), `bar_sessions` (IBKR daily bars per name); `[tolerances]` `close_rel`, `range_rel`, `hv_rel`, `high_52w_rel`, `extreme_rel` (52-week low, the dividend-gap rule), `yield_abs`, `iv_abs`, `spread_band` (option mids, in half-spreads), `max_missing_sessions`, `warn_multiple` (over tolerance by at most this factor: WARN; beyond: FAIL). Defaults are the reconciliation suite's tolerances (testing.md) |
| `universe.toml` (+ `overrides/leveraged_etfs.csv`, `overrides/figi.csv`) | `UniverseSettings` | coverage mode (`nasdaq_trader` / `csv_import`), security types, include / exclude symbols, leverage rules (markers, conventions, patterns, inverse markers, exclusions; regexes are compiled and `leverage_patterns` need a `(?P<n>...)` group); `figi_overrides` from `figi.csv` (columns `symbol`, `figi`, `note`; a composite FIGI or blank for "no FIGI, symbol id"; a malformed FIGI, an unknown column, or a symbol or FIGI listed twice fails with its line; see [instruments.md](data/instruments.md#figi-based-instrument-ids-implemented-phase-18)) |
| `nightly.toml` | `NightlySettings` | `[sessions]` settle margin and catch-up cap, `[alerts]` nightly duration, `[notify]` notifications on/off, the desktop notification and the summary file path; `[notify.email]` the daily summary email (`enabled`, `smtp_host`, `smtp_port`, `max_examples`) |
| `rollups.toml` | each rollup's own params dataclass (`rollup_params` / `load_rollups`) | one `["<name>@v<N>"]` section per rollup that takes parameters; each scalar field of its params dataclass (bool, int, float, str) is a key typed by its default, and the dataclass validates ranges (`price_stats@v2`: `year_sessions`, `min_year_sessions`, `periods_per_year`; `option_liquidity@v1`: DTE window, delta bands; `dividends@v2`: `min_history_days`, `include_special`; `iv30@v1`: `target_days`, `min_days`, `max_days`, `max_spread_pct`, `min_open_interest`, `min_volume`; `iv_history@v2`: `window`, `min_provisional`, `source` (`ours` / `cboe`); `fundamentals@v2`: `stale_days`). A rollup without parameters has no section (a fitness test checks both ways) |
| `features/<theme>.toml` | `FeatureDefinition` per `[name]` (`feature_definitions` / `load_features`) | the site's expression features ([below](#expression-features)); the formula, dtype, unit and categories are then checked against the feature catalogue (`features/expressions/definitions.py`) |

A missing file or key falls back to the dataclass default. Anything else is an error that
names the file, section and key: unknown keys (a typo is never silently ignored), wrong
types (`enabled = "yes"`), out-of-range values (`workers = 0`, a fraction above 1, a
negative interval) and invalid leverage-marker regexes. Every key must also drive code
(`tests/architecture/test_ownership.py`). Credentials never go in these files.

## Expression features

A formula over existing features is a TOML entry, not code (ADR 0023 step 3). Each
`config/site/features/<theme>.toml` (one per theme: `price`, `volatility`, `fundamentals`,
`liquidity`) holds one `[name]` per feature:

| Key | Meaning |
|---|---|
| `expr` | the formula (below); TOML multi-line strings and `#` comments are fine |
| `dtype` | `float`, `float32`, `int`, `bool`, `str` or `date`; the formula's type must fit it |
| `unit` | as for stored features (`decimal`, `ratio`, `usd`, `category`, `flag`, ...) |
| `description`, `null_meaning` | what it is, and when it is null (UNKNOWN) |
| `kind` | `expression` (default) or `label` (a status / tier / class: needs `categories`) |
| `valid_range` | `[min, max]` (`inf` / `-inf` open): a sanity flag, values are never clipped |
| `categories` | a label's closed set; a string the formula can produce must be in it |
| `params` | named constants the formula uses by name (`{ within = 0.10 }`); unused ones fail |
| `materialise` | `true`: stored as `rollups/instrument/<name>@v<version>` by the `rollups` task (needed when a group reads it, e.g. `div_yield` for `iv30@v1`); default `false`: computed on read |
| `version` | the definition's version (default 1): bump it when the formula changes |

**Language.** Literals: numbers (`10`, `0.25`, `1e6`, `100_000`), strings (`"HIGH"`),
`true`, `false`, `null`. Names: `group.column` is a stored feature of the registered group
version (`price_stats.hv30` is `price_stats@v2`'s), a bare name is another expression
feature or one of the feature's `params`. Operators, lowest precedence first: `or`, `and`,
`not`, comparisons `< <= > >= == !=` (one per term), `+ -`, `* /`, unary `-`. Functions:
`if(cond, a, b)`, `abs`, `sqrt`, `log` (natural), `min(a, b, ...)`, `max(a, b, ...)` (numbers
or strings), `clip(x, lo, hi)`, `coalesce(a, b, ...)`, `is_null(x)`, `one_of(x, "A", "B")`,
`exists(group)`. Types are checked at load: arithmetic takes numbers, `and` / `or` / `not` and
`if` conditions take bools, `==` compares like with like (never `null`: use `is_null`), and a
string compared with a label must be one of its categories.

**Nulls.** Null is UNKNOWN and propagates: `null + 1`, `null > 1` and `f(null)` are null;
`and` / `or` are three-valued (`false and null` is false, `true or null` is true);
`if(null, a, b)` is null; division by zero, `log` of a value <= 0, `sqrt` of a negative and
non-finite results are null. `exists(option_liquidity)` is true when the instrument has a row
in the group for the session, false when the group has rows that session but not for it,
null when the group has none at all (not computed: unknown, not "absent").

**Errors** name the file, the feature and the position, e.g.
`config/site/features/price.toml [near_52w] expr, line 2 col 4: unknown name 'pct_from_hi'`.
A cycle between expression features names its path. Formulas are parsed by our own code;
nothing is ever passed to Python `eval`.

**Reading them.** Selections use `feature.<name>`; screeners get them in `FeatureView`
(`services.views.feature_view(..., expressions=[...])`); a series over a date range is
`services.features.read_expressions(reader, names, start, end)`. Only the stored columns a
formula needs are read.

### User features

A user declares their own expression features in `config/users/<user_id>/features/<theme>.toml`
(ADR 0023 step 4), with the same keys and language as the site's, typed by the same loader
(unknown keys, missing keys and secret-looking keys fail with the file and feature). Example
(`config/users/alice/features/momentum.toml`):

```toml
[drawdown_pct]
expr = "pct_from_high_52w * 100"   # a site feature
dtype = "float"
unit = "pct_points"
description = "How far the close is below its 52-week high, in percent"
null_meaning = "pct_from_high_52w is null"

[quiet_uptrend]
expr = "price_stats.close > price_stats.sma_200 and price_stats.hv20 < max_vol and drawdown_pct > -10"
params = { max_vol = 0.25 }
dtype = "bool"
unit = "flag"
description = "Above the 200-day average, calm, within 10% of the high"
null_meaning = "any input is null"
```

- **Always virtual**: `materialise` is not allowed (computed on read; ask for a site feature
  when it must be stored or read by a group).
- **Names**: selectable as `feature.<name>` by that user only: their selections, strategy and
  screener configs, the Explore ticker table / compare columns and `GET /features` (listed
  with `scope = "user"` and `owner`). Another user never sees them (an unknown field there).
  A user feature may read stored features (`group.column`), site expression features and the
  user's own; it may **not** take a site feature's name (the error names both definitions), so
  `feature.<name>` means the same thing for everyone who sees it. A site feature never reads a
  user feature, so a cycle can only run through the user's own features (its path is named).
- **Hash**: a resolved config records the definitions of the user features its selection
  reads (and the user features those read) in its hash (`features` in `config show`), so
  editing one re-runs the config; adding or editing a feature it does not read changes
  nothing. Site features are versioned instead (bump `version` with the formula).
- **Check them**: `algotrade-backtest [--user U] config validate-features` loads and type
  checks every user feature, then prints each one's type, inputs and a sample evaluation on
  the latest session its inputs have:

```text
alice: 2 user feature(s), all valid

feature.drawdown_pct  expression float  (config/users/alice/features/momentum.toml [drawdown_pct])
  inputs: pct_from_high_52w@v1
  2026-10-02: 9840/10215 instruments with a value; e.g. EQ:BBG000B9XRY4=-3.1, ...
```

## Vendor pacing

One limiter per vendor key (`libs/sources/algotrade_sources/framework/limiter.py`), shared by every
thread and process through its lock file under `[http] limits_dir`. Each section of
`sources.toml` sets its bounds; `[http]` sets how every limiter adapts:

| Key | Where | Default | Meaning |
|---|---|---|---|
| `min_interval_s` | vendor section | the registry's default for the source | floor: the fastest the vendor is ever asked (Cboe 1.05, Massive 12.5, SEC 0.2, Nasdaq earnings 0.5, Treasury 1.0) |
| `max_interval_s` | vendor section | 4 × the floor | ceiling the back-off stops at (Cboe 5.0) |
| `start_interval_s` | vendor section | the floor | where each run starts |
| `backoff_factor` | `[http]` | 1.5 | a 429 (after holding every process for its `Retry-After`), or too many errors: interval × this |
| `max_error_rate`, `error_window` | `[http]` | 0.10, 50 | when the last `error_window` responses hold more than this share of errors (429, 5xx, a non-missing 403, timeouts and connection errors; **not** "no such object" answers such as a 404 or Cboe's S3 `AccessDenied`), slow down once and start a new window |
| `speedup_after`, `speedup_factor` | `[http]` | 100, 1.05 | after this many responses in a row without an error, interval ÷ this, never below the floor |

A burst of 429s from several workers backs off once (only a 429 arriving outside a running
hold multiplies the interval). The adaptive state lives in the lock file; a key unused for 10
minutes (`IDLE_RESET_S`) starts again from `start_interval_s`, so in practice **each run starts
fresh** and concurrent processes share what the vendor told either of them.

### Pacing stats

Every ingest run records, under `stats.pacing.<limiter key>` (only keys that sent requests
during the run; counts are this process's):

| Key | Meaning |
|---|---|
| `requests` | requests that went through the limiter (each retry counts) |
| `errors` | responses counted as errors (429s included; "no such object" never) |
| `throttled_429` | HTTP 429 responses |
| `backoffs_429` | of those, the ones that multiplied the interval (one per burst) |
| `retry_after_wait_s` | seconds of `Retry-After` holds added |
| `limiter_wait_s` | total seconds requests waited on the limiter (pacing + holds) |
| `error_rate_slowdowns` | slowdowns from the error-rate window |
| `speedups` | speed-ups after clean streaks |
| `interval_start_s`, `interval_final_s`, `interval_min_s`, `interval_max_s` | the interval at the run's first and last request, and its range |

The `chains` run also records `order_tiers` (`priority`, `liquidity`, `rest`: how many
underlyings fell in each fetch-order tier). The nightly email lists each step's limiters under "Run timing" → "Vendor pacing" (requests, 429s, Retry-After and total rate-limit wait, slowdowns, interval range).

## Environment

`src/algotrade/config/env.py` is the only code that reads environment variables. Entry points
call `load_dotenv()` once (a local `.env`, never overriding what is already set).

| Variable | Read by | Default |
|---|---|---|
| `ALGOTRADE_DATA_URL` | `data_url()`, passed to `storage.factory.open_backend(url)`; `--data-url` wins | `file://./var/data` |
| `ALGOTRADE_CONFIG_DIR` | `config_dir()`, passed to `open_config_store(dir)`; `--config-dir` wins | `./config` |
| `ALGOTRADE_USER` | `user_id()`, the default `--user` | `local` (`site` for site screens) |
| `ALGOTRADE_MASSIVE_API_KEY`, `ALGOTRADE_SEC_CONTACT` | `credential()`, handed to the source registry | unset: the source is skipped with the reason |
| `ALGOTRADE_IBKR_HOST`, `ALGOTRADE_IBKR_PORT`, `ALGOTRADE_IBKR_CLIENT_ID` | `credential()`, handed to the source registry for the IB Gateway session (`verify`, read-only); port 4001 live gateway, 4002 paper | unset: the `ibkr` source is skipped with the reason |
| `ALGOTRADE_NOTIFY_EMAIL_TO`, `ALGOTRADE_NOTIFY_EMAIL_FROM`, `ALGOTRADE_SMTP_USER`, `ALGOTRADE_SMTP_PASSWORD` | `credential()`, read by the nightly email notifier (`workflows/nightly/notify.py`) when `[notify.email] enabled`; recipients comma-separated, FROM defaults to the first recipient; Gmail needs an app password | unset with email enabled: a `notify` WARN "email not configured", the nightly carries on |

## Users

Phase 0 identity is a **label for namespacing, not authentication**: `--user` on both CLIs,
defaulting to `$ALGOTRADE_USER`, else `local` (`site` for runs scheduled from site presets). Market data and rollups are
global; configs, results and jobs are per user. Phase 4 maps authenticated users to
`user_id`, and services enforce that users only read and write their own configs, results
and jobs.

Rules: configs never contain secrets. Keys that look like credentials (`api_key`, `token`,
`password`, `secret`, …) anywhere in a config or in run overrides are rejected at load;
credentials come only from environment variables. Ids
are restricted to `[a-z0-9_-]`, so they are safe in paths.

## Running configs

```bash
algotrade-backtest [--user U] config validate|show <id>
algotrade-backtest [--user U] config validate-features    # the user's expression features
algotrade-backtest [--user U] backtest --config <id> --start 2024-01-02 --end 2025-12-31
algotrade-ingest   screen --config <id> --user U [--date D] [--export-dir out/]
algotrade-ingest   nightly        # every config with schedule = "nightly": site presets + each user's
```

All of these run as **jobs** (see [architecture.md](architecture.md#jobs)).

## Planned (see the [roadmap](roadmap.md))

| Item | Status |
|---|---|
| L4 `watchlists/` and `preferences.toml` | phase 4–5 |
| Database-backed `ConfigStore` written by the UI | phase 4 |
