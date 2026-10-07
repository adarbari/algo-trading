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
  presets/screeners/<id>/v<N>.toml  rule-screen preset versions: immutable, hash-locked (ADR 0029)
config/users/<user_id>/             L4: git-ignored locally; a DB behind ConfigStore later
  selections/<id>.toml
  strategies/<id>.toml
  features/<theme>.toml             the user's expression features (always virtual)
  screeners/<id>/draft.toml         a rule screen's working copy (never run)
  screeners/<id>/v<N>.toml          finalised versions: immutable; the latest (max N) runs nightly
  archive/screeners/<id>-<stamp>/   a deleted screen's folder, moved whole (never run or listed)
```

The location comes from `ALGOTRADE_CONFIG_DIR` (default `./config`) or `--config-dir`. Only
`storage/configs/files.py` knows this layout; everything else uses the `ConfigStore`
protocol (`load(scope, kind, name)`, `names`, `users`, and a user's rule-screen drafts and
versions: `draft`, `drafts`, `versions`, `version`, which the read model reads). A config id is found under the kind
`strategies` or `screeners` (both is an error). `screeners` are versioned:
`load(scope, "screeners", "<id>")` is the latest version, `"<id>@<N>"` exactly version N. User configs are **written** only by
`services/authoring` through `ConfigWriter` (`storage/configs/writer.py`; atomic files, a
version is never overwritten), which the API calls (ADR 0029): save / discard a draft,
delete a screen (archived, never erased),
finalise it (validated fail closed), copy a preset, rebase, save a user feature. Finalising puts a screen on the nightly (ADR 0033).

## Objects (`src/algotrade/config/`, pure, no I/O)

```text
Rule           { field, op: eq|ne|in|not_in|gt|gte|lt|lte|between|is_null|not_null, value }
Group          { all: [Rule|Group] } | { any: [Rule|Group] } | { not: Rule|Group }
Selection      { name, where: Group, max_instruments?, order_by? }   # top-N by a field
StrategyConfig { id, name? (display name; the id when absent; not hashed), kind: screener|strategy, impl, params, selection (preset name or inline),
                 selection_overrides?, schedule?: nightly, exports?: [...],
                 screening?: {...}, backtest?: {...}, extends? (user configs),
                 rule screens (impl = "rules"): version?, criteria, flags?,
                 columns?, rank? }
