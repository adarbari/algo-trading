# Feature catalogue

Generated from `src/algotrade/features/registry.py` by `make features-doc`; do not edit by
hand (a fitness test fails when it is out of date). The model is in
[ADR 0023](../adr/0023-feature-store.md); how groups are computed and stored is in
[layers.md](layers.md#rollups-as-built).

A feature is `<group>.<column>@v<N>`, selectable as `rollup.<group>@v<N>.<column>`. Null is
UNKNOWN, never zero: "Null when" says why a value can be missing. Valid values are a sanity
range (values outside are kept, not clipped) or a label's categories. Units: `decimal` is a
fraction (0.25 = 25%), `pct_points` a quoted percentage (25 = 25%), `sessions` exchange
sessions, `days` calendar days.

87 features in 8 groups, in dependency order.

## `option_liquidity@v1`

Short-premium tradeability tiers (A-D) for puts and calls at the target expiry. Stored as `rollups/instrument/option_liquidity@v1`; reads `chains/status`, `chains/option_quotes` (optional), `chains/underlying_quotes` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `liq_status` | label | str | category |  | OK, NO_STANDARD_SERIES, NO_TARGET_EXPIRY, or the chain fetch status when it failed (NO_CHAIN, STALE_DATA: ..., FETCH_ERROR, NOT_ATTEMPTED) | never | `chains/status.status`, `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `chain_oi` | chain | int | count | >= 0 | Open interest across every standard-series contract | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.open_interest` |
| `chain_volume` | chain | int | count | >= 0 | Volume across every standard-series contract | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.volume` |
| `expiries_within_60d` | chain | int | count | >= 0 | Listed expiries 0..60 calendar days out | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.expiry` |
| `target_expiry` | chain | date | date |  | The standard monthly closest to 35 days within 21..60 days, else any expiry in that window, else any at least 14 days out | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry` |
| `target_dte` | chain | int | days | >= 0 | Calendar days from the session to the target expiry | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry` |
| `short_put_ok` | expression | bool | flag |  | put_tier is one of the OK tiers (A, B) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `option_liquidity.put_tier@v1` |
| `short_call_ok` | expression | bool | flag |  | call_tier is one of the OK tiers (A, B) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `option_liquidity.call_tier@v1` |
| `underlying_price` | chain | float | usd_per_share | >= 0 | The underlying's price captured with the chain | no underlying quote captured with the session's chain | `chains/underlying_quotes.price` |
| `iv30` | chain | float | pct_points | 0 .. 500 | The feed's 30-day implied volatility as quoted (a percentage: 25.3 is 25.3%) | no underlying quote captured with the session's chain | `chains/underlying_quotes.iv30` |
| `stock_volume` | chain | float | shares | >= 0 | The underlying's share volume, from the feed | no underlying quote captured with the session's chain | `chains/underlying_quotes.volume` |
| `chain_asof` | chain | date | date |  | When the feed's chain snapshot was taken | no underlying quote captured with the session's chain | `chains/underlying_quotes.ts` |
| `put_tier` | label | str | category | A, B, C, D | Short-put tier: the first of A..C whose spread, zone OI, chain OI and bid limits the short strike meets, else D (not tradeable) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_strike` | chain | float | usd_per_share | >= 0 | The short put strike: tightest relative spread with 0.20 <= \|delta\| <= 0.40 (ties: higher OI), else the two-sided quote nearest \|delta\| 0.30 | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest` |
| `put_delta` | chain | float | ratio | -1 .. 0 | The short strike's delta (the feed's, 3 places) | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `put_bid` | chain | float | usd_per_share | >= 0 | The short strike's bid | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid` |
| `put_ask` | chain | float | usd_per_share | >= 0 | The short strike's ask | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.ask` |
| `put_spread_abs` | chain | float | usd_per_share | >= 0 | ask - bid at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `put_spread_pct` | chain | float | decimal | 0 .. 2 | (ask - bid) / mid at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `put_strike_oi` | chain | int | count | >= 0 | Open interest at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.open_interest` |
| `put_zone_oi` | chain | int | count | >= 0 | Open interest of the target expiry's puts with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_zone_vol` | chain | int | count | >= 0 | Volume of the target expiry's puts with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_missing_delta` | chain | int | count | >= 0 | The target expiry's puts without a delta (counted, not dropped) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `call_tier` | label | str | category | A, B, C, D | Short-call tier: the first of A..C whose spread, zone OI, chain OI and bid limits the short strike meets, else D (not tradeable) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_strike` | chain | float | usd_per_share | >= 0 | The short call strike: tightest relative spread with 0.20 <= \|delta\| <= 0.40 (ties: higher OI), else the two-sided quote nearest \|delta\| 0.30 | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest` |
| `call_delta` | chain | float | ratio | 0 .. 1 | The short strike's delta (the feed's, 3 places) | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `call_bid` | chain | float | usd_per_share | >= 0 | The short strike's bid | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid` |
| `call_ask` | chain | float | usd_per_share | >= 0 | The short strike's ask | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.ask` |
| `call_spread_abs` | chain | float | usd_per_share | >= 0 | ask - bid at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `call_spread_pct` | chain | float | decimal | 0 .. 2 | (ask - bid) / mid at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `call_strike_oi` | chain | int | count | >= 0 | Open interest at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.open_interest` |
| `call_zone_oi` | chain | int | count | >= 0 | Open interest of the target expiry's calls with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_zone_vol` | chain | int | count | >= 0 | Volume of the target expiry's calls with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_missing_delta` | chain | int | count | >= 0 | The target expiry's calls without a delta (counted, not dropped) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |

