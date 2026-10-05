# Feature catalogue

Generated from `src/algotrade/features/registry.py` (code groups) and
`config/site/features/*.toml` (expression features) by `make features-doc`; do not edit by
hand (a fitness test fails when it is out of date). The model is in
[ADR 0023](../adr/0023-feature-store.md); how groups are computed and stored is in
[layers.md](layers.md#rollups-as-built); the expression language is in
[configuration.md](../configuration.md#expression-features).

A group feature is `<group>.<column>@v<N>`, selectable as `rollup.<group>@v<N>.<column>`; an
expression feature is `<name>@v<N>`, selectable as `feature.<name>` and computed on read from
the stored features it names (unless materialised). Null is UNKNOWN, never zero: "Null when"
says why a value can be missing. Valid values are a sanity range or a label's categories:
values outside a range are kept, never clipped, and are reported by the feature-quality
checks (ADR 0023, step 7). Units: `decimal` is a fraction (0.25 = 25%), `pct_points` a
quoted percentage (25 = 25%), `sessions` exchange sessions, `days` calendar days. Types:
`float32` is a 32-bit float (about 7 significant digits). Licence: `open` (computed by us
from free data) or `personal` (derived from IBKR market data, a personal-use licence: the API
will show it to the owner only once there are other users;
[ADR 0028](../adr/0028-ibkr-enrichment-source.md)); an expression feature takes the most
restrictive licence of its inputs.

129 stored features in 15 groups, in dependency order; 36 expression features.

## `option_liquidity@v1`

Short-premium tradeability tiers (A-D) for puts and calls at the target expiry. Stored as `rollups/instrument/option_liquidity@v1`; reads `chains/status`, `chains/option_quotes` (optional), `chains/underlying_quotes` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `liq_status` | label | str | category | open |  | OK, NO_STANDARD_SERIES, NO_TARGET_EXPIRY, or the chain fetch status when it failed (NO_CHAIN, STALE_DATA: ..., FETCH_ERROR, NOT_ATTEMPTED) | never | `chains/status.status`, `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `chain_oi` | chain | int | count | open | >= 0 | Open interest across every standard-series contract | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.open_interest` |
| `chain_volume` | chain | int | count | open | >= 0 | Volume across every standard-series contract | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.volume` |
| `expiries_within_60d` | chain | int | count | open | >= 0 | Listed expiries 0..60 calendar days out | no standard-series contracts (NO_STANDARD_SERIES), or the chain fetch failed | `chains/option_quotes.expiry` |
| `target_expiry` | chain | date | date | open |  | The standard monthly closest to 35 days within 21..60 days, else any expiry in that window, else any at least 14 days out | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry` |
| `target_dte` | chain | int | days | open | >= 0 | Calendar days from the session to the target expiry | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry` |
| `short_put_ok` | expression | bool | flag | open |  | put_tier is one of the OK tiers (A, B) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `option_liquidity.put_tier@v1` |
| `short_call_ok` | expression | bool | flag | open |  | call_tier is one of the OK tiers (A, B) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `option_liquidity.call_tier@v1` |
| `underlying_price` | chain | float | usd_per_share | open | >= 0 | The underlying's price captured with the chain | no underlying quote captured with the session's chain | `chains/underlying_quotes.price` |
| `iv30` | chain | float | pct_points | open | 0 .. 500 | The feed's 30-day implied volatility as quoted (a percentage: 25.3 is 25.3%) | no underlying quote captured with the session's chain | `chains/underlying_quotes.iv30` |
| `stock_volume` | chain | float | shares | open | >= 0 | The underlying's share volume, from the feed | no underlying quote captured with the session's chain | `chains/underlying_quotes.volume` |
| `chain_asof` | chain | date | date | open |  | When the feed's chain snapshot was taken | no underlying quote captured with the session's chain | `chains/underlying_quotes.ts` |
| `put_tier` | label | str | category | open | A, B, C, D | Short-put tier: the first of A..C whose spread, zone OI, chain OI and bid limits the short strike meets, else D (not tradeable) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_strike` | chain | float | usd_per_share | open | >= 0 | The short put strike: tightest relative spread with 0.20 <= \|delta\| <= 0.40 (ties: higher OI), else the two-sided quote nearest \|delta\| 0.30 | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest` |
| `put_delta` | chain | float | ratio | open | -1 .. 0 | The short strike's delta (the feed's, 3 places) | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `put_bid` | chain | float | usd_per_share | open | >= 0 | The short strike's bid | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid` |
| `put_ask` | chain | float | usd_per_share | open | >= 0 | The short strike's ask | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.ask` |
| `put_spread_abs` | chain | float | usd_per_share | open | >= 0 | ask - bid at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `put_spread_pct` | chain | float | decimal | open | 0 .. 2 | (ask - bid) / mid at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `put_strike_oi` | chain | int | count | open | >= 0 | Open interest at the short strike | no two-sided put quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.open_interest` |
| `put_zone_oi` | chain | int | count | open | >= 0 | Open interest of the target expiry's puts with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_zone_vol` | chain | int | count | open | >= 0 | Volume of the target expiry's puts with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `put_missing_delta` | chain | int | count | open | >= 0 | The target expiry's puts without a delta (counted, not dropped) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `call_tier` | label | str | category | open | A, B, C, D | Short-call tier: the first of A..C whose spread, zone OI, chain OI and bid limits the short strike meets, else D (not tradeable) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_strike` | chain | float | usd_per_share | open | >= 0 | The short call strike: tightest relative spread with 0.20 <= \|delta\| <= 0.40 (ties: higher OI), else the two-sided quote nearest \|delta\| 0.30 | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.delta`, `chains/option_quotes.strike`, `chains/option_quotes.open_interest` |
| `call_delta` | chain | float | ratio | open | 0 .. 1 | The short strike's delta (the feed's, 3 places) | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |
| `call_bid` | chain | float | usd_per_share | open | >= 0 | The short strike's bid | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid` |
| `call_ask` | chain | float | usd_per_share | open | >= 0 | The short strike's ask | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.ask` |
| `call_spread_abs` | chain | float | usd_per_share | open | >= 0 | ask - bid at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `call_spread_pct` | chain | float | decimal | open | 0 .. 2 | (ask - bid) / mid at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `call_strike_oi` | chain | int | count | open | >= 0 | Open interest at the short strike | no two-sided call quote with a delta at the target expiry; or no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.open_interest` |
| `call_zone_oi` | chain | int | count | open | >= 0 | Open interest of the target expiry's calls with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_zone_vol` | chain | int | count | open | >= 0 | Volume of the target expiry's calls with 0.15 <= \|delta\| <= 0.40 | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.expiry`, `chains/option_quotes.strike`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/option_quotes.volume` |
| `call_missing_delta` | chain | int | count | open | >= 0 | The target expiry's calls without a delta (counted, not dropped) | no target expiry (NO_TARGET_EXPIRY), no standard series, or the fetch failed | `chains/option_quotes.delta` |

## `price_stats@v2`

Close, moving averages, returns, 52-week range, realised vol and dollar volume. Stored as `rollups/instrument/price_stats@v2`; reads `bars/1d`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `close` | window | float32 | usd_per_share | open | >= 0 | The session's close, split-adjusted as of the session | never: a row exists only for an instrument with a bar on the session | `bars/1d.close` |
| `sma_20` | window | float32 | usd_per_share | open | >= 0 | Mean close over the last 20 sessions | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `sma_50` | window | float32 | usd_per_share | open | >= 0 | Mean close over the last 50 sessions | a session among the last 50 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `sma_200` | window | float32 | usd_per_share | open | >= 0 | Mean close over the last 200 sessions | a session among the last 200 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `ret_20d` | window | float32 | decimal | open | >= -1 | Close / close 20 sessions earlier - 1 | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `ret_60d` | window | float32 | decimal | open | >= -1 | Close / close 60 sessions earlier - 1 | a session among the last 61 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `high_52w` | window | float32 | usd_per_share | open | >= 0 | Highest daily high over the last 52 weeks (252 sessions), split-adjusted (not dividend-adjusted) | fewer than min_year_sessions (240) bars among the last year_sessions (252) | `bars/1d.high` |
| `low_52w` | window | float32 | usd_per_share | open | >= 0 | Lowest daily low over the last 52 weeks (252 sessions), split-adjusted (not dividend-adjusted) | fewer than min_year_sessions (240) bars among the last year_sessions (252) | `bars/1d.low` |
| `hv20` | window | float32 | decimal | open | 0 .. 5 | Close-to-close realised volatility: sample stdev of the last 20 log returns x sqrt(252) | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `hv30` | window | float32 | decimal | open | 0 .. 5 | Close-to-close realised volatility: sample stdev of the last 30 log returns x sqrt(252) | a session among the last 31 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `hv20_yz` | window | float32 | decimal | open | 0 .. 5 | Yang-Zhang realised volatility over 20 sessions, annualised (252) | a session among the last 21 has no bar (a gap), or the history is shorter | `bars/1d.open`, `bars/1d.high`, `bars/1d.low`, `bars/1d.close` |
| `adv_usd_20d` | window | float32 | usd | open | >= 0 | Mean daily dollar volume (close x volume) over 20 sessions | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.close`, `bars/1d.volume` |
| `history_days` | window | int | sessions | open | >= 1 | Sessions with a bar among the last year_sessions (252), the session included | never | `bars/1d.close` |

## `earnings@v1`

Next and last earnings dates, report time and sessions to the next report. Stored as `rollups/instrument/earnings@v1`; reads `events/earnings`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `next_earnings_date` | window | date | date | open |  | The first report date on or after the session, as known on the session | no report date on or after the session in the calendars stored by then (the row exists for a last date) | `events/earnings.ts` |
| `earnings_time` | label | str | category | open | pre, post, unknown | When the next report is due: pre (before the open), post (after the close), unknown | no report date on or after the session in the calendars stored by then | `events/earnings.time` |
| `days_to_earnings` | window | int | sessions | open | >= 0 | Exchange sessions after the session up to the next report date (0: reports today) | no report date on or after the session in the calendars stored by then | `events/earnings.ts` |
| `date_confirmed` | window | bool | flag | open |  | Whether the source confirmed the next report date | the source does not say (the Nasdaq calendar never does), or no report date on or after the session in the calendars stored by then | `events/earnings.date_confirmed` |
| `last_earnings_date` | window | date | date | open |  | The latest report date before the session | no earlier report date in the calendars stored by then (they start with the first stored snapshot; a backfill does not invent history) | `events/earnings.ts` |

## `ibkr_iv@v1`

IBKR's IV30 and HV30, and the IV rank and percentile over 252 sessions of IBKR's IV (provisional after 60; personal-use licence). Stored as `rollups/instrument/ibkr_iv@v1`; reads `volatility/ibkr_iv30`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `iv30_ibkr` | window | float32 | decimal | personal | 0 .. 5 | IBKR's 30-day implied vol of the underlying's options for the session (IB's daily OPTION_IMPLIED_VOLATILITY bar, or the streamed tick 106 after the close) | IBKR had no implied vol for the underlying (no listed options, no quotes) | `volatility/ibkr_iv30.iv30_ibkr` |
| `hv30_ibkr` | window | float32 | decimal | personal | 0 .. 5 | IBKR's 30-day historical (realised) vol of the underlying for the session | IBKR had no historical vol for the session | `volatility/ibkr_iv30.hv30_ibkr` |
| `iv_rank_252d_ibkr` | window | float32 | decimal | personal | 0 .. 1 | IV rank on IBKR's IV: (iv - min) / (max - min) over the last 252 sessions, today included | rank_status_ibkr is UNKNOWN (fewer than 60 sessions with an IBKR IV), or IBKR has no IV for the session; or every IV in the window is equal | `volatility/ibkr_iv30.iv30_ibkr` |
| `iv_percentile_252d_ibkr` | window | float32 | decimal | personal | 0 .. 1 | IV percentile on IBKR's IV: the share of the window's earlier IVs strictly below today's | rank_status_ibkr is UNKNOWN (fewer than 60 sessions with an IBKR IV), or IBKR has no IV for the session; or no earlier IV | `volatility/ibkr_iv30.iv30_ibkr` |
| `history_days_ibkr` | window | int | sessions | personal | >= 0 | Sessions of the 252-session window with an IBKR IV, today included (gaps are not filled) | never | `volatility/ibkr_iv30.iv30_ibkr` |
| `rank_status_ibkr` | label | str | category | personal | UNKNOWN, PROVISIONAL, FULL | UNKNOWN below 60 sessions with an IBKR IV (no rank), PROVISIONAL below 252, FULL from 252 | never | `volatility/ibkr_iv30.iv30_ibkr` |

## `price_moves@v1`

The largest one-day close-to-close move over the last 20 sessions. Stored as `rollups/instrument/price_moves@v1`; reads `bars/1d`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `one_day_move` | window | float32 | decimal | open | >= 0 | Largest absolute one-day close-to-close return over the last 20 sessions (split-adjusted as of the session): 0.12 is a 12% move up or down | a session among the last 21 has no close (a gap), or the history is shorter | `bars/1d.close` |

## `momentum@v1`

Wilder ATR and RSI (14), 5-session return, relative volume and the 20 / 50-session high-low channel. Stored as `rollups/instrument/momentum@v1`; reads `bars/1d`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `atr_14` | window | float32 | usd_per_share | open | >= 0 | Wilder average true range (14): seeded with the mean of the first 14 true ranges, then (13 x ATR + TR) / 14, over the consecutive bars ending on the session (at most the last 150 sessions); TR = max(high - low, \|high - previous close\|, \|low - previous close\|) | fewer than 15 consecutive bars ending on the session (a gap among the last 15 sessions, or a shorter history) | `bars/1d.high`, `bars/1d.low`, `bars/1d.close` |
| `rsi_14` | window | float32 | pct_points | open | 0 .. 100 | Wilder RSI (14) of close changes over the same run as atr_14: 100 - 100 / (1 + average gain / average loss); 100 when there was no loss | fewer than 15 consecutive bars ending on the session (a gap among the last 15 sessions, or a shorter history); or the close never moved over the run (no gain and no loss: 0/0) | `bars/1d.close` |
| `ret_5d` | window | float32 | decimal | open | >= -1 | Close / close 5 sessions earlier - 1 | a session among the last 6 has no bar (a gap), or the history is shorter | `bars/1d.close` |
| `rel_volume` | window | float32 | ratio | open | >= 0 | The session's volume / the mean volume of the 20 sessions before it (the session excluded): 1.8 is 80% above normal; 0 on a day without trades | a session among the last 21 has no bar (a gap), or the history is shorter; or those 20 sessions had no volume at all | `bars/1d.volume` |
| `high_20d` | window | float32 | usd_per_share | open | >= 0 | Highest daily high over the last 20 sessions, the session included | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.high` |
| `low_20d` | window | float32 | usd_per_share | open | >= 0 | Lowest daily low over the last 20 sessions, the session included | a session among the last 20 has no bar (a gap), or the history is shorter | `bars/1d.low` |
| `high_50d` | window | float32 | usd_per_share | open | >= 0 | Highest daily high over the last 50 sessions, the session included | a session among the last 50 has no bar (a gap), or the history is shorter | `bars/1d.high` |
| `low_50d` | window | float32 | usd_per_share | open | >= 0 | Lowest daily low over the last 50 sessions, the session included | a session among the last 50 has no bar (a gap), or the history is shorter | `bars/1d.low` |
| `prior_high_20d` | window | float32 | usd_per_share | open | >= 0 | Highest daily high over the 20 sessions before the session (the session excluded): the level a breakout close must clear | a session among the 20 before the session has no bar (a gap), or the history is shorter | `bars/1d.high` |

## `swing_levels@v1`

Resistance and support: the most recent confirmed swing high above and swing low below the close (5 bars each side, last 252 sessions). Stored as `rollups/instrument/swing_levels@v1`; reads `bars/1d`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `swing_high` | window | float32 | usd_per_share | open | >= 0 | Resistance: the high of the most recent swing high above the close (a bar whose high is strictly above the 5 highs before it and at least the 5 after it, confirmed 5 sessions later) | no confirmed swing high above the close among the last 252 sessions (e.g. the close is at a 252-session high), or fewer than 11 bars in a row | `bars/1d.high`, `bars/1d.close` |
| `swing_high_date` | window | date | date | open |  | The session of that swing high | no confirmed swing high above the close among the last 252 sessions (e.g. the close is at a 252-session high), or fewer than 11 bars in a row | `bars/1d.high`, `bars/1d.close` |
| `swing_low` | window | float32 | usd_per_share | open | >= 0 | Support: the low of the most recent swing low below the close (a bar whose low is strictly below the 5 lows before it and at most the 5 after it, confirmed 5 sessions later) | no confirmed swing low below the close among the last 252 sessions (e.g. the close is at a 252-session low), or fewer than 11 bars in a row | `bars/1d.low`, `bars/1d.close` |
| `swing_low_date` | window | date | date | open |  | The session of that swing low | no confirmed swing low below the close among the last 252 sessions (e.g. the close is at a 252-session low), or fewer than 11 bars in a row | `bars/1d.low`, `bars/1d.close` |

## `anchored_vwap@v1`

VWAP anchored to the last earnings report (from the reaction session through the session). Stored as `rollups/instrument/anchored_vwap@v1`; reads `events/earnings`, `bars/1d`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `avwap_earnings` | window | float32 | usd_per_share | open | >= 0 | Volume-weighted average of the typical price (high + low + close) / 3 from the last earnings anchor session through the session (the anchor: the report date, or the next session for a report after the close) | no report known on the session anchors on or before it within the last 126 sessions (no earlier report stored, or the last one is older); or fewer than 2 sessions from the anchor through the session, a session in that range without a bar, or no volume in it | `events/earnings.ts`, `events/earnings.time`, `bars/1d.high`, `bars/1d.low`, `bars/1d.close`, `bars/1d.volume` |
| `avwap_anchor_date` | window | date | date | open |  | The session avwap_earnings is anchored on: the last report date (pre-market or unknown time) or the session after it (after the close) | no report known on the session anchors on or before it within the last 126 sessions (no earlier report stored, or the last one is older) | `events/earnings.ts`, `events/earnings.time` |

## `oi_walls@v1`

Call and put walls: the strikes with the most open interest at or above / at or below spot, summed across expiries 1..60 days out (end-of-day OI). Stored as `rollups/instrument/oi_walls@v1`; reads `chains/option_quotes`, `chains/underlying_quotes` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `wall_status` | label | str | category | open | OK, PARTIAL, NO_OI, NO_SPOT, NO_CHAIN, NO_EXPIRY | OK (both walls), PARTIAL (one wall), NO_OI (no open interest on either side), or the first failing step: NO_SPOT, NO_CHAIN (no quotes), NO_EXPIRY (none 1..60 days out) | never | `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `call_wall` | chain | float32 | usd_per_share | open | >= 0 | Call wall: the strike at or above spot with the most call open interest, summed across expiries 1..60 calendar days out (end-of-day OI; ties: nearer spot) | no call with open interest above 0 at a strike at or above spot 1..60 days out, or wall_status NO_SPOT, NO_CHAIN or NO_EXPIRY | `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `call_wall_oi` | chain | int | count | open | >= 1 | Call open interest at the call wall, summed across expiries 1..60 days out | no call with open interest above 0 at a strike at or above spot 1..60 days out, or wall_status NO_SPOT, NO_CHAIN or NO_EXPIRY | `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `put_wall` | chain | float32 | usd_per_share | open | >= 0 | Put wall: the strike at or below spot with the most put open interest, summed across expiries 1..60 calendar days out (end-of-day OI; ties: nearer spot) | no put with open interest above 0 at a strike at or below spot 1..60 days out, or wall_status NO_SPOT, NO_CHAIN or NO_EXPIRY | `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `put_wall_oi` | chain | int | count | open | >= 1 | Put open interest at the put wall, summed across expiries 1..60 days out | no put with open interest above 0 at a strike at or below spot 1..60 days out, or wall_status NO_SPOT, NO_CHAIN or NO_EXPIRY | `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |

## `dividends@v2`

Trailing-12-month cash dividends, split-adjusted to the session. Stored as `rollups/instrument/dividends@v2`; reads `rollups/instrument/price_stats@v2`, `events/dividend` (optional), `events/split` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `div_ttm` | window | float32 | usd_per_share | open | >= 0 | Cash dividends with ex-date in the last 365 days, split-adjusted to the session's share terms (specials excluded); 0 for a known non-payer | no dividend in the window and fewer than min_history_days (240) bars among the last 252 sessions (too new, or bars do not cover the window, to call it a non-payer) | `events/dividend.cash_amount`, `events/dividend.ts`, `events/split.ratio` |
| `div_count_ttm` | window | int | count | open | >= 0 | Ex-dates in the last 365 days | no dividend in the window and fewer than min_history_days (240) bars among the last 252 sessions (too new, or bars do not cover the window, to call it a non-payer) | `events/dividend.ts` |
| `last_ex_date` | window | date | date | open |  | The latest ex-date in the last 365 days | no ex-date in the window (a non-payer, or unknown as for div_ttm) | `events/dividend.ts` |

## `fundamentals@v2`

Shares outstanding (SEC company facts, point in time by filing date) and its status. Stored as `rollups/instrument/fundamentals@v2`; reads `rollups/instrument/price_stats@v2`, `instruments/shares` (optional), `events/split` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `shares_outstanding` | window | float32 | shares | open | >= 0 | Shares outstanding (company total of every class), split-adjusted to the session: the latest cover-page count (dei) while the company tags it, else the latest weighted average basic | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.shares`, `instruments/shares.concept`, `instruments/shares.filed`, `instruments/shares.period_end`, `events/split.ratio` |
| `shares_as_of` | window | date | date | open |  | The count's period end (the cover date, or the end of the averaged period) | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.period_end` |
| `shares_filed` | window | date | date | open |  | The filing date that made the count public | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.filed` |
| `shares_source` | label | str | category | open | dei, weighted_basic | Which count: dei (cover page) or weighted_basic (weighted average basic) | no share-count fact filed by the session (ETFs, funds, no CIK): NO_SHARES | `instruments/shares.concept` |
| `market_cap_status` | label | str | category | open | OK, NO_SHARES, STALE, NO_PRICE | OK; NO_SHARES (no count); STALE (period end more than stale_days, 400, before the session; the count is still shown); NO_PRICE (no close) | never | `fundamentals.shares_outstanding@v2`, `price_stats.close@v2` |

## `financials@v1`

Trailing-twelve-month revenue, net income and diluted EPS and the last fiscal year's revenue (SEC company facts, point in time by filing date). Stored as `rollups/instrument/financials@v1`; reads `rollups/instrument/price_stats@v2`, `instruments/shares` (optional), `events/split` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `revenue_ttm` | window | float | usd | open | >= 0 | Revenue over the trailing twelve months: the last four discrete quarters, else the latest fiscal year (us-gaap Revenues, else RevenueFromContractWithCustomer..., else SalesRevenueNet) | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or neither four consecutive quarters nor a fiscal year of this concept are known | `instruments/shares.concept`, `instruments/shares.value`, `instruments/shares.period_start`, `instruments/shares.period_end`, `instruments/shares.filed` |
| `revenue_ttm_year_ago` | window | float | usd | open | >= 0 | The revenue TTM one year earlier (the four quarters ending four quarters before, or the previous fiscal year): the base of revenue_growth_yoy | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or fewer than eight quarters (two fiscal years) of history | `instruments/shares.concept`, `instruments/shares.value`, `instruments/shares.period_start`, `instruments/shares.period_end`, `instruments/shares.filed` |
| `net_income_ttm` | window | float | usd | open |  | Net income (NetIncomeLoss) over the trailing twelve months; negative for a loss | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or neither four consecutive quarters nor a fiscal year of this concept are known | `instruments/shares.concept`, `instruments/shares.value`, `instruments/shares.period_start`, `instruments/shares.period_end`, `instruments/shares.filed` |
| `eps_diluted_ttm` | window | float32 | usd_per_share | open |  | Diluted EPS (EarningsPerShareDiluted) over the trailing twelve months, summed from the quarters, split-adjusted to the session; negative for a loss | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or neither four consecutive quarters nor a fiscal year of this concept are known | `instruments/shares.concept`, `instruments/shares.value`, `instruments/shares.period_start`, `instruments/shares.period_end`, `instruments/shares.filed`, `events/split.ratio` |
| `revenue_fy` | window | float | usd | open | >= 0 | Revenue of the latest fiscal year reported | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or no annual revenue fact filed | `instruments/shares.concept`, `instruments/shares.value`, `instruments/shares.period_start`, `instruments/shares.period_end`, `instruments/shares.filed` |
| `revenue_fy_end` | window | date | date | open |  | The end of that fiscal year | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS; or no annual revenue fact filed | `instruments/shares.period_end` |
| `ttm_as_of` | window | date | date | open |  | The oldest period end among the TTMs shown: all of them are current to at least this date (the last quarter, or the fiscal year end of an annual one) | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS | `instruments/shares.period_end` |
| `ttm_filed` | window | date | date | open |  | The newest filing date behind the TTMs (when they were public) | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS | `instruments/shares.filed` |
| `ttm_basis` | label | str | category | open | QUARTERS, ANNUAL | QUARTERS: every TTM is the sum of four quarters; ANNUAL: at least one is the latest fiscal year | no revenue / net income / EPS fact filed by the session (ETFs, funds, no CIK, issuers that report outside USD): NO_FACTS | `instruments/shares.period_start` |
| `financials_status` | label | str | category | open | OK, PARTIAL, NO_TTM, NO_FACTS, STALE | OK (all three TTMs); PARTIAL (some); NO_TTM (facts, but no TTM can be formed); NO_FACTS (none filed); STALE (the oldest TTM ended more than stale_days, 480, before the session; the values are still shown) | never | `instruments/shares.concept` |

## `iv30@v1`

Our 30-day ATM implied vol (forward ATM, put/call mid IVs, total-variance term interpolation) beside Cboe's, with a status code. Stored as `rollups/instrument/iv30@v1`; reads `chains/option_quotes`, `rates/treasury`, `chains/underlying_quotes` (optional), `rollups/instrument/div_yield@v1` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `iv30` | chain | float | decimal | open | 0 .. 5 | Our 30-calendar-day at-the-money implied volatility: forward ATM vols of the two expiries around 30 days, interpolated in total variance (ADR 0021) | iv30_status is neither OK nor SINGLE_EXPIRY (the status says why) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `iv30_cboe` | chain | float | decimal | open | 0 .. 5 | The feed's 30-day implied volatility, as a decimal | no underlying quote for it, or the feed gives no IV30 | `chains/underlying_quotes.iv30` |
| `iv30_status` | label | str | category | open | OK, SINGLE_EXPIRY, NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_QUOTES, WIDE_SPREADS, ILLIQUID, IV_FAILED | Why iv30 has a value or not; the first failing step wins (SINGLE_EXPIRY: one usable expiry, flat vol, still a value) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest`, `chains/underlying_quotes.price` |
| `near_expiry` | chain | date | date | open |  | The selected expiry at or before 30 days out (standard monthlies first, 7..90 days) | no expiry in 7..90 days at or before the target, or no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `far_expiry` | chain | date | date | open |  | The selected expiry at or after 30 days out (standard monthlies first, 7..90 days) | no expiry in 7..90 days at or after the target, or no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `atm_strike_near` | chain | float | usd_per_share | open | >= 0 | The listed strike nearest the forward in the near expiry (the far one without a near) | no expiry was selected (NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.strike`, `chains/underlying_quotes.price` |
| `spot` | chain | float | usd_per_share | open | >= 0 | The underlying's price captured with the chain | no positive underlying price (NO_SPOT) | `chains/underlying_quotes.price` |
| `rate` | chain | float | decimal | open | -0.05 .. 0.25 | Continuous risk-free rate at 30 days, from the Treasury curve the session sees | never (the curve is a required input) | `rates/treasury.rate_cont` |
| `div_yield` | expression | float | decimal | open | 0 .. 1 | The dividend yield q used for the forward, as read from div_yield@v1 | div_yield@v1 has no yield for it (UNKNOWN; priced with q = 0) | `div_yield@v1` |
| `n_quotes_used` | chain | int | count | open | >= 0 | Option quotes whose implied vols were averaged, across both expiries | never (0 when none) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.open_interest` |

## `put_wing@v1`

The short put at the expiry nearest 45 days: the one nearest 8-15 delta (our delta), then by cash-secured ROC; band OI, volume and spread. Stored as `rollups/instrument/put_wing@v1`; reads `chains/option_quotes`, `rates/treasury`, `chains/underlying_quotes` (optional), `rollups/instrument/div_yield@v1` (optional).

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `wing_status` | label | str | category | open | OK, OUTSIDE_BAND, NO_SPOT, NO_CHAIN, NO_EXPIRY, NO_STRIKE | OK (best put in 0.08..0.15 \|delta\|), OUTSIDE_BAND (best put in 0.05..0.35 but not the band), or the first failing step: NO_SPOT, NO_CHAIN (no puts), NO_EXPIRY (none 30..60 days out), NO_STRIKE (no put with our \|delta\| in 0.05..0.35) | never | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `target_expiry` | chain | date | date | open |  | The put expiry closest to 45 calendar days among those 30..60 days out, standard monthlies first (ties: the earlier); the best put's expiry | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `target_dte` | chain | int | days | open | 30 .. 60 | Calendar days from the session to the target expiry (the best put's DTE) | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.expiry` |
| `n_unpriced` | chain | int | count | open | >= 0 | Puts at the target expiry without our delta (no two-sided quote, or the implied-vol inversion failed): never candidates | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `n_strikes` | chain | int | count | open | >= 0 | Strikes at the target expiry whose put has our \|delta\| in 0.08..0.15 (edges included); 0 when none | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `wing_oi` | chain | int | count | open | >= 0 | Open interest across the puts in the 0.08..0.15 band; 0 when none | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1`, `chains/option_quotes.open_interest` |
| `wing_volume` | chain | int | count | open | >= 0 | Volume across the puts in the 0.08..0.15 band; 0 when none | no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1`, `chains/option_quotes.volume` |
| `wing_spread_pct` | chain | float32 | decimal | open | 0 .. 2 | Median (ask - bid) / mid across the puts in the 0.08..0.15 band (stored quote) | no put with our \|delta\| in 0.08..0.15 at the target expiry, or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `delta_band_distance` | chain | float32 | ratio | open | 0 .. 0.2 | How far the best put's \|delta\| is from the 0.08..0.15 band: 0 inside, else the distance to the nearer edge (0.20 delta: 0.05) | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `best_put_strike` | chain | float32 | usd_per_share | open | >= 0 | The best put's strike: the candidate nearest the band, then the highest ROC (ties: higher OI, then lower strike) | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `best_put_delta` | chain | float32 | ratio | open | -0.35 .. -0.05 | The best put's delta (ours, negative) | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `best_put_iv` | chain | float32 | decimal | open | 0 .. 5 | The best put's implied vol (ours, from the mid) | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |
| `best_put_mid` | chain | float32 | usd_per_share | open | >= 0 | The best put's mid, (bid + ask) / 2: the premium per share | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `best_put_oi` | chain | int | count | open | >= 0 | The best put's open interest | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.open_interest` |
| `best_put_volume` | chain | int | count | open | >= 0 | The best put's volume | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.volume` |
| `best_put_spread_pct` | chain | float32 | decimal | open | 0 .. 2 | The best put's (ask - bid) / mid on the stored quote (judge the trade on a live one) | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask` |
| `best_put_roc` | chain | float32 | decimal | open | 0 .. 1 | The best put's cash-secured return on capital: premium / (strike x 100) = mid / strike | no put at the target expiry with our \|delta\| in 0.05..0.35 (NO_STRIKE), or no target expiry (wing_status NO_SPOT, NO_CHAIN or NO_EXPIRY) | `chains/option_quotes.bid`, `chains/option_quotes.ask`, `chains/option_quotes.strike`, `chains/option_quotes.expiry`, `chains/option_quotes.right`, `chains/underlying_quotes.price`, `rates/treasury.rate_cont`, `div_yield@v1` |

## `iv_history@v2`

IV30 rank and percentile over 252 sessions (provisional after 60). Stored as `rollups/instrument/iv_history@v2`; reads `rollups/instrument/iv30@v1`.

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Inputs |
|---|---|---|---|---|---|---|---|---|
| `iv30` | expression | float32 | decimal | open | 0 .. 5 | The session's IV30 from iv30@v1 (ours; the feed's with source = cboe) | iv30@v1 has no IV for the session (its iv30_status says why) | `iv30.iv30@v1`, `iv30.iv30_cboe@v1` |
| `iv_rank_252d` | window | float32 | decimal | open | 0 .. 1 | IV rank: (iv30 - min) / (max - min) over the last 252 sessions' IVs, today included | rank_status is UNKNOWN (fewer than 60 sessions with an IV), or there is no IV today; or every IV in the window is equal | `iv30.iv30@v1` |
| `iv_percentile_252d` | window | float32 | decimal | open | 0 .. 1 | IV percentile: the share of the window's earlier IVs strictly below today's | rank_status is UNKNOWN (fewer than 60 sessions with an IV), or there is no IV today; or no earlier IV | `iv30.iv30@v1` |
| `history_days` | window | int | sessions | open | >= 0 | Sessions of the 252-session window with an IV, today included (gaps are not filled) | never | `iv30.iv30@v1` |
| `rank_status` | label | str | category | open | UNKNOWN, PROVISIONAL, FULL | UNKNOWN below 60 sessions with an IV (no rank), PROVISIONAL below 252, FULL from 252 | never | `iv30.iv30@v1` |

