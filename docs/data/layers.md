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
| `rollups/instrument/<name>@vN` | **derived state** "as of D", computed from L2 | next earnings date + time + days to it, ADV (20d $), liquidity class ("highly liquid"), option liquidity tiers, market cap, 52-week high/low, HV20/30, IV30 and IV rank | nightly | the `rollups` task |

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
| `chains/option_quotes`, `chains/underlying_quotes`, `chains/status` | contract (or underlying) × snapshot | end of day | built (Cboe) |
| `events/<type>` | instrument × event time | irregular | `earnings`, `split`, `dividend`, `reference_change`, `index_change` |
| `rates/treasury` | curve date × tenor (`RATE:UST-<tenor>`) | daily (bond-market days) | U.S. Treasury par yield curve: `tenor`, `tenor_days`, `rate_par`, `rate_cont` (decimals; ADR 0021). One partition per curve date; read through `data.rates.curve(reader, on)` (latest on or before, earliest flagged) |
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
chains/* ────────────────────────────────────┼─► rollups/instrument/option_liquidity@v1, iv30@v1 ─► iv_history@v1
events/earnings ─────────────────────────────┴─► rollups/instrument/earnings@v1     (next date, days to it)
```

- **Official daily bars win.** The vendor's `1d` bar (official close, including the closing
  auction) is the source of truth. A daily bar rolled up from `1m` bars is a cross-check,
  never a substitute.
- The code package is `features/`: a feature is a rollup definition
  ([Rollups as built](#rollups-as-built)).

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

**`instruments/shares`** (SEC company facts, phase 2b.4; increments merged across runs, one row
per instrument, concept, period end and filing date; `algotrade-ingest shares`)

| Columns | Notes |
|---|---|
| `instrument_id`, `symbol`, `cik` | every instrument of a CIK gets the CIK's facts (company totals; companyfacts has no class-specific counts) |
| `concept`, `tag` | `dei` (cover-page shares outstanding), `weighted_basic` (weighted average basic), or `checked`: a marker that the CIK was fetched on `fetched_on` (no shares; keeps funds without facts from being refetched nightly) |
| `period_start`, `period_end`, `filed`, `form`, `accn`, `fy`, `fp` | as filed; `filed` is the point-in-time date |
| `shares`, `class_values` | the count; `class_values` > 1 when several class values of one filing were summed |
| `fetched_on` | when SEC was last asked; drives `facts_refresh_days` |

Reads (`data.shares`) union every partition and keep the latest stored version per key. A fact
counts from its `filed` date, whichever partition stored it, so a backfill serves history.

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
  (each a table plus a lookback in exchange sessions, required or optional), params (a frozen
  dataclass of defaults, or none), its `FEATURES` (`features/framework/feature.py`: one
  `Feature` per output column, in stored order), and a pure
  `compute(inputs, session, params) -> frame`. Groups live in `features/rollups/<name>.py`
  and import only `core`, `quant`, numpy and pandas (import-linter); the registry is
  `features/registry.py` (`GROUPS`, `FEATURES`, `feature(name)` for descriptions and units).
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
  --to D] [--only price_stats@v1,...]` (alias `features`). A backfill computes each session
  exactly as the nightly run would have. Nightly runs it for every session it ingests, after
  earnings, bars, corporate actions, rates and chains. `--only` computes just the named
  rollups; their dependencies are read from the store.

Per-column meanings, units, ranges and null meanings: [features.md](features.md).

| Group | Columns | Inputs | Status |
|---|---|---|---|
| `option_liquidity@v1` | `liq_status`, put/call tiers, target expiry + DTE, short strike, spreads, zone OI / volume, chain OI / volume, `underlying_price`, `iv30`, `stock_volume`, `chain_asof` (date) | the session's `chains/status` (required), `chains/option_quotes`, `chains/underlying_quotes` | built |
| `price_stats@v1` | `close`, `sma_20/50/200`, `ret_20d/60d`, `high_52w`, `low_52w`, `pct_from_high_52w`, `pct_from_low_52w`, `hv20`, `hv30` (close-to-close), `hv20_yz` (Yang-Zhang), `adv_usd_20d`, `history_days` | `bars/1d` split-adjusted as of the session (not total return), 252 sessions back | built |
| `earnings@v1` | `next_earnings_date`, `earnings_time` (pre / post / unknown), `days_to_earnings` (sessions), `date_confirmed` (null: the source does not say), `last_earnings_date` | every `events/earnings` snapshot stored on or before the session | built |
| `dividends@v1` | `div_ttm`, `div_yield`, `div_count_ttm`, `last_ex_date` | `events/dividend`, `events/split` (by event date), `price_stats@v1` | built |
| `iv30@v1` | `iv30` (ours), `iv30_cboe`, `iv30_status`, `near_expiry`, `far_expiry`, `atm_strike_near`, `spot`, `rate`, `div_yield`, `n_quotes_used` | the session's `chains/option_quotes` + `chains/underlying_quotes`, `rates/treasury`, `dividends@v1` | built |
| `iv_history@v1` | `iv30`, `iv_rank_252d`, `iv_percentile_252d`, `history_days`, `rank_status` (UNKNOWN / PROVISIONAL / FULL), `iv_hv_spread`, `iv_hv_ratio` | `iv30@v1` over 252 sessions, `price_stats@v1` | built |
| `liquidity_class@v1` | `liquidity_class` (HIGH / MEDIUM / LOW / UNKNOWN), `adv_usd_20d`, `close`, `option_tier`, `chain_oi`, `rule_hash` | `price_stats@v1`, `option_liquidity@v1`, thresholds in `config/site/rollups.toml` | built |
| `fundamentals@v1` | `shares_outstanding`, `shares_as_of`, `shares_filed`, `shares_source` (dei / weighted_basic), `market_cap`, `market_cap_status` (OK / NO_SHARES / STALE / NO_PRICE) | `instruments/shares` (filed on or before the session), `price_stats@v1` close, `events/split`; `stale_days` in `config/site/rollups.toml` | built |

**`fundamentals@v1` rules.** Among facts FILED on or before the session: the latest cover
count (`dei`; latest filed, then latest period end, so an amendment wins) while the company
still tags it (its latest `dei` filing is no older than its latest weighted average), else the
latest filing's weighted average basic. Splits after the count multiply it (after
`period_end` for a cover count, after `filed` for a weighted average, which filers restate).
`market_cap = shares_outstanding x close` only when `OK`; `NO_SHARES` (ETFs, funds, no CIK:
null, not an error), `STALE` (period end more than `stale_days`, 400, before the session;
the count is still shown) and `NO_PRICE` have a null market cap. Counts are company totals,
so a class's market cap is the total times its own close (fine for GOOGL / GOOG, wrong for
classes at very different prices, such as BRK.A / BRK.B). One row per instrument with a
`price_stats@v1` row or a share count.

**`price_stats@v1` rules.** Windows are exchange sessions, not "the instrument's last n bars":
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
The windows named in the columns are the v1 definition (changing one is a v2).

**`dividends@v1` rules.** `div_ttm` sums cash dividends with ex-date in (session - 365 days,
session], each divided by the ratio of every split after its ex-date up to the session, so it
is in the same share terms as the session's close; `div_yield = div_ttm / close`. Distributions
typed `special` are left out by default. No dividend in the window is 0 only with at least
`min_history_days` (240) bars among the last 252 sessions; otherwise every column is null.
A future (declared) ex-date never counts.

**`iv30@v1` rules.** Our constant-maturity 30-day ATM vol, computed beside Cboe's and used by
default (ADR 0021, "IV30"): bracketing expiries (standard monthlies first, 7 to 90 days),
forward ATM `F = S e^{(r-q)t}` with `r` from the Treasury curve and `q = div_yield`, the two
strikes around `F`, mid prices of calls and puts that pass the quality filters inverted with
`quant.implied_vol`, put/call average, linear in strike to `F`, then linear in total variance
to 30 days. `iv30_status` says why a value is missing (`NO_SPOT`, `NO_CHAIN`, `NO_EXPIRY`,
`NO_QUOTES`, `WIDE_SPREADS`, `ILLIQUID`, `IV_FAILED`); `SINGLE_EXPIRY` (one usable expiry,
flat vol) still has a value. `iv30_cboe` is the feed's percentage as a decimal.

**`iv_history@v1` rules.** Over the last 252 sessions (today included) of `iv30@v1.iv30`
(`source = "cboe"` switches to the feed's): rank `(iv - min) / (max - min)` (null when flat),
percentile = share of earlier IVs strictly below today's, `history_days` = sessions with an IV.
`rank_status` is UNKNOWN below 60 sessions (rank and percentile null), PROVISIONAL below 252,
FULL from 252 (owner decision). History starts with the first stored chain: nothing is
back-filled from before chains were collected. `iv_hv_spread = iv30 - hv30` and
`iv_hv_ratio = iv30 / hv30` (`price_stats@v1`) are the variance-risk-premium inputs.

**`liquidity_class@v1` rules.** HIGH when every HIGH threshold holds (ADV, close, the worse
of the put / call option tier, chain open interest and volume), else MEDIUM when every MEDIUM
one does, else LOW. A threshold that cannot be checked (null ADV; no `option_liquidity@v1`
for the session; a failed chain fetch) is unknown, and the class is UNKNOWN unless it is
decided without it (three-valued logic). An instrument not in the session's chain run has no
options. `rule_hash` is the first 12 hex characters of the SHA-256 of the thresholds.

**`earnings@v1` rules.** The earnings task stores, each session, the calendar for the days
ahead. For each report date the authority is the latest snapshot on or before the session
whose range covers it (from its session, or its earliest row, to its latest row): a date a
later snapshot no longer lists was moved or cancelled. `days_to_earnings` is 0 on the report
day and counts sessions (`core/time/calendar.py`). Sessions before the first stored snapshot
have no row (UNKNOWN); a backfill does not invent what was not stored then.
