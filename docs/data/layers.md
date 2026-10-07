# Data layers

All data and configuration lives in **four layers**. Each layer has one definition, one owner,
one format and one way to read it. Decision record: [ADR 0016](../adr/0016-four-data-layers.md).
Physical storage (partitions, backends, contract tests) is in [storage.md](storage.md);
configuration (L3/L4) is in [../configuration.md](../configuration.md).

```
 ┌───────────────────────────────────────────────────────────────────────────────────────┐
 │ L4  USER CONFIG   config/users/<user_id>/*.toml       per user · selections, strategy   │
 │                   (ConfigStore; DB later)              configs, watchlists, preferences  │
 ├───────────────────────────────────────────────────────────────────────────────────────┤
 │ L3  SITE CONFIG   config/site/*.toml (+ overrides/*.csv)   shared · universe coverage,  │
 │                   reviewed via PR, versioned by git        sources, defaults, presets    │
 ╞═══════════════════════════════════════════════════════════════════════════════════════╡
 │ L1  INSTRUMENT    instruments/reference         what each instrument IS (sourced facts) │
 │                   rollups/instrument/<name>@vN   what we KNOW about it now (derived)     │
 │                   → read together as InstrumentView(as_of=D)                           │
 ├───────────────────────────────────────────────────────────────────────────────────────┤
 │ L2  INSTRUMENT ×  bars/<interval>       OHLCV at 1m · 5m · 1h · 1d                      │
 │     TIME          rates/treasury        Treasury par yield curve (risk-free rates)      │
 │                   chains/*              option-chain snapshots (instrument × contract)  │
 │                   events/<type>         earnings, splits, dividends, renames, index Δ   │
 │                   rollups/daily/<name>@vN   intraday → one row per instrument per day   │
 └───────────────────────────────────────────────────────────────────────────────────────┘
   L1 and L2 are market data: global, written only by apps/ingestion, Parquet, point-in-time.
   L3 and L4 are configuration: TOML, read by services, resolved into a hashed ResolvedConfig.
   Below the layers sits plumbing (raw vendor responses, run and job records); above them sit
   outputs (screen and backtest results, per user).
```

## L1: Instrument level (one row per instrument, as of a date)

Two physical parts, always read together:

| Part | Holds | Examples | Changes | Written by |
|---|---|---|---|---|
| `instruments/reference` | **sourced facts**: identity, company, classification, contract terms | ticker, FIGI, company name, website, description, sector/industry, country, exchange, security type, ETF flags (leveraged, inverse, leverage, tracks), optionable, multiplier, tick size, listing status, listed/delisted dates | rarely | universe and reference ingestion jobs |
| `rollups/instrument/<name>@vN` | **derived state** "as of D", computed from L2 | next earnings date + time + days to it, ADV (20d $), liquidity class ("highly liquid"), option liquidity tiers, market cap, 52-week high/low, HV20/30, IV30 and IV rank | nightly | the `rollups` task (market-entity groups, `rollups/market/<name>@vN` with one `MKT:US` row per session, by the non-critical `market-rollups` task, ADR 0047) |

- **Vendor contract ids**: `instruments/ibkr_contracts` (IBKR `conid`, primary exchange,
  `resolved_at`; one full snapshot per run, ADR 0028), read through
  `data.reference.ibkr_contracts` (on or before the date, never a later snapshot).
- **Format and history:** Parquet, **one full snapshot per date** (≈10k rows, < 1 MB/day).
  Reading "as of D" returns the latest snapshot on or before D, so a 2025 backtest sees 2025's
  company names, listings and delistings. Validity ranges (`valid_from`/`valid_to`) are
  *derived* from snapshots if ever needed; they are not stored.
- **Changes become events.** The nightly job diffs today's reference snapshot against the
  previous one and writes `events/reference_change` rows (renames, delistings, type changes).
- **Definitions live in site config.** A label such as "highly liquid" is a rollup whose
  thresholds come from `config/site/rollups.toml`, so the definition is explicit, versioned
  and auditable, never hard-coded.
- **Not in L1:** option and futures *contracts*. There are 1M+ option series; their terms
  (underlying, expiry, strike, right, standard/adjusted) live in the OSI symbol and on each
  chain row in L2. Futures get `instruments/futures_contracts` when they arrive (phase 6).
- **Stable id** ([ADR 0018](../adr/0018-figi-instrument-ids.md)). `instrument_id` is
  `EQ:<composite FIGI>` when the FIGI is known (it survives renames and ticker reuse:
  FB → META), else `EQ:<ticker>`. `instruments/symbol_history` maps ticker → id over time and
  `instruments/id_map` records symbol-id → FIGI-id upgrades. Tickers become ids only through
  `SymbolResolver` (`data.reference.resolver(reader, session)`).
- **InstrumentView** (`data.reference.instrument_view(reader, session, fields)`) returns
  reference facts (latest snapshot on or before the session, else the earliest, flagged
  `pre_snapshot`) joined with rollups **for** the session, one row
  per instrument, columns named by field. A rollup with no data for the session is listed in
  `missing`, and its fields are UNKNOWN to selections (never stale values).

## L2: Instrument × time (values)

