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
| `rollup.<name>@v<N>.<column>` | `rollups/instrument/<name>@v<N>` (columns and types declared on the rollup, `features/registry.py`) | `rollup.option_liquidity@v1.put_tier`, `rollup.price_stats@v1.hv30`, `rollup.price_stats@v1.adv_usd_20d`, `rollup.earnings@v1.days_to_earnings`, `rollup.fundamentals@v1.market_cap` |

Selectable rollup fields today ([data/layers.md](data/layers.md#rollups-as-built) has the rules):

| Rollup | Fields (type) |
|---|---|
| `option_liquidity@v1` | `liq_status`, `put_tier`, `call_tier` (str); `short_put_ok`, `short_call_ok` (bool); `chain_oi`, `chain_volume`, `target_dte`, `expiries_within_60d` (int); `underlying_price`, `iv30`, spreads… (float); `target_expiry`, `chain_asof` (date) |
| `price_stats@v1` | `close`, `sma_20`, `sma_50`, `sma_200`, `ret_20d`, `ret_60d`, `high_52w`, `low_52w`, `pct_from_high_52w`, `pct_from_low_52w`, `hv20`, `hv30`, `hv20_yz`, `adv_usd_20d` (float); `history_days` (int) |
| `earnings@v1` | `next_earnings_date`, `last_earnings_date` (date); `earnings_time` (str: pre / post / unknown); `days_to_earnings` (int); `date_confirmed` (bool, null today) |
| `dividends@v1` | `div_ttm`, `div_yield` (float); `div_count_ttm` (int); `last_ex_date` (date) |
| `iv30@v1` | `iv30`, `iv30_cboe`, `atm_strike_near`, `spot`, `rate`, `div_yield` (float); `iv30_status` (str); `near_expiry`, `far_expiry` (date); `n_quotes_used` (int) |
| `iv_history@v1` | `iv30`, `iv_rank_252d`, `iv_percentile_252d`, `iv_hv_spread`, `iv_hv_ratio` (float); `history_days` (int); `rank_status` (str: UNKNOWN / PROVISIONAL / FULL) |
| `liquidity_class@v1` | `liquidity_class` (str: HIGH / MEDIUM / LOW / UNKNOWN), `option_tier`, `rule_hash` (str); `adv_usd_20d`, `close` (float); `chain_oi` (int) |

A rollup with no row for an instrument, or no partition for the session, is UNKNOWN: e.g.
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
| `sources.toml` | `SourcesSettings` (`VendorSettings` per section) | per-vendor `enabled` and `min_interval_s` pacing, chain workers, earnings days, corporate-actions window, SEC refresh days (`[sec_edgar] refresh_days` company details, `facts_refresh_days` share counts; spread over the window by CIK); `[http]` retry cap, circuit breaker and limiter directory; raw and staging retention; `[quality]` thresholds of the nightly data-quality checks |
| `universe.toml` (+ `overrides/leveraged_etfs.csv`) | `UniverseSettings` | coverage mode (`nasdaq_trader` / `csv_import`), security types, include / exclude symbols, leverage rules (markers, conventions, patterns, inverse markers, exclusions; regexes are compiled and `leverage_patterns` need a `(?P<n>...)` group) |
| `nightly.toml` | `NightlySettings` | `[sessions]` settle margin and catch-up cap, `[alerts]` nightly duration, `[notify]` desktop notification and the summary file path |
| `rollups.toml` | each rollup's own params dataclass (`rollup_params` / `load_rollups`) | one `["<name>@v<N>"]` section per rollup that takes parameters; each scalar field of its params dataclass (bool, int, float, str) is a key typed by its default, and the dataclass validates ranges (`price_stats@v1`: `year_sessions`, `min_year_sessions`, `periods_per_year`; `option_liquidity@v1`: DTE window, delta bands; `dividends@v1`: `min_history_days`, `include_special`; `iv30@v1`: `target_days`, `min_days`, `max_days`, `max_spread_pct`, `min_open_interest`, `min_volume`; `iv_history@v1`: `window`, `min_provisional`, `source` (`ours` / `cboe`); `liquidity_class@v1`: `high_` / `medium_` `min_adv_usd`, `min_price`, `option_tiers` (comma list, worse of put / call; `""` none), `min_chain_oi`, `min_chain_volume` (0 none)). A rollup without parameters has no section (a fitness test checks both ways) |

A missing file or key falls back to the dataclass default. Anything else is an error that
names the file, section and key: unknown keys (a typo is never silently ignored), wrong
types (`enabled = "yes"`), out-of-range values (`workers = 0`, a fraction above 1, a
negative interval) and invalid leverage-marker regexes. Every key must also drive code
(`tests/architecture/test_ownership.py`). Credentials never go in these files.

## Environment

`src/algotrade/config/env.py` is the only code that reads environment variables. Entry points
call `load_dotenv()` once (a local `.env`, never overriding what is already set).

| Variable | Read by | Default |
|---|---|---|
| `ALGOTRADE_DATA_URL` | `data_url()`, passed to `storage.factory.open_backend(url)`; `--data-url` wins | `file://./var/data` |
| `ALGOTRADE_CONFIG_DIR` | `config_dir()`, passed to `open_config_store(dir)`; `--config-dir` wins | `./config` |
| `ALGOTRADE_USER` | `user_id()`, the default `--user` | `local` (`site` for site screens) |
| `ALGOTRADE_MASSIVE_API_KEY`, `ALGOTRADE_SEC_CONTACT` | `credential()`, handed to the source registry | unset: the source is skipped with the reason |

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