ScreenSpec     { criteria (HARD / SOFT + tolerance / SCORE), flags, columns, rank }  # rules.md
ResolvedConfig { config, selection, settings, user, layers, hash }
UserContext    { user_id }   # a validated label: [a-z0-9_-]{1,64}
```

`Rule` / `Group` and their three-valued evaluation live in `core/model/predicates.py` (shared
by selections and [rule screens](screeners/rules.md)); `ScreenSpec` in `core/model/screen_spec.py`,
parsed by `config/strategy/screen_spec.py`. Parsing errors name the exact path, e.g. `users/alice/strategies/x.selection.where.all[2]: op
must be one of [...]`. A bad config never runs (fail closed).

## Resolution

```
built-in defaults  <  L3 site (defaults.toml + preset)  <  L4 user config  <  run-time overrides
```

- **Find the document.** A user config with the same id overrides the site preset of that id;
  `extends = "<preset id>"` builds a new id on top of a preset; a user-only config needs no
  preset. `extends = "<preset id>@<N>"` pins version N of a rule-screen preset; it keeps
  resolving when the site adds newer versions (rebasing is optional, results never change
  silently). The `site` user (scheduled site presets) never reads user documents.
- **Merge.** Tables merge deeply; lists are replaced.
- **Selection.** A preset name resolves user-first, then site. A user either **narrows** the
  preset with `selection_overrides` (AND-ed with the preset's rules, so later preset fixes
  still apply) or **replaces** it with its own `selection`. A user can never widen coverage:
  covering a new instrument is a site change.
- **Settings.** `[screening]`, `[backtest]` and `[regime]` come from defaults, overridden by
  the config, and are typed at resolve time (`ResolvedConfig.screening`, `.backtest`,
  `.regime`, [below](#regime); see
  [site settings](#site-settings-typed-one-loader)): an unknown key or a bad value fails
  with its path, e.g. `sma_trend [backtest.costs]: unknown keys ['fee']`.
- **Hash.** SHA-256 of everything that affects results (impl, params, selection, exports,
  settings), not of provenance and not of the schedule (when a config runs never changes what
  it computes). Every result row and run record carries `user_id`,
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
| `financials@v1` | `revenue_ttm`, `revenue_ttm_year_ago`, `net_income_ttm`, `revenue_fy` (float); `eps_diluted_ttm` (float32); `revenue_fy_end`, `ttm_as_of`, `ttm_filed` (date); `eps_stale`, `is_adr` (bool); `ttm_basis`, `financials_status` (str) |
| `put_wing@v1` | `wing_status` (str); `target_expiry` (date); `target_dte`, `n_unpriced`, `n_strikes`, `wing_oi`, `wing_volume`, `best_put_oi`, `best_put_volume` (int); `wing_spread_pct`, `delta_band_distance`, `best_put_strike`, `best_put_delta`, `best_put_iv`, `best_put_mid`, `best_put_spread_pct`, `best_put_roc` (float32) |
| `price_moves@v1` | `one_day_move` (float32) |
| `momentum@v1` | `atr_14`, `rsi_14`, `ret_5d`, `rel_volume`, `high_20d`, `low_20d`, `high_50d`, `low_50d`, `prior_high_20d` (float32) |
| `volume@v1` | `session_volume`, `dollar_volume`, `adv_shares_20d`, `volume_ratio_5d_20d`, `volume_z_20d`, `up_volume_share_20d`, `cmf_20d` (float32) |
| `swing_levels@v1` | `swing_high`, `swing_low` (float32); `swing_high_date`, `swing_low_date` (date) |
| `pivot_strength@v1` | `resistance_touches`, `support_touches`, `resistance_age`, `support_age` (int); `pivot_structure` (str) |
| `retest@v1` | `breakout_date` (date); `breakout_level` (float32); `sessions_since_breakout`, `failed_breakouts_252d` (int); `retest_state` (str) |
| `gaps@v1` | `gap_open_pct`, `gap_above`, `gap_below` (float32); `gap_above_date`, `gap_below_date` (date) |
| `bands@v1` | `ema_10`, `ema_20`, `ema_50`, `ema_200`, `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d`, `close_std_20`, `bb_width_pctile_252d` (float32); `band_walk` (int, signed) |
| `trend_stats@v1` | `ret_1d`, `ret_3d`, `ret_10d`, `ret_120d`, `ret_252d`, `mom_12_1`, `mom_accel_5d`, `ret_z_20d`, `high_100d`, `low_100d`, `high_200d`, `low_200d`, `prior_high_50d`, `prior_low_20d`, `prior_low_50d`, `close_range_pos` (float32); `sessions_since_high_20d`, `close_streak`, `sma20_streak`, `tight_range_sessions` (int) |
| `anchored_vwap@v1` | `avwap_earnings` (float32); `avwap_anchor_date` (date) |
| `oi_walls@v1` | `wall_status` (str); `call_wall`, `put_wall` (float32); `call_wall_oi`, `put_wall_oi` (int) |
| `nearest_expiry@v1` | `expiry_date` (date); `dte`, `sessions_to_expiry` (int) |

Expression features (`feature.<name>`): `liquidity_class` (str: HIGH / MEDIUM / LOW /
UNKNOWN), `option_tier` (str: A-D), `option_chain_known`, `liquidity_high`,
`liquidity_medium` (bool), `option_chain_oi`, `option_chain_volume` (int), `div_yield`
(float32, materialised), `market_cap`, `pe_ratio`, `revenue_growth_yoy`, `pct_from_high_52w`, `pct_from_low_52w`,
`iv_hv_spread`, `iv_hv_ratio`, `atr_pct`, `range_20d_pct`, `dist_to_resistance`,
`dist_to_support`, `dist_to_resistance_atr`, `dist_to_support_atr` (float), `breakout_20d`,
`pullback_to_sma20`, `earnings_before_expiry` (bool), `near_52w` (str: HIGH / LOW / BOTH /
NONE), `trend_state` (str: UPTREND / DOWNTREND / MIXED).

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

## Regime

`[regime]` (ADR 0049; typed `RegimeSettings` in `config/strategy/regime.py`) sizes backtests
and gates screeners by the session's market regime. It layers like `[screening]` and
`[backtest]`: built-in < `config/site/defaults.toml` < the site preset < the user's config
(`config/users/<id>/strategies/<id>.toml` or `screeners/`) < run overrides, tables merging, so
the config hash records it.

```toml
[regime]
enabled = false                    # off until the site, a user or a run turns it on
label = "market.regime@v3.label"   # a market feature field: CALM, CAUTION, STRESS, CRISIS
unknown_multiplier = 0.0           # size when the label is null or unknown (fail closed)
pause_in = []                      # labels in which a screener's picks are PAUSED
[regime.multipliers]               # size per label, each in [0, 1]
CALM = 1.0
CAUTION = 0.75
STRESS = 0.5
CRISIS = 0.25
[regime.screeners.vrp_scanner]     # per screener (config id): replaces pause_in
pause_in = ["STRESS", "CRISIS"]
```

- **Backtests.** Enabled, the run reads the label for every session of its bars (a session
  with no row is unknown; no row in the whole range is a `MissingDataError`) and the engine's
  `ScaleByLabel` overlay multiplies the strategy's weights by the session's multiplier (0 in a
  `pause_in` label, `unknown_multiplier` when unknown) before the risk limits; the run record's
  `overlay_reasons` counts the bars per reason.
- **Screeners.** Enabled, a QUALIFIED / WATCH row is `PAUSED` when the session's label is in
  the screener's `pause_in` (its `[regime.screeners.<id>]` table, else that of the site preset it
  extends, so a user's copy of the VRP scanner keeps its pause, else the top-level list), and
  in every gated screener (a non-empty `pause_in`) when the label is unknown; result rows
  carry `regime` and `size_multiplier` ([screeners](screeners/README.md#contract-all-screeners)).
- **Validation.** Unknown keys, a multiplier outside [0, 1], a label outside the four, or a
  `label` that is not a `market.<group>@v<N>.<column>` field fail at resolve with the path,
  e.g. `vrp_scanner [regime] pause_in: unknown labels ['STORM']`.
- **Evaluation.** `make evaluate` also runs every strategy on every golden dataset without and
  with the site's overlay (whether or not it is enabled) and prints max drawdown, Sharpe and
  exposure for both, or `regime overlay: no market feature rows in the store`.

## Site settings (typed, one loader)

Every `config/site/*.toml` is loaded and validated by `src/algotrade/config/site/settings.py`
alone (ADR 0019 `site-settings`); apps receive frozen dataclasses, never dicts:

| File | Type | Holds |
|---|---|---|
| `defaults.toml` | `ScreeningSettings`, `BacktestSettings` (`CostSettings`, `LimitSettings`), `RegimeSettings` ([regime](#regime)) | run defaults, layered per config |
| `sources.toml` | `SourcesSettings` (`VendorSettings` per section) | per-vendor `enabled` and pacing (`min_interval_s`, `max_interval_s`, `start_interval_s`; see [Vendor pacing](#vendor-pacing)), chain workers and `[cboe] priority_symbols`, earnings days, corporate-actions window, SEC refresh days (`[sec_edgar] refresh_days` company details, `facts_refresh_days` share counts; spread over the window by CIK), ETF holdings (`[etf_holdings] refresh_days` 7: each fund once per window on its slot day, N-PORT funds at most every 90 days; `per_night` 200: funds the nightly reads a night from one list across issuers, 0 no cap (the CLI is uncapped); `keep_top` 100: holdings stored per fund, 0 all; `fallback_scope` `liquid` (default) / `optionable` / `all` / `off`: which funds SEC N-PORT is read for (`liquid`: the optionable ones plus those with `fallback_min_adv_usd` 5,000,000 of 20-session dollar volume); `[spy_holdings]`, the older name of `[ssga]`, still switches State Street off; `[ssga]`, `[ishares]` and `[proshares]` hold the issuers' `enabled`, pacing and `raw_retention_days` 14; `[ssga] etf_files` false turns off only the SPDR fund files; `[etf_holdings]` takes only `enabled` and its own keys, no pacing or retention); `[sec_edgar] fund_quarters` (6: prospectus data sets read for ETF descriptions, ADR 0034), `[massive] descriptions_per_night` (100: stocks the nightly asks Massive for; 0 turns the nightly requests off, hand runs still work) and `descriptions_refresh_days` (365); `[http]` retry cap, circuit breaker, limiter directory and adaptive-pacing rules; raw and staging retention, `live_retention_days` (7: `live/option_quotes` partitions older than this are purged by `purge-raw`) (a vendor section's `raw_retention_days` overrides the global raw window for every raw source in that section: `[sec_edgar]` keeps 7 days; see [storage.md](data/storage.md#retention)); `[quality]` thresholds of the nightly steps' acceptance checks (ADR 0039: outside them the step FAILS and holds back what needs it): `max_bar_count_drop` (0.10), `max_bar_unresolved` (0.01: share of the session's bars whose ticker the resolver did not know), `max_universe_change` (0.05), `max_name_over_vendor` (0.02: share of ACTIVE reference rows typed by the name over a generic vendor type) and `max_type_disagreement` (0.10: share whose vendor type our name rules contradict), the `reference_classification` check (ADR 0045); `macro.toml [macro] run_budget_s` (900: the `macro` task stops fetching after that many seconds and records the rest as skipped, so a FRED outage cannot hold the nightly up); `max_macro_stale_share` (0.20: the `macro_fresh` check FAILs above that share of the enabled macro series with no observation newer than cadence + `release_lag_days` + 2 days (3 for a daily series), ADR 0048; the `macro_vintages` check FAILs when a series holds fewer vintages than an earlier run recorded); `min_calendar_future_dates` (1: the `macro_calendar_future` check of the `macro-calendar` step FAILs when a FRED release of `config/site/events/releases.toml` lists fewer scheduled dates after the session, ADR 0050); `max_filings_failed` (0.05: the `filings_fetched` check of the `filings` step FAILs when over that share of the scoped CIKs' SEC requests failed, ADR 0050); option chains: `max_chain_fetch_failures` = share of optionable names whose fetch failed (`FETCH_ERROR`, including an open circuit, or `NOT_ATTEMPTED`) above which `chains_fetch` FAILs, default 0.02; `max_chain_stale_share` = share of the "rest" tier's `STALE_DATA` chains above which `chains_stale_rest` FAILs, default 0.20, and `max_chain_stale_share_core` the same for the "core" tier (S&P 500, `[cboe] priority_symbols`, HIGH liquidity; `chains/status.tier`, recorded at fetch time) with `chains_stale_core`, default 0.02; the details list the OK / STALE_DATA / NO_CHAIN / NO_STANDARD_SERIES counts. `min_chain_coverage` was replaced by these two and is now rejected); `[quality.coverage.<group>.<column>]` (ADR 0043: `core_min`, `rest_min`, `max_drop`, `level`, `core_level`, `covered_by` `value` / `row` / `recent`; `recent` takes `max_age_days`, 100, and `or_value`) grade per tier the share of the names a feature applies to that have a value: the `coverage_<feature>` checks of the `rollups` step; `earnings.last_earnings_date` (`recent`) flags overdue earnings, core companies whose last report is over 100 days old with no next date |
| `sources.toml [ibkr]` | `IbkrSettings` (`SourcesSettings.ibkr`) | IB Gateway for the read-only `verify`, `ibkr-contracts` and `ibkr-iv` tasks (ADR 0026, 0028): `enabled` (off by default: a missing section is disabled too), `min_interval_s` (every message, 0.02 = 50/s), `historical_min_interval_s` (>= 0, default 10: the shared `ibkr_historical` limiter, one historical request per 10 s = 60 per 10 minutes. IBKR documents that 60-per-10-minutes rule only for bars of 30 s or less; daily bars, which every IBKR task asks for, are soft throttled. The default stays 10; the owner may trial 5, then 3, watching the `ibkr_historical` pacing stats, request timeouts and error 162 (pacing violation): an unanswered request is retried and then left pending, never recorded as `NO_DATA`), `market_data_type` (1 live, 3 delayed), `connect_timeout_s`, `request_timeout_s`, `stream_wait_s` (IB dividends tick; the IV ticks too), `raw_retention_days` (30); the IBKR enrichment (ADR 0028, tasks `ibkr-contracts`, `ibkr-iv`): `contracts_refresh_days` (30: each conid again once a month, on a slot day by key), `contracts_batch` (25 per `qualifyContracts`), `iv_batch` (50 IV streams open together), `iv_history_days` (730: the history a nightly backfill fetches), `iv_backfill_per_night` (100 underlyings without history the nightly backfills, one IV request each; 0 off); `[quality] max_verify_failures` (0.10): the `verification` check FAILs above that share of failing graded checks and WARNs on any |
| `verification.toml` | `VerificationSettings` | the live verification vs IBKR: `[sample]` `core_symbols` (always verified), `rotating` (more per session, by a hash of the session), `option_symbols` + `options_per_symbol` (option quotes compared with our chain), `bar_sessions` (IBKR daily bars per name); `[tolerances]` `close_rel`, `range_rel`, `hv_rel`, `high_52w_rel`, `extreme_rel` (52-week low, the dividend-gap rule), `yield_abs`, `iv_abs`, `spread_band` (option mids, in half-spreads), `max_missing_sessions`, `warn_multiple` (over tolerance by at most this factor: WARN; beyond: FAIL). Defaults are the reconciliation suite's tolerances (testing.md) |
| `llm.toml` | `LlmSettings` | the text model behind natural-language screener drafts (ADR 0041; [rules.md](screeners/rules.md#drafting-from-a-sentence-adr-0041)): `enabled` (off as shipped), `base_url` (an OpenAI-compatible root; plain `http` only for this machine), `model`, `timeout_s`, `answer_limit` (tokens for the answer and a thinking model's thinking), `retries`; an optional `[request]` table of extra fields sent with every request as given (strings, numbers, booleans; never `model`, `messages`, `temperature`, `max_tokens` or `response_format`), e.g. `reasoning_effort = "low"` so Gemini 3.x thinks briefly. The key only from `ALGOTRADE_LLM_API_KEY`. A file that does not load does not stop the API: drafting is off, the error is logged and is the reason the drafting route answers 503 with; `make doctor` reports it |
| `universe.toml` (+ `overrides/leveraged_etfs.csv`, `overrides/figi.csv`) | `UniverseSettings` | coverage mode (`nasdaq_trader` / `csv_import`), security types, include / exclude symbols, leverage rules (markers, conventions, patterns, inverse markers, exclusions; regexes are compiled and `leverage_patterns` need a `(?P<n>...)` group); `figi_overrides` from `figi.csv` (columns `symbol`, `figi`, `note`; a composite FIGI or blank for "no FIGI, symbol id"; a malformed FIGI, an unknown column, or a symbol or FIGI listed twice fails with its line; see [instruments.md](data/instruments.md#figi-based-instrument-ids-implemented-phase-18)) |
| `nightly.toml` | `NightlySettings` | `[sessions]` settle margin and catch-up cap, `[alerts]` nightly duration, `[notify]` notifications on/off, the desktop notification and the summary file path; `[notify.email]` the daily summary email (`enabled`, `smtp_host`, `smtp_port`, `max_examples`) |
| `rollups.toml` | each rollup's own params dataclass (`rollup_params` / `load_rollups`) | one `["<name>@v<N>"]` section per rollup that takes parameters; each scalar field of its params dataclass (bool, int, float, str) is a key typed by its default, and the dataclass validates ranges (`price_stats@v2`: `year_sessions`, `min_year_sessions`, `periods_per_year`; `option_liquidity@v1`: DTE window, delta bands; `dividends@v2`: `min_history_days`, `include_special`; `iv30@v1`: `target_days`, `min_days`, `max_days`, `max_spread_pct`, `min_open_interest`, `min_volume`; `iv_history@v2`: `window`, `min_provisional`, `source` (`ours` / `cboe`); `fundamentals@v2`: `stale_days`; `financials@v1`: `stale_days`, `history_days`; `put_wing@v1`: `dte_target`, `dte_min`, `dte_max`, `delta_lo`, `delta_hi`, `search_lo`, `search_hi`, `prefer_monthly`; `pivot_strength@v1`: `touch_atr`; `retest@v1`: `search_sessions`, `retest_atr`, `fail_sessions`). A rollup without parameters has no section (a fitness test checks both ways) |
| `features/<theme>.toml` | `FeatureDefinition` per `[name]` (`feature_definitions` / `load_features`) | the site's expression features ([below](#expression-features)); the formula, dtype, unit and categories are then checked against the feature catalogue (`features/expressions/definitions.py`) |

A missing file or key falls back to the dataclass default. Anything else is an error that
names the file, section and key: unknown keys (a typo is never silently ignored), wrong
types (`enabled = "yes"`), out-of-range values (`workers = 0`, a fraction above 1, a
negative interval) and invalid leverage-marker regexes. Every key must also drive code
(`tests/architecture/test_ownership.py`). Credentials never go in these files.

## Expression features

A formula over existing features is a TOML entry, not code (ADR 0023 step 3). Each
`config/site/features/<theme>.toml` (one per theme: `price`, `volatility`, `fundamentals`,
`liquidity`, `vrp`, `swing`, `bands`) holds one `[name]` per feature:

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
`if(cond, a, b)`, `abs`, `sqrt`, `log` (natural), `ncdf` (the standard normal CDF, for a
probit: `ncdf(b0 + b1 * x)`), `min(a, b, ...)`, `max(a, b, ...)` (numbers
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
  screener configs, the Explore ticker table / compare columns and the GraphQL `catalogue` (listed
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


## Field guide

How to read each catalogue field, which criterion means what, and when the reading lies:
`config/site/field_guide/<theme>.toml` (`momentum`, `liquidity`, `volatility`, `events`,
`fundamentals`) plus `situations.toml` (ADR 0041, amended). Each `[[field]]` names a catalogue
field, its `theme`, `reads` (what the number means), `caveats` (each ending with the field to
check), `sources`, and `[[field.use]]` entries: an intent (`for`) with the criterion as a rule
screen takes it (`op`, `value`, `mode`, `tolerance`, `on_miss`, `note`). A `[[situation]]`
(`name`, `signs`, `affects`, `do`) is one state of the world that fools several thresholds. The
loader checks shape and vocabulary; `tests/architecture/test_features.py` checks that every name
is a catalogue field and every value fits its type, categories and range. `make features-doc`
renders [data/field-guide.md](data/field-guide.md); the drafting prompt and the Builder read
the same files.

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
| `ALGOTRADE_AUTH` | `auth_mode()`: how the API resolves its caller (ADR 0040): `supabase` verifies a Supabase access token on every request (401 without a valid one, 403 when its email maps to no registry user); `off` serves `ALGOTRADE_USER` without a token and the API refuses to start that way on a non-loopback `--host` | `supabase` |
| `ALGOTRADE_CORS_ORIGINS` | `cors_origins()`: the web origins the API allows (CORS), comma-separated, e.g. `https://app.example.com`; replaces the list, so include the local dev server too if it is still wanted | `http://localhost:5173`, `http://127.0.0.1:5173`, `http://localhost:3000`, `http://127.0.0.1:3000` |
| `ALGOTRADE_WEB_DIST` | `web_dist()`: the built web app the API serves on its own origin (ADR 0044, [hosting.md](hosting.md)): `make web-build` writes `var/web`; relative paths are from the working directory (the checkout, for the launchd agent); a directory without `index.html` stops the API at startup | unset: the API serves no files |
| `SUPABASE_URL` | `supabase_url()`: the Supabase project (`https://<ref>.supabase.co`); the API fetches its JWKS once at startup (refetched on an unknown `kid`) and checks the token's issuer against it | unset with `ALGOTRADE_AUTH=supabase`: the API refuses to start |
| `SUPABASE_JWT_SECRET` | `supabase_jwt_secret()`: the project's legacy HS256 signing secret, for projects not yet on asymmetric keys | unset: only JWKS-signed (ES256 / RS256) tokens are accepted |
| `ALGOTRADE_MASSIVE_API_KEY`, `ALGOTRADE_SEC_CONTACT` | `credential()`, handed to the source registry | unset: the source is skipped with the reason |
| `ALGOTRADE_IBKR_HOST`, `ALGOTRADE_IBKR_PORT`, `ALGOTRADE_IBKR_CLIENT_ID` | `credential()`, handed to the source registry for the IB Gateway session (`verify`, read-only); port 4001 live gateway, 4002 paper | unset: the `ibkr` source is skipped with the reason |
| `ALGOTRADE_IBKR_API_CLIENT_ID` | `api_credential()`: the client id of the API's live option quotes (ADR 0028) | `ALGOTRADE_IBKR_CLIENT_ID` + 1 |
| `ALGOTRADE_NOTIFY_EMAIL_TO`, `ALGOTRADE_NOTIFY_EMAIL_FROM`, `ALGOTRADE_SMTP_USER`, `ALGOTRADE_SMTP_PASSWORD` | `credential()`, read by the nightly email notifier (`workflows/nightly/notify.py`) when `[notify.email] enabled`; recipients comma-separated, FROM defaults to the first recipient; Gmail needs an app password | unset with email enabled: a `notify` WARN "email not configured", the nightly carries on |

**The web app's build-time variables** (`apps/web`, read only in `src/shared/config/env.ts`; Vite reads them from `apps/web/.env.local`, git-ignored, not from the repo `.env`): `VITE_SUPABASE_URL` (the same project URL as `SUPABASE_URL`) and `VITE_SUPABASE_ANON_KEY` (Project Settings -> API -> the public `anon` key, which is safe in a browser) let the web sign users in. Unset (the API runs `ALGOTRADE_AUTH=off`), there is no session and no login page: the API's `viewer` answers and counts as signed in; trying to sign in then says the keys are missing. `VITE_API_BASE_URL` (default `/api`, which the Vite dev server proxies to the API) is the API's address; `make web-build` sets it empty, so the hosted build calls the API on its own origin (ADR 0044).

**Creating the Supabase project** (ADR 0040; the API maps a token to a user by its email, so
these settings are required, not optional):

- [ ] Authentication -> Sign In / Providers: **Allow new users to sign up** off (users are
  invited from Authentication -> Users -> Invite user, with the email in their `identity.toml`).
- [ ] Email provider: **Confirm email** on.
- [ ] **Allow anonymous sign-ins** off (the API refuses anonymous tokens with 403 anyway).
- [ ] Copy the project URL into `SUPABASE_URL` (and, for a project still on the legacy JWT
  secret, that secret into `SUPABASE_JWT_SECRET`), then set `ALGOTRADE_AUTH=supabase`.
- [ ] Put the same URL and the `anon` key in `apps/web/.env.local` as `VITE_SUPABASE_URL` and
  `VITE_SUPABASE_ANON_KEY` (the web signs in with them; add the web's origin to Authentication
  -> URL Configuration when it is hosted: [hosting.md](hosting.md)).
- [ ] After each user's first sign-in, pin their `subject` in `identity.toml` (below) from
  Authentication -> Users (the user's UID).

## Users

The users are declared in `config/site/users.toml` (id, role, name; ADR 0040). The email a
Supabase sign-in maps to is personal data, so it is not in that public file: each user's lives
in their git-ignored `config/users/<id>/identity.toml`:

```toml
email = "alice@example.com"   # the address the user signs in with (case ignored, unique)
subject = "7b1c1d2e-..."      # optional: the user's Supabase UID; then the token must be theirs
```

A user without the file cannot sign in to the API (403); `site` never has one. Without
`subject` the email alone identifies the user (safe under the project settings above); with
it, a token for another Supabase account carrying the same email is 403. Pin it from the
Supabase dashboard (Authentication -> Users, the UID column) after the user's first sign-in;
the API reads the file at startup, so restart it after a change. The CLIs ignore the file.

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