| Table | Grain (one row is…) | Interval | Notes |
|---|---|---|---|
| `bars/<interval>` | instrument × bar start | `1d` (phase 1), `1h`/`5m`/`1m` later | OHLCV + VWAP, **unadjusted**; splits and dividends applied at read time from `events` |
| `chains/option_quotes`, `chains/underlying_quotes`, `chains/status` | contract (or underlying) × snapshot | end of day | built (Cboe); `chains/status` carries each underlying's `status` and `tier` (core / rest at fetch time, `tasks/market/tiers.py`) |
| `events/<type>` | instrument × event time | irregular | `earnings`, `split`, `dividend`, `reference_change`, `index_change` |
| `volatility/ibkr_iv30` | instrument × session | daily | IBKR's 30-day implied vol of the underlying's options and 30-day historical vol (`iv30_ibkr`, `hv30_ibkr`, `source_kind` history / snapshot; ADR 0028). Merge runs (a backfill writes many sessions, the nightly one; latest run wins per instrument). Personal-use licence. Read through `data.volatility.ibkr_iv30` |
| `live/option_quotes` | contract × time taken | on request | the live IBKR quotes the API served (`/chains/{id}/live`; ADR 0028): bid, ask, last, close, volume, IB's model `iv` and `delta`, `conid`, `market_data_type`. Merge runs (each a batch of snapshots; every snapshot kept, keyed by contract and `ts`); `session_date` is the session the quote was taken in. The API's one write, only through `LiveWriter`; never read by backtests. Personal-use licence. Read through `data.chains.live_option_quotes` |
| `rates/treasury` | curve date × tenor (`RATE:UST-<tenor>`) | daily (bond-market days) | U.S. Treasury par yield curve: `tenor`, `tenor_days`, `rate_par`, `rate_cont` (decimals; ADR 0021). One partition per curve date; read through `data.rates.curve(reader, on)` (latest on or before, earliest flagged) |
| `holdings/etf` | ETF × holding × issuer as-of date | weekly | what an ETF holds (ADR 0035): the largest `[etf_holdings] keep_top` (100) lines of the issuer's file ranked by the size of the weight (`weight` a fraction of the fund; `filed` hides an N-PORT row before its filing date), `holding_symbol` / `holding_name` / `asset_class` / `sector` / `shares` / `identifier` (CUSIP or ISIN), `holding_id` (the universe instrument the ticker resolves to, else null), `holdings_count` (every line of the file). Sources: State Street and iShares daily files, SEC N-PORT (quarterly) for the rest. Merge runs (a run reads a few funds); read through `data.funds.holdings.etf_holdings` |
| `rollups/daily/<name>@vN` | instrument × session | daily | rolls intraday bars up to a day: session OHLCV, VWAP, intraday range, opening gap |

**`bars/<interval>` columns.** Key (`instrument_id`, `ts`) within an interval table.

| Column | Type | Notes |
|---|---|---|
| `instrument_id` | str | `EQ:BBG000B9XRY4` (`EQ:AAPL` without a FIGI) |
| `ts` | timestamp UTC | bar start |
| `session_date` | date | exchange trading day |
| `open`, `high`, `low`, `close` | float64 | **unadjusted**; sanity-checked on write (positive, high ≥ open/close ≥ low) |
| `volume`, `vwap` | float64 | `vwap` nullable |
| `knowledge_ts`, `source`, `run_id` | | point-in-time lineage (every table) |

**Roll-up chain.** Each step is a versioned, pure definition (in `features/`), recomputed
nightly and stored point-in-time:

```
bars/1m ──► rollups/daily/session_stats@v1 ──┐
bars/1d ─────────────────────────────────────┼─► rollups/instrument/price_stats@v2   (52w hi/lo, MAs, HV, ADV), price_moves@v1, momentum@v1, swing_levels@v1,
                                                   volume@v1, anchored_vwap@v1 (+ events/earnings)
chains/* ────────────────────────────────────┼─► rollups/instrument/option_liquidity@v1, put_wing@v1, call_wing@v1, oi_walls@v1, nearest_expiry@v1, iv30@v1 ─► iv_history@v2 ─┐
volatility/ibkr_iv30 ────────────────────────┼─► rollups/instrument/ibkr_iv@v1 ─────────────────────────────────────────────────────────────────────────────────┴─► iv_rank (+ source)
events/earnings ─────────────────────────────┴─► rollups/instrument/earnings@v1     (next date, days to it)
```

- **Official daily bars win.** The vendor's `1d` bar (official close, including the closing
  auction) is the source of truth. A daily bar rolled up from `1m` bars is a cross-check,
  never a substitute.
