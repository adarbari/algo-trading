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
 │     TIME          chains/*              option-chain snapshots (instrument × contract)  │
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
| `rollups/instrument/<name>@vN` | **derived state** "as of D", computed from L2 | next earnings date + time + days to it, ADV (20d $), liquidity class ("highly liquid"), option liquidity tiers, market cap, 52-week high/low, HV20/30, IV30 and IV rank | nightly | rollup (features) jobs |

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
  `SymbolResolver` (`StoreReader.resolver(session)`).
- **InstrumentView** (`StoreReader.instrument_view(session, fields)`) returns reference facts
  (latest snapshot on or before the session) joined with rollups **for** the session, one row
  per instrument, columns named by field. A rollup with no data for the session is listed in
  `missing`, and its fields are UNKNOWN to selections (never stale values).

## L2: Instrument × time (values)

| Table | Grain (one row is…) | Interval | Notes |
|---|---|---|---|
| `bars/<interval>` | instrument × bar start | `1d` (phase 1), `1h`/`5m`/`1m` later | OHLCV + VWAP, **unadjusted**; splits and dividends applied at read time from `events` |
| `chains/option_quotes`, `chains/underlying_quotes`, `chains/status` | contract (or underlying) × snapshot | end of day | built (Cboe) |
| `events/<type>` | instrument × event time | irregular | `earnings`, `split`, `dividend`, `reference_change`, `index_change` |
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
bars/1d ─────────────────────────────────────┼─► rollups/instrument/price_stats@v1   (52w hi/lo, MAs, HV, ADV)
chains/* ────────────────────────────────────┼─► rollups/instrument/option_liquidity@v1, iv_history@v1
events/earnings ─────────────────────────────┴─► rollups/instrument/earnings@v1     (next date, days to it)
```

- **Official daily bars win.** The vendor's `1d` bar (official close, including the closing
  auction) is the source of truth. A daily bar rolled up from `1m` bars is a cross-check,
  never a substitute.
- The code package is `features/`: a feature is a rollup definition.

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
`overrides/leveraged_etfs.csv` and the presets; `sources.toml` and `rollups.toml` arrive with
the phases that read them (see [roadmap](../roadmap.md)).

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
| Company | `name`, `description` (1), `country` (1); SIC, `sector`, `industry`, website… live in `instruments/company` (below) | Nasdaq Trader; SEC EDGAR, Massive ticker details (1) |
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

Selections read the company columns as `instrument.<column>` (`instrument.sector`,
`instrument.industry`, `instrument.sic`, `instrument.sic_division`, `instrument.website`,
`instrument.state_of_incorporation`, `instrument.fiscal_year_end`) from the latest snapshot on
or before the session; with no snapshot they are UNKNOWN. ETFs and funds usually have none.

**`rollups/instrument/*`** (derived "as of D"; one table per rollup, versioned)

| Rollup | Columns | Inputs | Phase |
|---|---|---|---|
| `option_liquidity@v1` | put/call tiers, target expiry, spreads, zone OI, chain OI | `chains/*` | built |
| `price_stats@v1` | `close`, `sma_20/50/200`, `ret_20d/60d`, `high_52w`, `low_52w`, `pct_from_high/low`, `hv20`, `hv30`, `adv_usd_20d` | `bars/1d` + split events | 2b |
| `liquidity_class@v1` | `liquidity_class` (HIGH/MEDIUM/LOW) with the thresholds used | `price_stats`, `option_liquidity`, `config/site/rollups.toml` | 2b |
| `iv_history@v1` | `iv30`, `iv_rank_252d`, `iv_percentile_252d`, `history_days` (UNKNOWN below the minimum) | `chains/underlying_quotes` history | 2b |
| `earnings@v1` | `next_earnings_date`, `earnings_time` (pre/post), `days_to_earnings`, `date_confirmed` | `events/earnings` | 2b |
| `fundamentals@v1` | `market_cap`, `shares_outstanding` | Massive / EDGAR | 2b |