## `price_stats@v1`

Close, moving averages, returns, 52-week range, realised vol and dollar volume. Stored as `rollups/instrument/price_stats@v1`; reads `bars/1d`.

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `close` | window | float | usd_per_share | >= 0 | The session's close, split-adjusted as of the session | never: a row exists only for an instrument with a bar on the session | `bars/1d.close` |
| `sma_20` | window | float | usd_per_share | >= 0 | Mean close over the last 20 sessions | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `sma_50` | window | float | usd_per_share | >= 0 | Mean close over the last 50 sessions | a session among the last 50 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `sma_200` | window | float | usd_per_share | >= 0 | Mean close over the last 200 sessions | a session among the last 200 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `ret_20d` | window | float | decimal | >= -1 | Close / close 20 sessions earlier - 1 | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `ret_60d` | window | float | decimal | >= -1 | Close / close 60 sessions earlier - 1 | a session among the last 61 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `high_52w` | window | float | usd_per_share | >= 0 | Highest daily high over the last 52 weeks (252 sessions) | fewer than min_year_sessions (240) bars among the last year_sessions (252) | `bars/1d.high` |
| `low_52w` | window | float | usd_per_share | >= 0 | Lowest daily low over the last 52 weeks (252 sessions) | fewer than min_year_sessions (240) bars among the last year_sessions (252) | `bars/1d.low` |
| `pct_from_high_52w` | expression | float | decimal | -1 .. 0 | Close / 52-week high - 1 (at or below 0) | high_52w is null | `price_stats.close@v1`, `price_stats.high_52w@v1` |
| `pct_from_low_52w` | expression | float | decimal | >= 0 | Close / 52-week low - 1 (at or above 0) | low_52w is null | `price_stats.close@v1`, `price_stats.low_52w@v1` |
| `hv20` | window | float | decimal | 0 .. 5 | Close-to-close realised volatility over 20 sessions, annualised (252) | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `hv30` | window | float | decimal | 0 .. 5 | Close-to-close realised volatility over 30 sessions, annualised (252) | a session among the last 31 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `hv20_yz` | window | float | decimal | 0 .. 5 | Yang-Zhang realised volatility over 20 sessions, annualised (252) | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.open`, `bars/1d.high`, `bars/1d.low`, `bars/1d.close` |
| `adv_usd_20d` | window | float | usd | >= 0 | Mean daily dollar volume (close x volume) over 20 sessions | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.close`, `bars/1d.volume` |
| `history_days` | window | int | sessions | >= 1 | Sessions with a bar among the last year_sessions (252), the session included | never | `bars/1d.close` |