## Expression features

Declared in `config/site/features/<theme>.toml`; virtual (computed on read) unless stored (materialised, by the `rollups` task after its inputs).

### `fundamentals.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `div_yield` | expression | float32 | decimal | open | 0 .. 1 | Trailing dividend yield: div_ttm / close; the continuous q in option pricing (iv30 reads it, so it is stored) | dividends div_ttm is null (no dividend in the window and too little bar history to call it a non-payer), or the close is not positive | `if(price_stats.close > 0, dividends.div_ttm / price_stats.close, null)` | `rollups/instrument/div_yield@v1` |
| `market_cap` | expression | float | usd | open | >= 0 | shares_outstanding x close (the company total times this class's close) | fundamentals market_cap_status is not OK (no count, a stale count, or no close) | `if(fundamentals.market_cap_status == "OK", fundamentals.shares_outstanding * price_stats.close, null)` | virtual |
| `pe_ratio` | expression | float | ratio | open | >= 0 | Trailing P/E: close / diluted EPS over the trailing twelve months. Null when the company lost money (EPS <= 0): a negative P/E is not shown | financials eps_diluted_ttm is null or not positive (a loss; ETFs and funds have none), the close is not positive, or the financials are STALE (the oldest TTM period ended more than stale_days before the session) | `if(financials.eps_diluted_ttm > 0 and price_stats.close > 0 and financials.financials_status != "STALE", price_stats.close / financials.eps_diluted_ttm, null)` | virtual |
| `revenue_growth_yoy` | expression | float | decimal | open | >= -1 | Revenue growth year over year: the trailing-twelve-month revenue against the same TTM a year earlier | revenue_ttm or revenue_ttm_year_ago is null (fewer than two years of reported quarters or fiscal years), or the year-ago revenue is not positive | `if(financials.revenue_ttm_year_ago > 0, financials.revenue_ttm / financials.revenue_ttm_year_ago - 1, null)` | virtual |

### `liquidity.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `option_chain_known` | expression | bool | flag | open |  | Whether the session's chain run says what the options are: its fetch succeeded, or it did not list the instrument (no options) | no option_liquidity rows for the session (chains not run) | `if(exists(option_liquidity), one_of(option_liquidity.liq_status, "OK", "NO_CHAIN", "NO_STANDARD_SERIES", "NO_TARGET_EXPIRY"), true)` | virtual |
| `option_tier` | label | str | category | open | A, B, C, D | The worse of the put and call tier (option_liquidity); D: no usable options, also for an instrument the session's chain run did not list | option_chain_known is not true (no chain run for the session, or its fetch failed: STALE_DATA, FETCH_ERROR, NOT_ATTEMPTED) | `if(option_chain_known, max(coalesce(option_liquidity.put_tier, "D"), coalesce(option_liquidity.call_tier, "D")), null)` | virtual |
| `option_chain_oi` | expression | int | count | open | >= 0 | Chain open interest (option_liquidity); 0 when the chain run did not list the instrument | option_chain_known is not true | `if(option_chain_known, coalesce(option_liquidity.chain_oi, 0), null)` | virtual |
| `option_chain_volume` | expression | int | count | open | >= 0 | Chain volume (option_liquidity); 0 when the chain run did not list the instrument | option_chain_known is not true | `if(option_chain_known, coalesce(option_liquidity.chain_volume, 0), null)` | virtual |
| `liquidity_high` | expression | bool | flag | open |  | Every HIGH threshold holds: 20-session ADV >= $100M, close >= $10, worse option tier A, chain OI >= 50k, chain volume >= 5k (params; a threshold <= 0 is no requirement) | no threshold fails and one cannot be checked (an unknown ADV, close or option input) | `(min_adv_usd <= 0 or price_stats.adv_usd_20d >= min_adv_usd) and (min_price <= 0 or price_stats.close >= min_price) and option_tier == "A" and (min_chain_oi <= 0 or option_chain_oi >= min_chain_oi) and (min_chain_volume <= 0 or option_chain_volume >= min_chain_volume)` (min_adv_usd = 100000000.0, min_price = 10.0, min_chain_oi = 50000, min_chain_volume = 5000) | virtual |
| `liquidity_medium` | expression | bool | flag | open |  | Every MEDIUM threshold holds: 20-session ADV >= $10M, close >= $5, worse option tier A or B, chain OI >= 5k (params; chain volume 0: no requirement) | no threshold fails and one cannot be checked (an unknown ADV, close or option input) | `(min_adv_usd <= 0 or price_stats.adv_usd_20d >= min_adv_usd) and (min_price <= 0 or price_stats.close >= min_price) and one_of(option_tier, "A", "B") and (min_chain_oi <= 0 or option_chain_oi >= min_chain_oi) and (min_chain_volume <= 0 or option_chain_volume >= min_chain_volume)` (min_adv_usd = 10000000.0, min_price = 5.0, min_chain_oi = 5000, min_chain_volume = 0) | virtual |
| `liquidity_class` | label | str | category | open | HIGH, MEDIUM, LOW, UNKNOWN | HIGH when every HIGH threshold holds, else MEDIUM when every MEDIUM one does, else LOW; UNKNOWN when an unknown input decides it | no price_stats row for the instrument on the session (no bar) | `if(not exists(price_stats), null, if(is_null(liquidity_high), "UNKNOWN", if(liquidity_high, "HIGH", if(is_null(liquidity_medium), "UNKNOWN", if(liquidity_medium, "MEDIUM", "LOW")))))` | virtual |

### `price.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `pct_from_high_52w` | expression | float | decimal | open | -1 .. 0 | Close / 52-week high - 1 (at or below 0) | price_stats high_52w is null (fewer than 240 bars in the last 252 sessions), or no price_stats row | `price_stats.close / price_stats.high_52w - 1` | virtual |
| `pct_from_low_52w` | expression | float | decimal | open | >= 0 | Close / 52-week low - 1 (at or above 0) | price_stats low_52w is null (fewer than 240 bars in the last 252 sessions), or no price_stats row | `price_stats.close / price_stats.low_52w - 1` | virtual |
| `near_52w` | label | str | category | open | HIGH, LOW, BOTH, NONE | Where the close sits in its 52-week range: HIGH within 10% (params.within) of the high, LOW within 10% of the low, BOTH (a narrow range), else NONE | the 52-week high or low is unknown (pct_from_high_52w or pct_from_low_52w is null) | `if(pct_from_high_52w >= -within and pct_from_low_52w <= within, "BOTH", if(pct_from_high_52w >= -within, "HIGH", if(pct_from_low_52w <= within, "LOW", "NONE")))` (within = 0.1) | virtual |
| `dist_52w` | expression | float | decimal | open | >= 0 | Distance to the nearer 52-week extreme: the smaller of (high - close) / high and (close - low) / low (0 at an extreme) | the 52-week high or low is unknown (pct_from_high_52w or pct_from_low_52w is null) | `min(-pct_from_high_52w, pct_from_low_52w)` | virtual |
| `pct_vs_sma_20` | expression | float | decimal | open | >= -1 | Close / 20-session moving average - 1 | price_stats sma_20 is null (a gap among the last 20 sessions, or a shorter history), or no price_stats row | `price_stats.close / price_stats.sma_20 - 1` | virtual |
| `pct_vs_sma_50` | expression | float | decimal | open | >= -1 | Close / 50-session moving average - 1 | price_stats sma_50 is null (a gap among the last 50 sessions, or a shorter history), or no price_stats row | `price_stats.close / price_stats.sma_50 - 1` | virtual |
| `pct_vs_sma_200` | expression | float | decimal | open | >= -1 | Close / 200-session moving average - 1 | price_stats sma_200 is null (a gap among the last 200 sessions, or a shorter history), or no price_stats row | `price_stats.close / price_stats.sma_200 - 1` | virtual |

### `swing.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `atr_pct` | expression | float | decimal | open | >= 0 | Wilder ATR(14) as a fraction of the close: 0.02 is a typical daily range of 2% | atr_14 is null (fewer than 15 consecutive bars), or no momentum or price_stats row | `momentum.atr_14 / price_stats.close` | virtual |
| `range_20d_pct` | expression | float | decimal | open | >= 0 | Width of the 20-session high-low channel as a fraction of the close: (high_20d - low_20d) / close | high_20d or low_20d is null (a gap among the last 20 sessions, or a shorter history) | `(momentum.high_20d - momentum.low_20d) / price_stats.close` | virtual |
| `trend_state` | label | str | category | open | UPTREND, DOWNTREND, MIXED | UPTREND when close > SMA50 > SMA200, DOWNTREND when close < SMA50 < SMA200, else MIXED (an equality is MIXED) | sma_50 or sma_200 is null (a gap among the last 50 / 200 sessions, or a shorter history), or no price_stats row | `if(is_null(price_stats.sma_50) or is_null(price_stats.sma_200), null, if(price_stats.close > price_stats.sma_50 and price_stats.sma_50 > price_stats.sma_200, "UPTREND", if(price_stats.close < price_stats.sma_50 and price_stats.sma_50 < price_stats.sma_200, "DOWNTREND", "MIXED")))` | virtual |
| `dist_to_resistance` | expression | float | decimal | open | >= 0 | How far the nearest confirmed swing high above the close is: (swing_high - close) / close, 0.05 is 5% above | no confirmed swing high above the close in the last 252 sessions (e.g. at a one-year high), or no swing_levels row | `(swing_levels.swing_high - price_stats.close) / price_stats.close` | virtual |
| `dist_to_support` | expression | float | decimal | open | 0 .. 1 | How far the nearest confirmed swing low below the close is: (close - swing_low) / close, 0.05 is 5% below | no confirmed swing low below the close in the last 252 sessions (e.g. at a one-year low), or no swing_levels row | `(price_stats.close - swing_levels.swing_low) / price_stats.close` | virtual |
| `dist_to_resistance_atr` | expression | float | ratio | open | >= 0 | Distance to resistance in ATRs: (swing_high - close) / atr_14 | dist_to_resistance is null, atr_14 is null (fewer than 15 consecutive bars), or atr_14 is 0 | `(swing_levels.swing_high - price_stats.close) / momentum.atr_14` | virtual |
| `dist_to_support_atr` | expression | float | ratio | open | >= 0 | Distance to support in ATRs: (close - swing_low) / atr_14 | dist_to_support is null, atr_14 is null (fewer than 15 consecutive bars), or atr_14 is 0 | `(price_stats.close - swing_levels.swing_low) / momentum.atr_14` | virtual |
| `breakout_20d` | expression | bool | flag | open |  | A 20-session breakout on volume: close above the highest high of the 20 sessions before today (prior_high_20d) and rel_volume above 1.5 (params.min_rel_volume) | neither condition is false and one is unknown (prior_high_20d or rel_volume null: a gap among the last 21 sessions, or a shorter history) | `price_stats.close > momentum.prior_high_20d and momentum.rel_volume > min_rel_volume` (min_rel_volume = 1.5) | virtual |
| `pullback_to_sma20` | expression | bool | flag | open |  | A pullback in an uptrend: trend_state UPTREND and the close within 1 ATR (params.atr_multiple) of SMA20, above or below it (edges included) | neither condition is false and one is unknown (trend_state, sma_20 or atr_14 null) | `trend_state == "UPTREND" and abs(price_stats.close - price_stats.sma_20) <= atr_multiple * momentum.atr_14` (atr_multiple = 1.0) | virtual |

### `volatility.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `iv_hv_spread` | expression | float | decimal | open | -5 .. 5 | IV30 minus HV30 (iv_history, price_stats): the variance risk premium's raw input | iv30 or hv30 is null (no IV for the session, or a gap in the last 31 sessions) | `iv_history.iv30 - price_stats.hv30` | virtual |
| `iv_hv_ratio` | expression | float | ratio | open | >= 0 | IV30 / HV30 (iv_history, price_stats) | iv30 or hv30 is null, or hv30 is 0 | `if(price_stats.hv30 > 0, iv_history.iv30 / price_stats.hv30, null)` | virtual |
| `iv_rank` | expression | float | decimal | personal | 0 .. 1 | IV rank over 252 sessions: IBKR's (ibkr_iv) where it has one, else ours (iv_history); iv_rank_source says which | neither has a rank: both rank statuses are UNKNOWN (under 60 sessions of IV), there is no IV today, or every IV in the window is equal | `coalesce(ibkr_iv.iv_rank_252d_ibkr, iv_history.iv_rank_252d)` | virtual |
| `iv_percentile` | expression | float | decimal | personal | 0 .. 1 | IV percentile over 252 sessions: IBKR's (ibkr_iv) where it has one, else ours (iv_history); iv_rank_source says which | neither has a percentile: both rank statuses are UNKNOWN, there is no IV today, or no earlier IV | `coalesce(ibkr_iv.iv_percentile_252d_ibkr, iv_history.iv_percentile_252d)` | virtual |
| `iv_rank_source` | label | str | category | personal | ibkr, ours | Where iv_rank and iv_percentile came from: ibkr (IBKR's IV history) or ours (iv_history, from Cboe chains) | iv_rank is null (neither source has a rank) | `if(not is_null(ibkr_iv.iv_rank_252d_ibkr), "ibkr", if(not is_null(iv_history.iv_rank_252d), "ours", null))` | virtual |

### `vrp.toml`

| Feature | Kind | Type | Unit | Licence | Valid values | Description | Null when | Formula | Stored |
|---|---|---|---|---|---|---|---|---|---|
| `vrp_iv30` | expression | float | decimal | personal | 0 .. 5 | The VRP gate's IV30: the lower of IBKR's (ibkr_iv) and Cboe's (iv30.iv30_cboe) when both exist, else whichever exists; vrp_iv30_source says which | neither IBKR nor Cboe has an IV30 for the session | `min(coalesce(ibkr_iv.iv30_ibkr, iv30.iv30_cboe), coalesce(iv30.iv30_cboe, ibkr_iv.iv30_ibkr))` | virtual |
| `vrp_iv30_source` | label | str | category | personal | ibkr, cboe | Where vrp_iv30 came from: ibkr or cboe (the lower one when both exist; ibkr on a tie) | vrp_iv30 is null (neither source has an IV30) | `if(is_null(vrp_iv30), null, if(is_null(iv30.iv30_cboe), "ibkr", if(is_null(ibkr_iv.iv30_ibkr), "cboe", if(ibkr_iv.iv30_ibkr <= iv30.iv30_cboe, "ibkr", "cboe"))))` | virtual |
| `vrp_iv_hv_spread` | expression | float | decimal | personal | -5 .. 5 | vrp_iv30 minus HV30 (price_stats): the VRP scanner's volatility premium | vrp_iv30 or hv30 is null (no IV30 from IBKR or Cboe, or a gap in the last 31 sessions) | `vrp_iv30 - price_stats.hv30` | virtual |
| `vrp_iv_hv_ratio` | expression | float | ratio | personal | >= 0 | vrp_iv30 / HV30 (price_stats): plain ratio, no HV30 floor (owner decision 2026-10-03) | vrp_iv30 or hv30 is null, or hv30 is 0 | `vrp_iv30 / price_stats.hv30` | virtual |

## Superseded groups

Readable until retired (`algotrade-ingest retire-features --group <key>`); their selection fields fail with the field that replaced them.

| Group | Replaced by |
|---|---|
| `price_stats@v1` | `price_stats@v2` + expression features |
| `dividends@v1` | `dividends@v2` + expression features |
| `fundamentals@v1` | `fundamentals@v2` + expression features |
| `iv_history@v1` | `iv_history@v2` + expression features |
| `liquidity_class@v1` | `price_stats@v2` + expression features; `chain_oi` -> `feature.option_chain_oi`, `rule_hash` retired |