- The code package is `features/`: a feature is a column of a rollup definition
  ([Rollups as built](#rollups-as-built)), or an expression feature: a formula over stored
  features in `config/site/features/*.toml`, computed on read unless materialised
  ([configuration.md](../configuration.md#expression-features), ADR 0023 step 3).

## L3: Site configuration (shared, reviewed)

```
config/site/
  universe.toml          coverage: which instruments we ingest (all US-listed stocks, ADRs, ETFs incl.
                         leveraged/inverse; test issues excluded). The UNIVERSE is coverage, not a filter.
  sources.toml           enabled vendors, schedules, rate limits, raw retention days
  rollups.toml           default parameters for rollups (e.g. liquidity-class thresholds)
  defaults.toml          backtest defaults (cash, costs, risk limits), screening coverage threshold
  presets/selections/*.toml    shared selections, e.g. liquid_optionable
  presets/strategies/*.toml    shared strategy/screener configs, e.g. short_premium_liquidity
  overrides/leveraged_etfs.csv curated reference corrections (leverage, inverse, tracks)
```

Owner: the repo (changes by PR, recorded by git commit). Read by ingestion (universe, sources,
rollups) and services (defaults, presets). Built today: `defaults.toml`, `universe.toml`,
`sources.toml`, `nightly.toml`, `rollups.toml` ([Rollups as built](#rollups-as-built)),
`overrides/leveraged_etfs.csv` and the presets.

## L4: User configuration (per user)

```
config/users/<user_id>/          git-ignored locally; a DB behind ConfigStore later
  selections/*.toml      the user's own subsets (narrow a preset, or replace it)
  strategies/*.toml      strategy and screener configs: impl + params + selection + schedule + outputs
  watchlists/*.toml      named instrument lists (a selection by explicit ids)
  preferences.toml       export directory; later notifications and UI settings
```

Built today: `selections/` and `strategies/`. Watchlists and preferences are planned.
Resolution order and the narrow/replace rules are in [../configuration.md](../configuration.md).

## Where does a new piece of data go?

| Question | Layer / table |
|---|---|
| Is it a fact about what the instrument is, from a vendor? | L1 `instruments/reference` (company filings facts: `instruments/company`) |
| Is it a number derived from history, and true "as of" a day? | L1 `rollups/instrument/*` (or L2 `rollups/daily/*` if per session) |
| Does it have a value per bar or per snapshot? | L2 `bars/*` or `chains/*` |
| Did it *happen* at a point in time? | L2 `events/*` |
| Is it a choice everyone shares? | L3 `config/site` |
| Is it one user's choice? | L4 `config/users/<id>` |

## L1 columns

**`instruments/reference`** (sourced facts; one snapshot per date). Phase in brackets.

| Group | Columns | Source |
|---|---|---|
| Identity | `instrument_id`, `symbol`, `figi` (1), `cik` (1) | Nasdaq Trader, universe CSVs; Massive / OpenFIGI (1) |
| Company | `name`, `country` (1); SIC, `sector`, `industry`, website… live in `instruments/company` (below); the `description` lives in `instruments/description` (below) | Nasdaq Trader; SEC EDGAR |
| Classification | `asset_class`, `security_type` (COMMON_STOCK, ADR, ETF, ETN, PREFERRED, WARRANT, UNIT, RIGHT, CEF), `exchange`, `currency` | Nasdaq Trader, universe CSVs |
| Contract terms | `multiplier`, `tick_size`, `round_lot` | derived per asset class |
| ETF attributes | `is_etf`, `is_leveraged`, `is_inverse`, `leverage`, `tracks` | ETF flag + `config/site/overrides/leveraged_etfs.csv`; **unknown for an ETF unless supplied** (fail closed) |
| Options | `optionable` | Nasdaq Trader `options.txt`, universe CSVs |
| Status | `status`, `listed_on`, `delisted_on`, `is_test_issue` | Nasdaq Trader, Massive |
| Lineage | `session_date`, `knowledge_ts`, `source`, `run_id` | ingestion |

**`instruments/company`** (SEC EDGAR, phase 1.7; one full snapshot per date, one row per
instrument whose company is known; `algotrade-ingest company-details`)

| Columns | Notes |
|---|---|
| `instrument_id`, `symbol`, `cik`, `cik_source` | CIK from the reference (`reference`) or the SEC ticker map (`sec_map`) |
| `name`, `entity_type`, `former_names`, `exchanges`, `tickers` | as filed with the SEC |
| `sic`, `sic_description`, `sic_division`, `sector`, `industry` | `sector`: SIC ranges → market sector (heuristic); `industry` = SIC description |
| `state_of_incorporation`, `fiscal_year_end` (MMDD), `website` | `website` is blank for most filers |
| `fetched_on` | when SEC was last asked; drives the `refresh_days` refresh |

**`instruments/description`** (ADR 0034; increments merged across runs, one row per instrument;
`algotrade-ingest descriptions`). A short plain-text description of what a company or fund is
about. The read model serves its text as `Instrument.description` (GraphQL; `None` when
nothing is stored).

| Columns | Notes |
|---|---|
| `instrument_id`, `symbol` | stocks and ADRs (Massive) and ETFs (SEC) |
| `description` | stock: Massive's ticker overview (a paragraph); ETF: the investment objective from the SEC prospectus (a sentence or two); `NULL` is a marker that the vendor was asked and had no text |
| `description_source` | `massive_overview` or `sec_fund_objective` |
| `homepage_url`, `total_employees` | from the Massive overview (stocks only) |
| `filed`, `accn` | the prospectus filing date and accession (ETFs only) |
| `fetched_on` | when the vendor was asked; drives `descriptions_refresh_days` |

Reads (`data.reference.descriptions`) union every partition and keep the latest stored row per
instrument; markers are left out of `descriptions` and kept in `stored_descriptions`.

**`instruments/shares`** (SEC company facts, phase 2b.4; increments merged across runs, one row
per instrument, concept, period start, period end and filing date; `algotrade-ingest shares`)

| Columns | Notes |
|---|---|
| `instrument_id`, `symbol`, `cik` | every instrument of a CIK gets the CIK's facts (company totals; companyfacts has no class-specific counts) |
| `concept`, `tag` | share counts: `dei` (cover-page shares outstanding), `weighted_basic` (weighted average basic); financials: `revenue`, `net_income`, `eps_diluted` (`tag` is the us-gaap tag that supplied it); or `checked`: a marker that the CIK was fetched on `fetched_on` (no fact; keeps funds without facts from being refetched nightly) |
| `period_start`, `period_end`, `filed`, `form`, `accn`, `fy`, `fp` | as filed; `filed` is the point-in-time date. `period_start` is part of the key: a year-to-date and a quarterly fact share an end date (null for `dei` and `checked`) |
| `shares`, `class_values` | the count (share concepts only); `class_values` > 1 when several class values of one filing were summed |
| `value`, `unit` | the amount of a financial fact and its unit, `usd` or `usd_per_share` (financial concepts only). A period appears once for the filing that first reported it, plus once per later filing that changed the value (a restatement) |
| `fetched_on` | when SEC was last asked; drives `facts_refresh_days` |

Reads (`data.shares`) union every partition and keep the latest stored version per key. A fact
counts from its `filed` date, whichever partition stored it, so a backfill serves history. The
financial facts only ever add rows to a store that already has share counts: the first
`algotrade-ingest shares --force` after they shipped stores them and leaves the rest alone.

**`macro/series`** (ADR 0048; increments merged across runs, one row per series, observation date
and vintage) holds economic series (`MACRO:<KEY>`) and index levels (`IDX:<KEY>`: index levels
are series, never bars) declared in `config/site/macro.toml` (`config/site/macro.py`):
`series` (the vendor's code), `obs_date`, `vintage_date`, `value` (null where FRED prints "."),
`vintage_kind` (`alfred`: ALFRED's `realtime_start`; `lagged`: `obs_date` + the series'
`release_lag_days`, for unrevised series and observations before ALFRED's first vintage,
`data.macro.vintages`). `vintage_date` is the point-in-time date, not `knowledge_ts` (which
stays the storage stamp): reads (`data.macro.series.series_as_of`) union every partition and
give each observation's latest vintage on or before the session, so a backfill serves history
without lookahead; feature groups read it as `Input("macro/series", ids=...)` and name a series
in `Feature.inputs` as `series:<KEY>`. The `macro` task (`tasks/macro/series.py`) writes it: it
stores only the vintages the table lacks, and a changed `lagged` value is a new vintage dated the
run's session, never an overwrite.

Selections read the company columns as `instrument.<column>` (`instrument.sector`,
`instrument.industry`, `instrument.sic`, `instrument.sic_division`, `instrument.website`,
`instrument.state_of_incorporation`, `instrument.fiscal_year_end`) from the latest snapshot on
or before the session; with no snapshot they are UNKNOWN. ETFs and funds usually have none.

## Rollups as built

A rollup is a **feature group** (ADR 0023): a versioned, pure definition, `<name>@v<N>`, stored
as `rollups/instrument/<name>@v<N>` with one row per instrument per session (phase 2b.2). Each
stored column is a **feature** with a kind, type, unit, description, null meaning and valid
range; every feature is listed in the generated **[feature catalogue](features.md)**
(`make features-doc`).

- **Declaration** (`features/framework/declaration.py`, `FeatureGroup`): name, version, inputs
  (each a table plus a lookback in exchange sessions, required or optional; or only some of its
  instruments, `ids` / `symbols`, or fixed date `windows` for a history years back, ADR 0047), params (a frozen
  dataclass of defaults, or none), its `FEATURES` (`features/framework/feature.py`: one
  `Feature` per output column, in stored order), and a pure
  `compute(inputs, session, params) -> frame`. Groups live in
  `features/rollups/<kind>/<name>.py` (`price/`, `options/`, `corporate/`) and import only
  `core`, `quant`, numpy and pandas (import-linter); the registry is `features/registry.py`
  (`GROUPS`, `FEATURES`, `feature(name)` for descriptions and units).
- **Inputs** are asked of `algotrade.data` by table name (`data/feature_inputs.py`,
  `load_input`; each table's read lives in its `data` owner), never storage or a domain reader,
  once per chunk of up to 126 sessions. `compute` sees only rows on or before its session
  (point in time; a runner guard asserts it). A required input with nothing for a session
  means no row and `no_input` in the run stats, not a failure.
- **Types** come from the features: the framework casts the output to the declared types
  (`features/framework/columns.py`) before the task stores it, so stored types, the selection
  catalogue (`rollup.<name>@v<N>.<column>`) and the `[[table]]` producers all derive from it.
- **Params** come from `config/site/rollups.toml` (one `["<name>@v<N>"]` section per rollup
  with parameters), typed by the one settings loader (`config/site/settings.py`).
- **Rollups read rollups.** An input may name another rollup's table
  (`rollups/instrument/<name>@v<N>`, with a lookback like any input). The registry orders
  rollups by dependency (`features/framework/graph.py`, topological; an unknown dependency or
  a cycle fails at import, and a fitness test checks the order). The task computes them in
  that order, so a rollup reads what its dependencies just wrote (stored rows for sessions
  they did not write); if a dependency fails, its dependents are not computed this run (a
  failed item each). `compute_in_memory` evaluates a chain without writing: each rollup reads
  the frames the earlier ones produced in memory (`produced`), which win over stored rows.
- **Computed by** the `rollups` ingestion task: `algotrade-ingest rollups [--date D | --from D
  --to D] [--only price_stats@v2,...]` (alias `features`). A backfill computes each session
  exactly as the nightly run would have. Nightly runs it for every session it ingests, after
  earnings, bars, corporate actions, rates and chains. `--only` computes just the named
  rollups; their dependencies are read from the store.
- **Market-entity groups** (ADR 0047). A group declared with `entity = "market"` describes the
  whole market, not an instrument: breadth, trend, stress. It is stored as
  `rollups/market/<name>@v<N>` with **one row per session**, `instrument_id = MKT:US`
  (`core.model.instruments.market_id`, the only place that id is built; the column is the
  storage key, as `RATE:UST-3M` is for rates), the point-in-time columns unchanged, and is
  read as `market.<name>@v<N>.<column>`, never selected per instrument. Its compute has the
  same signature and reads ordinary multi-instrument frames (all of `bars/1d`, other groups'
  tables), plus `universe` (the session's universe snapshot, `None` before the first one: a
  later list would count today's survivors) and `instruments/symbol_ids` (symbol -> id from the
  reference snapshot, to find SPY without building an id). `symbol_ids` is a lookup only, never
  a population (it may come from a later snapshot); `universe` is the population. A group that
  reads a few tickers declares `Input("bars/1d", symbols=(...))` and loads only the bars of the
  ids they resolve to in each session's reference snapshot (the union over the chunk), not every
  instrument's. The runner
  fails the group unless it returns exactly that one row. An instrument group never reads a
  market group (broadcasting needs its own ADR), and a market group's `applies_to` is `any`.
  An expression feature takes the entity of what it reads; one
  that reads two entities is a definition error. `compute_rollups(..., entity="market")`
  computes them after the instrument groups; the catalogue lists them under "Market features".
  The groups (`features/rollups/market/`): `market_trend@v2` (the S&P 500, the Nasdaq-100 and
  the Nasdaq Composite vs their 200-day average, death cross, drawdown, realised vol, returns:
  `spx_` from SPY's bars when its 253-session window is complete, else from the `IDX:SPX`
  level of `macro/series`, `ndx_` from QQQ's bars, `comp_` from the `IDX:COMP` level; one
  source per prefix and session, never mixed in a window, said by `spx_source` / `comp_source`;
  an index window counts the last observations known by the session, which is the previous
  session's close (`pit = "lag"`), null when the newest is more than 2 sessions old; the
  index-fed columns are `personal`), `market_breadth@v1` (the shares of the
  session's universe stocks above their averages and in a bear, new highs minus lows, the Zweig
  thrust, 90% down days; null below `min_coverage`) and `market_cross_asset@v1` (turbulence and
  the absorption ratio of an ETF basket, leadership ratios), from `bars/1d`;
  `market_macro@v3` (the curve from the session's own `rates/treasury` curve else FRED, credit
  spreads, labour, financial conditions, lending, policy, inflation, activity, the excess bond
  premium, the OFR stress index, policy uncertainty, VIX / VIX3M: each the latest observation of `macro/series` known by the session, by vintage, with the
  registry's `yoy` / `diff` transform applied here; null without FRED data, the row still
  written); `regime_indicators@v1` (per regime card: the value, its on / off verdict and
  whether it changed within 5 sessions); and `regime@v3` (`market_stress` and the macro
  score's early and confirming tiers, `macro_early` and `macro_confirming`, on the covered-weight
  scale, `macro_risk` the higher tier, their unnormalised `_raw`, `fragility`, the label with a stateless 5-session hold, coverage and missing counts: no
  data is UNKNOWN, never CALM). The groups' thresholds and weights are their
  `config/site/rollups.toml` sections; the plan's context signals (VIX band, drawdown band,
  death cross, ...) and the bear-state probit (`bear_prob_6m`, `bear_prob_source`: its
  coefficients are params; `make regime-scorecard` prints a fit to paste, with
  `fitted_through`, and a pasted fit is a version bump) are market expression features in
  `config/site/features/regime.toml`.

Per-column meanings, units, ranges and null meanings: [features.md](features.md). Floats of
the v2 groups are stored as 32-bit (`float32`). Columns computed from other columns are
expression features (`feature.<name>`): `pct_from_high_52w`, `pct_from_low_52w`, `near_52w`,
`div_yield` (materialised as `rollups/instrument/div_yield@v1`: `iv30@v1` reads it),
`market_cap`, `pe_ratio`, `revenue_growth_yoy`, `iv_hv_spread`, `iv_hv_ratio`, and the liquidity class (`liquidity_class`,
`option_tier`, ...; the former `liquidity_class@v1` group). The v1 tables they replaced stay
readable until `algotrade-ingest retire-features --group <name>@v1` deletes them.

| Group | Columns | Inputs | Status |
|---|---|---|---|
| `option_liquidity@v1` | `liq_status`, put/call tiers, target expiry + DTE, short strike, spreads, zone OI / volume, chain OI / volume, `underlying_price`, `iv30`, `stock_volume`, `chain_asof` (date) | the session's `chains/status` (required), `chains/option_quotes`, `chains/underlying_quotes` | built |
| `price_stats@v2` | `close`, `sma_20/50/200`, `ret_20d/60d`, `high_52w`, `low_52w`, `hv20`, `hv30` (close-to-close), `hv20_yz` (Yang-Zhang), `adv_usd_20d`, `history_days` | `bars/1d` split-adjusted as of the session (not total return), 252 sessions back | built |
| `price_history@v1` | `bar_status` (TRADED / NO_TRADE), `last_bar_session`, `range_sessions`, `range_status` (FULL / SINCE_LISTING / NEW_LISTING / FEW_BARS / NO_HISTORY), `high_avail`, `low_avail` | `bars/1d` split-adjusted as of the session, 252 + 60 sessions back; params in `config/site/rollups.toml` | built |
| `episode_behaviour@v1` | `beta_252d`, `corr_252d` (log returns on SPY's), `dd_<episode>` and `recovery_sessions_<episode>` for `covid_2020`, `hikes_2022`, `tariffs_2025` (ADR 0047) | `bars/1d` split-adjusted, 252 sessions back; `instruments/symbol_ids` (SPY's id); `bars/1d#windows`: each episode's own closes from 5 sessions before its peak to 400 after its trough (`Input.windows`) | built |
| `earnings@v1` | `next_earnings_date`, `earnings_time` (pre / post / unknown), `days_to_earnings` (sessions), `date_confirmed` (null: the source does not say), `last_earnings_date` | every `events/earnings` snapshot stored on or before the session | built |
| `earnings_schedule@v1` | `next_status` (SCHEDULED / NOT_ANNOUNCED): the status of `earnings@v1`'s next-report features (ADR 0046) | `events/earnings`, through `earnings@v1`'s compute (same rows) | built |
| `fund_reference@v1` | `reference_instrument_id` (the one stock a leveraged or inverse fund tracks), `reference_kind` (single_stock / index / sector / commodity / none), `reference_source` (holdings / name_rule), `reference_status` (ADR 0050); rows only for those funds, `applies_to = leveraged_fund` | `instruments/reference` (name, flags, security types), `holdings/etf` (the funds' latest holdings), `instruments/symbol_ids` | built |
| `dividends@v2` | `div_ttm`, `div_count_ttm`, `last_ex_date` | `events/dividend`, `events/split` (by event date), `price_stats@v2` | built |
| `dividend_schedule@v1` | `dividend_status` (SCHEDULED / NOT_ANNOUNCED: the status of the next-ex-date features), `next_ex_date`, `next_div_amount` (split-adjusted to the session), `days_to_ex_date`, `next_pay_date`: the next ex-dividend date after the session among the dividend rows stored by it (a declared date is known from the session that stored it) | `events/dividend_declared` (`events/dividend` by knowledge date), `events/split` (by event date), `price_stats@v2` | built |
| `div_yield@v1` | `div_yield` (the materialised expression feature) | `dividends@v2`, `price_stats@v2` | built |
| `iv30@v1` | `iv30` (ours), `iv30_cboe`, `iv30_status`, `near_expiry`, `far_expiry`, `atm_strike_near`, `spot`, `rate`, `div_yield`, `n_quotes_used` | the session's `chains/option_quotes` + `chains/underlying_quotes`, `rates/treasury`, `div_yield@v1` | built |
| `iv_history@v2` | `iv30`, `iv_rank_252d`, `iv_percentile_252d`, `history_days`, `rank_status` (UNKNOWN / PROVISIONAL / FULL) | `iv30@v1` over 252 sessions | built |
| `fundamentals@v2` | `shares_outstanding`, `shares_as_of`, `shares_filed`, `shares_source` (dei / weighted_basic), `market_cap_status` (OK / NO_SHARES / STALE / NO_PRICE) | `instruments/shares` (filed on or before the session), `price_stats@v2` close, `events/split`; `stale_days` in `config/site/rollups.toml` | built |
| `financials@v1` | `revenue_ttm`, `revenue_ttm_year_ago`, `net_income_ttm`, `eps_diluted_ttm`, `revenue_fy`, `revenue_fy_end`, `ttm_as_of`, `ttm_filed`, `ttm_basis` (QUARTERS / ANNUAL), `eps_stale`, `is_adr`, `financials_status` (OK / PARTIAL / NO_TTM / NO_FACTS / STALE) | `instruments/shares` financial concepts (filed on or before the session), `price_stats@v2` (which instruments get a row), `events/split`, `instruments/reference` (security type); `stale_days`, `history_days` in `config/site/rollups.toml` | built |
| `put_wing@v1` | `wing_status` (OK / OUTSIDE_BAND / NO_SPOT / NO_CHAIN / NO_EXPIRY / NO_STRIKE), `target_expiry` + `target_dte` (nearest 45 days in 30..60, standard monthlies first), `n_unpriced`; band totals of the puts with OUR \|delta\| in 0.08..0.15 (`n_strikes`, `wing_oi`, `wing_volume`, `wing_spread_pct`); the best put among 0.05..0.35 delta, nearest the band then by cash-secured ROC (`delta_band_distance`, `best_put_strike`, `_delta`, `_iv`, `_mid`, `_oi`, `_volume`, `_spread_pct`, `_roc`) | the session's `chains/option_quotes` + `chains/underlying_quotes`, `rates/treasury`, `div_yield@v1` | built |
| `call_wing@v1` | the covered-call mirror of `put_wing@v1`, by the same search: `wing_status`, `target_expiry` + `target_dte`, `n_unpriced`; band totals of the calls with OUR delta in 0.15..0.30 (`n_strikes`, `wing_oi`, `wing_volume`, `wing_spread_pct`); the best call among 0.05..0.50 delta, nearest the band then by premium yield mid / spot, then OI, then the higher strike (`delta_band_distance`, `best_call_strike`, `_delta`, `_iv`, `_mid`, `_oi`, `_volume`, `_spread_pct`, `_yield`) | the session's `chains/option_quotes` + `chains/underlying_quotes`, `rates/treasury`, `div_yield@v1` | built |
| `price_moves@v1` | `one_day_move`: the largest \|close-to-close return\| over the last 20 sessions | `bars/1d` split-adjusted as of the session, 20 sessions back | built |
| `momentum@v1` | `atr_14`, `rsi_14` (Wilder, 150-session warm-up), `ret_5d`, `rel_volume` (vs the 20 sessions before), `high_20d`, `low_20d`, `high_50d`, `low_50d`, `prior_high_20d` ([swing.md](swing.md)) | `bars/1d` split-adjusted as of the session, 149 sessions back | built |
| `volume@v1` | `session_volume`, `dollar_volume`, `adv_shares_20d`, `volume_ratio_5d_20d` (last 5 vs last 20 sessions), `volume_z_20d` (vs the 20 sessions before), `up_volume_share_20d`, `cmf_20d` (Chaikin money flow) | `bars/1d` split-adjusted as of the session, 20 sessions back | built |
| `swing_levels@v1` | `swing_high` / `swing_high_date` (resistance: the most recent confirmed swing high above the close), `swing_low` / `swing_low_date` (support); pivots 5 bars each side, confirmed 5 sessions later ([swing.md](swing.md)) | `bars/1d` split-adjusted as of the session, 251 sessions back | built |
| `pivot_strength@v1` | `resistance_touches` / `support_touches` (distinct touches of the swing level within 0.5 ATR over 252 sessions), `resistance_age` / `support_age` (sessions since the pivot), `pivot_structure` (HH_HL / LH_LL / MIXED from the last two swing highs and lows) ([swing.md](swing.md)) | `bars/1d` split-adjusted as of the session, 251 sessions back, and the session's `swing_levels@v1` and `momentum@v1` rows | built |
| `retest@v1` | `breakout_date`, `breakout_level`, `sessions_since_breakout` (the latest 20-session breakout of the last 60 sessions), `retest_state` (FAILED / NONE / RETESTING / HELD / FRESH / NO_ATR), `failed_breakouts_252d` ([swing.md](swing.md)) | `bars/1d` split-adjusted as of the session, 291 sessions back, and the session's `momentum@v1` rows | built |
| `gaps@v1` | `gap_open_pct` (today's open vs the previous close), `gap_above` / `gap_above_date` (nearest unfilled down gap above the close), `gap_below` / `gap_below_date` (nearest unfilled up gap below it) ([swing.md](swing.md)) | `bars/1d` split-adjusted as of the session, 252 sessions back | built |
| `bands@v2` | `ema_10/20/50/200`, `sma_150`, `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d`, `close_std_20`, `bb_width_pctile_252d` (the squeeze: the bandwidth's rank against the year), `band_walk` (signed sessions outside the bands) ([technical.md](technical.md)) | `bars/1d` split-adjusted as of the session, 399 sessions back | built |
| `trend_stats@v2` | `ret_1d/3d/10d/120d/252d`, `mom_12_1` (12-1 momentum), `mom_accel_5d`, `ret_z_20d`, `high_100d`, `low_100d`, `high_200d`, `low_200d`, `prior_high_50d`, `prior_low_20d`, `prior_low_50d`, `sessions_since_high_20d`, `close_range_pos`, `trend_r2_90d`, `reg_slope_90d_ann`, `close_streak`, `sma20_streak`, `tight_range_sessions` ([technical.md](technical.md)) | `bars/1d` split-adjusted as of the session, 252 sessions back | built |
| `anchored_vwap@v1` | `avwap_earnings` (VWAP of the typical price from the last earnings anchor session: the report day, or the next session for a report after the close), `avwap_anchor_date` | `events/earnings` snapshots (read as `earnings@v1` reads them), `bars/1d` split-adjusted as of the session, 126 sessions back | built |
| `oi_walls@v1` | `wall_status` (OK / PARTIAL / NO_OI / NO_SPOT / NO_CHAIN / NO_EXPIRY), `call_wall` + `call_wall_oi` (most call OI at or above spot), `put_wall` + `put_wall_oi` (most put OI at or below spot); OI summed across expiries 1..60 days out, ties nearer spot | the session's `chains/option_quotes`, `chains/underlying_quotes` | built |
| `nearest_expiry@v1` | `expiry_date` (the nearest listed expiry on or after the session; 0-DTE counts), `dte` (calendar days to it), `sessions_to_expiry` (exchange sessions after the session up to it); a row per underlying with a chain, null when every listed expiry is past. `feature.earnings_before_expiry` (`config/site/features/earnings.toml`) compares it with `earnings@v1.next_earnings_date` | the session's `chains/option_quotes` | built |

**`fundamentals@v2` rules.** Among facts FILED on or before the session: the latest cover
count (`dei`; latest filed, then latest period end, so an amendment wins) while the company
still tags it (its latest `dei` filing is no older than its latest weighted average), else the
latest filing's weighted average basic. Splits after the count multiply it (after
`period_end` for a cover count, after `filed` for a weighted average, which filers restate).
The expression feature `market_cap = shares_outstanding x close` only when `OK`; `NO_SHARES` (ETFs, funds, no CIK:
null, not an error), `STALE` (period end more than `stale_days`, 400, before the session;
the count is still shown) and `NO_PRICE` have a null market cap. Counts are company totals,
so a class's market cap is the total times its own close (fine for GOOGL / GOOG, wrong for
classes at very different prices, such as BRK.A / BRK.B). One row per instrument with a
`price_stats@v2` row or a share count.

**`financials@v1` rules.** Among facts FILED on or before the session (a filing counts for
the session of its filing date, even one made in the evening: the same few-hours look-ahead as
`fundamentals@v2`), each (concept, tag, period) takes its latest known value (a restatement
counts from its filing date). Per concept a TTM is: (1) `QUARTERS`: the sum of the last four
consecutive discrete quarters, when the newest quarter ends on or after the newest fiscal year;
a discrete quarter is a reported three-month fact (the best revenue tag first), else the
difference of two year-to-date facts of one fiscal year and **one tag** (6M minus 3M, 9M minus
6M, and Q4 as the annual figure minus 9M; the 10-K therefore makes Q4 public on its filing
date). The two facts must have been filed within 150 days of each other, i.e. belong to one
restatement generation (a restated annual figure is not subtracted from an unrestated nine
months), and a derived revenue quarter is never negative; otherwise that quarter is unknown and
the TTM falls back; (2) else `ANNUAL`: the latest fiscal year (a filer that reports only
annually, or whose quarters do not chain, such as a bank that tags quarterly revenue
differently); (3) else null. `revenue_ttm_year_ago` is the same TTM one year earlier: the four
quarters ending 340 to 380 days before the newest one, or the previous fiscal year; null when
that history has a hole, so `revenue_growth_yoy = revenue_ttm / revenue_ttm_year_ago - 1` is
never measured over more than a year. `revenue_fy` / `revenue_fy_end` are the latest annual
revenue fact. `eps_diluted_ttm` sums the quarterly diluted EPS (not strictly additive when the
share count moves, the usual definition) after dividing each EPS fact by the ratio of every split
that took effect after the fact's filing date and on or before the session, so it is on the
same basis as the split-adjusted close. Revenue is stored under `Revenues`,
`RevenueFromContractWithCustomerExcludingAssessedTax` and `SalesRevenueNet` (all three kept);
the group prefers them in that order for a period. Statuses: `NO_FACTS` (ETFs, funds, no CIK,
non-USD issuers; every value null, never an error), `NO_TTM` (facts but no TTM can be formed),
`PARTIAL` (some of the three), `STALE` (the first TTM present, revenue else net income else EPS,
ended more than `stale_days`, 480, before the session; values still shown), else `OK`.
`ttm_as_of`, `ttm_filed` and `ttm_basis` describe that same first TTM (revenue's, normally).
`eps_stale` says the EPS TTM itself is stale, and `is_adr` that the instrument is an ADR
(`instruments/reference` security type). The expression feature
`pe_ratio = close / eps_diluted_ttm` is null when `eps_diluted_ttm` is missing or not positive
(a negative P/E is not shown), when the close is not positive, when `eps_stale`, and for an ADR:
an ADR's EPS is per ordinary share and the ADR ratio is not stored. Every instrument of a CIK
gets the company's figures, which is right for classes with equal economics (GOOGL / GOOG) and
wrong otherwise. One row per instrument with a `price_stats@v2` row or a financial fact. The
whole `instruments/shares` table is read once per `rollups` run and filtered per session.

**`price_history@v1` rules (ADR 0046).** One row per instrument with a bar among the last
`year_sessions` (252), so a stock with no bar on the session has a row saying `NO_TRADE` (its
`close` reads "No trade", never an older close). `range_status` is FULL with `full_bars` (240)
bars in the window (as the 52-week high / low), SINCE_LISTING when no bar falls in the
`listing_quiet` (60) sessions before the window's first bar and that bar is at least
`min_listing_sessions` (20) sessions back, NEW_LISTING when younger, FEW_BARS for an older
name trading too rarely, and NO_HISTORY when a session these rules rest on has no bars in the
store at all (it starts inside the lookback): never a false "new listing", the range stays UNKNOWN;
`high_avail` / `low_avail` exist for FULL and SINCE_LISTING (`feature.pct_from_high_avail`).

**`price_stats@v2` rules.** Windows are exchange sessions, not "the instrument's last n bars":
a session without a bar is a gap, and a statistic is null (UNKNOWN), never zero or computed
over a shorter window, unless every session of its window has a bar. The 52-week high / low
(daily highs / lows) need `min_year_sessions` (240) bars among the last `year_sessions` (252).
Prices are split-adjusted as of the session: a later split never changes an earlier row.
Returns and volatilities are scale-free; `adv_usd_20d` is close x volume, split-invariant.
The 52-week high / low are on split-adjusted prices, **not dividend-adjusted** (decided
2026-10-03 after the IBKR comparison: IBKR's 52-week range is dividend-adjusted, so on a payer
it sits below ours by up to the dividends paid since the extreme; we keep the traded-price
basis). `hv20` / `hv30` are close-to-close: the sample stdev of the last 20 / 30 log returns
x sqrt(252); IBKR's own historical volatility uses another estimator and differs. Both are
checked against recorded IBKR data by the reconciliation suite (`docs/testing.md`).
The windows named in the columns are part of the definition (changing one is a new version).

**`episode_behaviour@v1` rules (ADR 0047).** The episode dates are code constants checked against
`config/site/regime/episodes.toml`; a column is null before the episode's trough (`known_from`), and
for an instrument with under 80% of the sessions from peak to trough on file. The drawdown is
the worst close-to-close fall from the instrument's own running high (it starts 5 sessions
before the peak); recovery counts the sessions from the trough until a close regains the
pre-episode high, and is null until it does (or beyond 400 sessions). Each episode reads only its
own window of closes (`Input.windows`, one split adjustment per window), never the years in
between; the nightly recomputes the settled columns, as a group has no cadence of its own.

**`dividends@v2` rules.** `div_ttm` sums cash dividends with ex-date in (session - 365 days,
session], each divided by the ratio of every split after its ex-date up to the session, so it
is in the same share terms as the session's close; the expression feature
`div_yield = div_ttm / close` (null unless the close is positive). Distributions
typed `special` are left out by default. No dividend in the window is 0 only with at least
`min_history_days` (240) bars among the last 252 sessions; otherwise every column is null.
A future (declared) ex-date never counts.

**`dividend_schedule@v1` rules.** The one place a declared future ex-date counts. It reads
`events/dividend` by KNOWLEDGE date (`events/dividend_declared`): on session S the rows are those
stored in partitions on or before S (a dividend declared later is not known), the next ex-date
is the earliest one after S, and a date the latest listing drops beside another is ignored (moved
or withdrawn). The corporate-actions window is `-7..+30` days, so a date is listed only from
about 30 days before it: `NOT_ANNOUNCED` means none known yet, not none this quarter. Every
distribution type counts (a special dividend is an ex-date too). The amount is divided by the
splits after the partition that stored it, up to S. Sessions older than the first stored
partition read `NOT_ANNOUNCED`.

**`iv30@v1` rules.** Our constant-maturity 30-day ATM vol, computed beside Cboe's and used by
default (ADR 0021, "IV30"): bracketing expiries (standard monthlies first, 7 to 90 days),
forward ATM `F = S e^{(r-q)t}` with `r` from the Treasury curve and `q = div_yield`, the two
strikes around `F`, mid prices of calls and puts that pass the quality filters inverted with
`quant.implied_vol`, put/call average, linear in strike to `F`, then linear in total variance
to 30 days. `iv30_status` says why a value is missing (`NO_SPOT`, `NO_CHAIN`, `NO_EXPIRY`,
`NO_QUOTES`, `WIDE_SPREADS`, `ILLIQUID`, `IV_FAILED`); `SINGLE_EXPIRY` (one usable expiry,
flat vol) still has a value. `iv30_cboe` is the feed's percentage as a decimal.

**`iv_history@v2` rules.** Over the last 252 sessions (today included) of `iv30@v1.iv30`
(`source = "cboe"` switches to the feed's): rank `(iv - min) / (max - min)` (null when flat),
percentile = share of earlier IVs strictly below today's, `history_days` = sessions with an IV.
`rank_status` is UNKNOWN below 60 sessions (rank and percentile null), PROVISIONAL below 252,
FULL from 252 (owner decision). History starts with the first stored chain: nothing is
back-filled from before chains were collected. The expression features
`iv_hv_spread = iv30 - hv30` and `iv_hv_ratio = iv30 / hv30` (`price_stats@v2`) are the
variance-risk-premium inputs.

**Liquidity class (expression features, `config/site/features/liquidity.toml`).** HIGH when
every HIGH threshold holds (ADV, close, the worse of the put / call option tier, chain open
interest and volume), else MEDIUM when every MEDIUM one does, else LOW. A threshold that cannot
be checked (null ADV; no `option_liquidity@v1` for the session; a failed chain fetch) is
unknown, and the class is UNKNOWN unless it is decided without it (three-valued logic). An
instrument not in the session's chain run has no options. The thresholds are the params of
`liquidity_high` / `liquidity_medium`; a change to one is a new feature version.

**`earnings@v1` rules.** The earnings task stores, each session, the calendar for the days
ahead. For each report date the authority is the latest snapshot on or before the session
whose range covers it (from its session, or its earliest row, to its latest row): a date a
later snapshot no longer lists was moved or cancelled. `days_to_earnings` is 0 on the report
day and counts sessions (`core/time/calendar.py`). Sessions before the first stored snapshot
have no row (UNKNOWN); a backfill does not invent what was not stored then.

Past report dates (for `last_earnings_date` and `anchored_vwap@v1`) are backfilled into the
latest session's snapshot, never under past sessions: `algotrade-ingest earnings --date
<latest session> --start <past day> --days <N>` fetches past calendar days (rows with
`reported` true) into that session's partition, where they merge with its nightly window
(`events/*` runs merge, ADR 0007), and the snapshot's range then starts at its earliest row.
They count from that session on; earlier sessions stay UNKNOWN. Done 2026-10-04 for
2026-03-16..2026-10-02 into the 2026-10-02 snapshot.