## `earnings@v1`

Next and last earnings dates, report time and sessions to the next report. Stored as `rollups/instrument/earnings@v1`; reads `events/earnings`.

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `next_earnings_date` | window | date | date |  | The first report date on or after the session, as known on the session | no report date on or after the session in the calendars stored by then (the row exists for a last date) | `events/earnings.ts` |
| `earnings_time` | label | str | category | pre, post, unknown | When the next report is due: pre (before the open), post (after the close), unknown | no report date on or after the session in the calendars stored by then | `events/earnings.time` |
| `days_to_earnings` | window | int | sessions | >= 0 | Exchange sessions after the session up to the next report date (0: reports today) | no report date on or after the session in the calendars stored by then | `events/earnings.ts` |
| `date_confirmed` | window | bool | flag |  | Whether the source confirmed the next report date | the source does not say (the Nasdaq calendar never does), or no report date on or after the session in the calendars stored by then | `events/earnings.date_confirmed` |
| `last_earnings_date` | window | date | date |  | The latest report date before the session | no earlier report date in the calendars stored by then (they start with the first stored snapshot; a backfill does not invent history) | `events/earnings.ts` |

## `dividends@v1`

Trailing-12-month cash dividends (split-adjusted to the session) and dividend yield. Stored as `rollups/instrument/dividends@v1`; reads `rollups/instrument/price_stats@v1`, `events/dividend` (optional), `events/split` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `div_ttm` | window | float | usd_per_share | >= 0 | Cash dividends with ex-date in the last 365 days, split-adjusted to the session's share terms (specials excluded); 0 for a known non-payer | no dividend in the window and fewer than min_history_days (240) bars among the last 252 sessions (too new, or bars do not cover the window, to call it a non-payer) | `events/dividend.cash_amount`, `events/dividend.ts`, `events/split.ratio` |
| `div_yield` | expression | float | decimal | 0 .. 1 | Trailing dividend yield: div_ttm / close; the continuous q in option pricing | no dividend in the window and fewer than min_history_days (240) bars among the last 252 sessions (too new, or bars do not cover the window, to call it a non-payer); or the close is not positive | `dividends.div_ttm@v1`, `price_stats.close@v1` |
| `div_count_ttm` | window | int | count | >= 0 | Ex-dates in the last 365 days | no dividend in the window and fewer than min_history_days (240) bars among the last 252 sessions (too new, or bars do not cover the window, to call it a non-payer) | `events/dividend.ts` |
| `last_ex_date` | window | date | date |  | The latest ex-date in the last 365 days | no ex-date in the window (a non-payer, or unknown as for div_ttm) | `events/dividend.ts` |

## `liquidity_class@v1`

HIGH / MEDIUM / LOW liquidity from dollar volume, price and option liquidity thresholds. Stored as `rollups/instrument/liquidity_class@v1`; reads `rollups/instrument/price_stats@v1`, `rollups/instrument/option_liquidity@v1` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `liquidity_class` | label | str | category | HIGH, MEDIUM, LOW, UNKNOWN | HIGH when every HIGH threshold holds (ADV, close, worse option tier, chain OI and volume; rollups.toml), else MEDIUM when every MEDIUM one does, else LOW; UNKNOWN when an unknown threshold decides it | never | `price_stats.adv_usd_20d@v1`, `price_stats.close@v1`, `option_liquidity.put_tier@v1`, `option_liquidity.call_tier@v1`, `option_liquidity.chain_oi@v1`, `option_liquidity.liq_status@v1`, `option_liquidity.chain_volume@v1` |
| `adv_usd_20d` | expression | float | usd | >= 0 | price_stats@v1 adv_usd_20d, as classified | price_stats@v1 adv_usd_20d is null (a gap in the last 20 sessions) | `price_stats.adv_usd_20d@v1` |
| `close` | expression | float | usd_per_share | >= 0 | price_stats@v1 close, as classified | never: a row exists for each price_stats@v1 row | `price_stats.close@v1` |
| `option_tier` | expression | str | category | A, B, C, D | The worse of the put and call tier (option_liquidity@v1); D: no usable options, also for an instrument the session's chain run did not list | unknown: no option_liquidity@v1 for the session, or its chain fetch failed (STALE_DATA, FETCH_ERROR, NOT_ATTEMPTED) | `option_liquidity.put_tier@v1`, `option_liquidity.call_tier@v1`, `option_liquidity.chain_oi@v1`, `option_liquidity.liq_status@v1` |
| `chain_oi` | expression | int | count | >= 0 | Chain open interest from option_liquidity@v1 (0 when the chain run did not list it) | unknown: no option_liquidity@v1 for the session, or its chain fetch failed (STALE_DATA, FETCH_ERROR, NOT_ATTEMPTED) | `option_liquidity.put_tier@v1`, `option_liquidity.call_tier@v1`, `option_liquidity.chain_oi@v1`, `option_liquidity.liq_status@v1` |
| `rule_hash` | label | str | text |  | The first 12 hex characters of the SHA-256 of the thresholds: which rule made the row | never |  |

## `fundamentals@v1`

Shares outstanding (SEC company facts, point in time by filing date) and market cap. Stored as `rollups/instrument/fundamentals@v1`; reads `rollups/instrument/price_stats@v1`, `instruments/shares` (optional), `events/split` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `shares_outstanding` | window | float | shares | >= 0 | Shares outstanding (company total of every class), split-adjusted to the session: the latest cover-page count (dei) while the company tags it, else the latest weighted average basic | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.shares`, `instruments/shares.concept`, `instruments/shares.filed`, `instruments/shares.period_end`, `events/split.ratio` |
| `shares_as_of` | window | date | date |  | The count's period end (the cover date, or the end of the averaged period) | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.period_end` |
| `shares_filed` | window | date | date |  | The filing date that made the count public | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.filed` |
| `shares_source` | label | str | category | dei, weighted_basic | Which count: dei (cover page) or weighted_basic (weighted average basic) | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.concept` |
| `market_cap` | expression | float | usd | >= 0 | shares_outstanding x close (the company total times this class's close) | market_cap_status is not OK | `fundamentals.shares_outstanding@v1`, `price_stats.close@v1` |
| `market_cap_status` | label | str | category | OK, NO_SHARES, STALE, NO_PRICE | OK; NO_SHARES (no count); STALE (period end more than stale_days, 400, before the session; the count is still shown); NO_PRICE (no close) | never | `fundamentals.shares_outstanding@v1`, `price_stats.close@v1` |

## `iv30@v1`

Our 30-day ATM implied vol (forward ATM, put/call mid IVs, total-variance term interpolation) beside Cboe's, with a status code. Stored as `rollups/instrument/iv30@v1`; reads `chains/option_quotes`, `rates/treasury`, `chains/underlying_quotes` (optional), `rollups/instrument/dividends@v1` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `iv30` | chain | float | decimal | 0 .. 5 | Our 30-calendar-day at-the-money implied volatility: forward ATM vols of the two expiries around 30 days, interpolated in total variance (ADR 0021) | iv30_status is neither OK nor SINGLE_EXPIRY (the status says why) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `dividends.div_yield@v1` |
| `iv30_cboe` | chain | float | decimal | 0 .. 5 | The feed's 30-day implied volatility, as a decimal | no underlying quote for it, or the feed gives no IV30 | `chains/underlying_quotes.iv30` |
| `iv30_status` | label | str | category | OK, SINGLE_EXPIRY, NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_QUOTES, WIDE_SPREADS, ILLIQUID, IV_FAILED | Why iv30 has a value or not; the first failing step wins (SINGLE_EXPIRY: one usable expiry, flat vol, still a value) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `near_expiry` | chain | date | date |  | The selected expiry at or before 30 days out (standard monthlies first, 7..90 days) | no expiry in 7..90 days at or before the target, or no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `far_expiry` | chain | date | date |  | The selected expiry at or after 30 days out (standard monthlies first, 7..90 days) | no expiry in 7..90 days at or after the target, or no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `atm_strike_near` | chain | float | usd_per_share | >= 0 | The listed strike nearest the forward in the near expiry (the far one without a near) | no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.strike`, `chains/underlying_quotes.price` |
| `spot` | chain | float | usd_per_share | >= 0 | The underlying's price captured with the chain | no positive underlying price (NO_SPOT) | `chains/underlying_quotes.price` |
| `rate` | chain | float | decimal | -0.05 .. 0.25 | Continuous risk-free rate at 30 days, from the Treasury curve the session sees | never (the curve is a required input) | `rates/treasury.rate_cont` |
| `div_yield` | expression | float | decimal | 0 .. 1 | The dividend yield q used for the forward, as read from dividends@v1 | dividends@v1 has no yield for it (UNKNOWN; priced with q = 0) | `dividends.div_yield@v1` |
| `n_quotes_used` | chain | int | count | >= 0 | Option quotes whose implied vols were averaged, across both expiries | never (0 when none) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest` |

## `iv_history@v1`

IV30 rank and percentile over 252 sessions (provisional after 60) and IV minus HV30. Stored as `rollups/instrument/iv_history@v1`; reads `rollups/instrument/iv30@v1`, `rollups/instrument/price_stats@v1` (optional).

| Feature | Kind | Type | Unit | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|
| `iv30` | expression | float | decimal | 0 .. 5 | The session's IV30 from iv30@v1 (ours; the feed's with source = cboe) | iv30@v1 has no IV for the session (its iv30_status says why) | `iv30.iv30@v1`, `iv30.iv30_cboe@v1` |
| `iv_rank_252d` | window | float | decimal | 0 .. 1 | IV rank: (iv30 - min) / (max - min) over the last 252 sessions' IVs, today included | rank_status is UNKNOWN (fewer than 60 sessions with an IV), or there is no IV today; or every IV in the window is equal | `iv30.iv30@v1` |
| `iv_percentile_252d` | window | float | decimal | 0 .. 1 | IV percentile: the share of the window's earlier IVs strictly below today's | rank_status is UNKNOWN (fewer than 60 sessions with an IV), or there is no IV today; or no earlier IV | `iv30.iv30@v1` |
| `history_days` | window | int | sessions | >= 0 | Sessions of the 252-session window with an IV, today included (gaps are not filled) | never | `iv30.iv30@v1` |
| `rank_status` | label | str | category | UNKNOWN, PROVISIONAL, FULL | UNKNOWN below 60 sessions with an IV (no rank), PROVISIONAL below 252, FULL from 252 | never | `iv30.iv30@v1` |
| `iv_hv_spread` | expression | float | decimal | -5 .. 5 | iv30 - hv30 (price_stats@v1): the variance risk premium's raw input | iv30 or hv30 is null | `iv_history.iv30@v1`, `price_stats.hv30@v1` |
| `iv_hv_ratio` | expression | float | ratio | >= 0 | iv30 / hv30 (price_stats@v1) | iv30 or hv30 is null, or hv30 is 0 | `iv_history.iv30@v1`, `price_stats.hv30@v1` |
