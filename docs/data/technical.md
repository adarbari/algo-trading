# Technical, level and relative-strength features (TA track)

Bands, z-scores, trend statistics, price-level structure, volume at price and relative
strength from stored daily bars, and the option-chain shape and flow groups that the options
strategies read. Each feature is one sentence the owner can check against a chart. The
options groups' conventions are in [positioning.md](positioning.md) (ADR 0031); the earnings
reaction statistics are the EV track's ([event-sensitivity-plan.md](../event-sensitivity-plan.md)).
Every column's generated entry is in [features.md](features.md); how to read each one is in the
field guide ([field-guide.md](field-guide.md)).

## The bar: exhaustive, then selective

A feature earns its column when a named strategy sets a threshold on it and no stored column
already expresses it. Left out on purpose, with the column that covers the need:

| Left out | Why |
|---|---|
| MACD, ADX, stochastics, Williams %R, Ichimoku, Supertrend | overlap with `rsi_14`, `atr_14`, the SMA stack, `trend_state`, the bands and the stretches below |
| OBV and its slope | `cmf_20d` and `up_volume_share_20d` carry the accumulation reading |
| Probability of profit of a short strike | it is `1 - |delta|` to first order: a rule reads `best_put_delta` |
| Gamma and delta exposure, hedge wall, flip level | ADR 0031's dealer-sign decision (P1) is the owner's; the drafts stay in positioning.md |
| Historical earnings reactions, IV crush | EV track (`own_sensitivity`, `iv_crush_pct`) |
| An intraday volume profile | needs intraday bars (roadmap phase 6); the daily-bar profile below says it is an approximation |
| Breakdown-and-retest (the short side) | mirror of the long side; added when a screen asks |

## The owner's list, mapped (2026-10-06)

Every requested feature and where it lives: an existing field, a column of this track, or
left out with the field that covers it. Screener presets come last (section "Presets").

| Area | Requested | Where |
|---|---|---|
| Trend | SMA 20 / 50 / 200 | `price_stats` `sma_20/50/200` |
| | EMA 10 / 20 / 50 / 200 | `bands` `ema_10/20/50/200` (EMA 5 and SMA 5 / 10 / 100 left out: one short and one long average each is enough to state alignment; SMA 10 is `ema_10`'s twin) |
| | slopes | `bands` `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d` |
| | EMA alignment | `feature.ema_stack` (BULL / BEAR / MIXED over EMA 20 / 50 / 200; `trend_state` is the SMA version) |
| | distance from moving averages | `feature.pct_vs_sma_20/50/200`, `feature.pct_vs_ema_20/50/200`, `feature.stretch_sma20_atr`, `feature.stretch_sma50_atr` |
| Momentum | returns 1 / 3 / 5 / 10 / 20 / 60 / 120 / 252 | `trend_stats` `ret_1d`, `ret_3d`, `ret_10d`; `momentum.ret_5d`; `price_stats.ret_20d/60d`; `trend_stats` `ret_120d`, `ret_252d`, `mom_12_1` |
| | momentum acceleration | `trend_stats` `mom_accel_5d` (ret_5d today minus ret_5d five sessions earlier; negative = deteriorating) |
| | relative strength vs SPY / sector, percentile ranks | `relative_strength@v1`: `rs_spy_63d`, `rs_spy_252d`, `rs_line_high_252d`, `rs_sector_63d`, `rs_spy_trend_20d` (improving / deteriorating), `ret_5d_pctile`, `mom_pctile_63d`, `mom_pctile_252d`; `feature.rs_spy_positive`, `feature.rs_improving` |
| Price structure | 20 / 50 / 100 / 200-session highs and lows | `momentum.high_20d/low_20d/high_50d/low_50d`; `trend_stats` `high_100d`, `low_100d`, `high_200d`, `low_200d` |
| | 52-week high / low | `price_stats.high_52w/low_52w`; `feature.pct_52w_range` (where the close sits in the range) |
| | swing highs / lows, support / resistance | `swing_levels` |
| | number of touches | `pivot_strength@v1` (planned) |
| | breakout / breakdown distance | `feature.dist_to_high_20d/50d`, `feature.dist_to_low_20d/50d`; `feature.breakout_magnitude_20d`; `feature.breakdown_20d`, `feature.breakout_50d` (over `trend_stats` `prior_high_50d`, `prior_low_20d`, `prior_low_50d`) |
| Volatility | ATR 5 / 14 / 20 | `momentum.atr_14`; `vol_stats@v1` (planned) `atr_5`, `atr_20`; `feature.atr_ratio_5_20` (expansion above 1, contraction below). ATR 10 and 50 left out: 5 / 14 / 20 state expansion and the norm |
| | ATR % | `feature.atr_pct` |
| | HV 10 / 20 / 30 / 60 | `price_stats.hv20/hv30`; `vol_stats` `hv10`, `hv60`; `feature.hv_ratio_10_60` |
| | volatility percentile | `vol_stats` `hv20_pctile_252d`; `iv_percentile` on the implied side |
| | Bollinger width, expansion / contraction | `feature.bb_width`, `bands.bb_width_pctile_252d`, `feature.bb_squeeze`, `feature.atr_ratio_5_20` |
| Price location | distance to support / resistance | `feature.dist_to_support(_atr)`, `feature.dist_to_resistance(_atr)` |
| | distance to EMA 20 / 50 / 200, to 20 / 50-session high / low | `feature.pct_vs_ema_*`, `feature.dist_to_high_*`, `feature.dist_to_low_*` |
| | Bollinger position, ATR-channel position, 52-week percentile | `feature.bb_pct_b`, `feature.kc_position`, `feature.pct_52w_range` |
| | close location in the day's range | `trend_stats` `close_range_pos` ((close - low) / (high - low) of the session) |
| Pullback quality | magnitude, pullback / ATR | `feature.dist_to_high_20d`, `feature.pullback_atr_20d` ((high_20d - close) / atr_14) |
| | duration | `trend_stats` `sessions_since_high_20d` |
| | retracement % | `feature.donchian_pos_20d` (1 - retracement of the 20-session range) |
| | volume contraction | `volume.volume_ratio_5d_20d`, `feature.volume_dry_up` |
| | higher-low formation | `pivot_strength.pivot_structure` (planned) |
| | momentum deterioration / recovery | `trend_stats.mom_accel_5d`; `relative_strength.rs_spy_trend_20d` |
| Breakout quality | above the 20 / 50-session high, magnitude, volume | `feature.breakout_20d`, `feature.breakout_50d`, `feature.breakout_magnitude_20d`, `momentum.rel_volume`, `trend_stats.close_range_pos` |
| | ATR expansion | `feature.atr_ratio_5_20` |
| | follow-through, failed-breakout history | `retest@v1` (planned): `sessions_since_breakout`, `retest_state`, `failed_breakouts_252d` |
| Volume / liquidity | dollar volume, relative volume | `volume.dollar_volume`, `price_stats.adv_usd_20d`, `momentum.rel_volume`, `volume.volume_z_20d` |
| | volume trend / acceleration / percentile, turnover | `vol_stats` (planned) `adv_shares_60d`, `volume_pctile_252d`; `feature.volume_trend_20_60`; `feature.turnover_20d` (adv_shares_20d / shares_outstanding) |
| Market / sector regime | SPY / QQQ trend, market volatility, breadth | `market_trend@v2`, `market_breadth@v1`, `regime@v3` (`market.*`); IWM through `cross_asset.iwm_vs_spy` |
| | sector momentum, sector relative strength | `relative_strength@v1`: `sector_etf`, `sector_ret_63d`, `sector_rank_63d`, `rs_sector_63d`; `feature.sector_leader` |
| Options | IV, IV rank, IV percentile, IV / HV, IV - HV spread | `iv30`, `iv_rank`, `iv_percentile`, `iv_hv_ratio`, `iv_hv_spread`, the `vrp_*` set |
| | OI, option volume, spread, delta, DTE | `option_liquidity`, `put_wing`, `oi_walls`, `nearest_expiry` |
| | skew, expected move | `skew@v1`, `implied_move@v1` (planned, positioning.md) |
| | strike distance from support, / ATR | `feature.put_support_cushion` ((best put strike... see swing.toml: (swing_low - best_put_strike) / close) and `feature.put_support_cushion_atr` (/ atr_14) |
| Catalyst / risk | days to earnings | `earnings.days_to_earnings`, `feature.earnings_before_expiry` |
| | historical, worst and average earnings moves; news / catalyst flags | EV track (`own_sensitivity`: `move_multiple_median`, `down_move_worst_pct`, 8-K item flags); not duplicated here |

## Presets

Once the inputs above exist, the eight rule screens the owner described (breakout, pullback,
support reversal, exhaustion, trend continuation, range breakout, failed breakout, oversold
reversal) are site presets in `config/site/presets/` (`add-screener`), each criterion a
catalogue field with its guide threshold. They are the last PR of the track; a preset that
needs a field this table marks planned waits for that field.

## Where the columns live

`features/rollups/price/` is at its module cap, so the new kinds get their own folders (`relative/` holds the groups that compare an instrument with the market, its sector and the universe) (one
folder per kind of thing; `architecture/layout.toml`):

| Group | Folder | Columns | Status |
|---|---|---|---|
| `bands@v1` | `price/` | `ema_10/20/50/200`, `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d`, `close_std_20`, `bb_width_pctile_252d`, `band_walk` | built |
| `trend_stats@v1` | `price/` | `ret_1d/3d/10d/120d/252d`, `mom_12_1`, `mom_accel_5d`, `ret_z_20d`, `high_100d`, `low_100d`, `high_200d`, `low_200d`, `prior_high_50d`, `prior_low_20d`, `prior_low_50d`, `sessions_since_high_20d`, `close_range_pos`, `close_streak`, `sma20_streak`, `tight_range_sessions` | built |
| `swing_levels@v1` | `levels/` (moved from `price/`) | unchanged | built |
| `pivot_strength@v1` | `levels/` | `resistance_touches`, `support_touches`, `resistance_age`, `support_age`, `pivot_structure` | built ([swing.md](swing.md)) |
| `retest@v1` | `levels/` | `breakout_date`, `breakout_level`, `sessions_since_breakout`, `retest_state`, `failed_breakouts_252d` | built ([swing.md](swing.md)) |
| `gaps@v1` | `levels/` | `gap_open_pct`, `gap_above`, `gap_above_date`, `gap_below`, `gap_below_date` | built ([swing.md](swing.md)) |
| `volume_profile@v1` | `levels/` | `poc_252d`, `value_area_high`, `value_area_low`, `hvn_above`, `hvn_below`, `lvn_above`, `lvn_below`, `volume_near_close_share`, `profile_status` | planned |
| `anchored_vwap@v2` | `price/` | v1 + `avwap_swing_low`, `avwap_swing_high` | planned |
| `relative_strength@v1` | `relative/` | `rs_spy_63d`, `rs_spy_252d`, `rs_line_high_252d`, `rs_spy_trend_20d`, `ret_5d_pctile`, `mom_pctile_63d`, `mom_pctile_252d`, `sector_etf`, `sector_ret_63d`, `rs_sector_63d`, `sector_rank_63d` | built |
| `chain_flow@v1`, `flow_history@v1`, `skew@v1`, `skew_history@v1`, `implied_move@v1`, `iv_term@v1` | `positioning/` | [positioning.md](positioning.md) | planned |
| `call_wing@v1` | `options/` | the covered-call mirror of `put_wing@v1` | planned |
| `dividend_schedule@v1` | `corporate/` | `next_ex_date`, `next_div_amount`, `days_to_ex_date` | planned |

Formulas over stored columns are expression features (computed on read):
`config/site/features/bands.toml` (bands, channels, z-scores, stretches),
`swing.toml` (level distances, the pullback in ATRs, the 52-week position, the 50-session breakout and
20-session breakdown, the short put's cushion above support), `price.toml` (`rs_spy_positive`,
`rs_improving`, `sector_leader`),
`positioning.toml` (flow ratios, skew, term structure, implied move, wing yields).

## Shared rules

- Bars are `bars/1d` split-adjusted as of the session (`data.prices.session_bars`); one row
  per instrument with a bar on the session.
- A window named in a column (`_20`, `_252d`) is part of the definition: changing it is a new
  version. A gap (a session without a bar) inside a window makes the value null (UNKNOWN),
  never a shorter window; the exceptions say so (`bb_width_pctile_252d`, the profile).
- Null is UNKNOWN, never zero; a ratio with a zero denominator is null.
- Point in time (ADR 0007): a row for session S reads bars up to S only; a backfilled row
  equals the row computed on S.

## `bands@v1` (price/)

Inputs: `bars/1d`, the session plus 399 earlier sessions (the EMA run, and 252 bandwidths of
20 closes each).

| Column | Definition | Null when |
|---|---|---|
| `close_std_20` | sample standard deviation (ddof 1) of the last 20 closes, the session included | a gap among the last 20 sessions, or a shorter history |
| `ema_10`, `ema_20`, `ema_50`, `ema_200` | exponential moving average of the close, alpha 2 / (n + 1), seeded with the mean of the first n closes of the consecutive run of bars ending on the session (at most the last 400 sessions; every charting package seeds the same way and uses all its history, so the 200 differs from theirs by the seed's remaining weight, (199/201)^k after k more bars) | fewer than n consecutive bars ending on the session |
| `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d` | the average today / the average h sessions earlier - 1 | the average is unknown on either session |
| `bb_width_pctile_252d` | share of the 252 sessions before the session whose Bollinger bandwidth (4 x close_std_20 / sma_20) was strictly below the session's: 0.05 is a squeeze (narrower than 95% of the year), 0.95 an expansion | the session's bandwidth is unknown, or fewer than 240 of the 252 sessions before have one |
| `band_walk` | signed count of consecutive sessions, ending on the session, with the close above the upper Bollinger band (positive) or below the lower (negative); 0 inside the bands | the session's bands are unknown (the count stops at the first session without bands) |

Expression features (`bands.toml`), with `k = 2` (Bollinger) and `m = 2` (Keltner, over
`atr_14`; the classic uses ATR(10): same reading, one window fewer to store):
`bb_upper`, `bb_lower`, `bb_width`, `bb_pct_b`, `kc_upper`, `kc_lower`, `kc_position`,
`bb_squeeze` (both Bollinger bands inside the Keltner channel: the TTM squeeze), `price_z_20d`
((close - sma_20) / close_std_20), `stretch_sma20_atr`, `stretch_sma50_atr` ((close - SMA) /
atr_14), `donchian_pos_20d` ((close - low_20d) / (high_20d - low_20d)), `pct_vs_ema_20/50/200`
and `ema_stack` (BULL / BEAR / MIXED).

Worked example: closes 100, 101, ..., 119 (20 bars): sma_20 109.5, close_std_20 5.916;
bb_upper 121.33, bb_lower 97.67, bb_width 0.2161, bb_pct_b (119 - 97.67) / 23.66 = 0.9014,
price_z_20d 1.606.

## `trend_stats@v1` (price/)

Inputs: `bars/1d`, the session plus 252 earlier sessions. Param `tight_range_pct` (0.15).

| Column | Definition | Null when |
|---|---|---|
| `ret_1d`, `ret_3d`, `ret_10d`, `ret_120d`, `ret_252d` | close / close n sessions earlier - 1 | a gap among the last n + 1 sessions, or a shorter history |
| `mom_accel_5d` | ret_5d today - ret_5d five sessions earlier | a gap among the last 11 sessions |
| `high_100d`, `low_100d`, `high_200d`, `low_200d` | the extreme over the last n sessions, the session included | a gap among the last n sessions |
| `prior_high_50d`, `prior_low_20d`, `prior_low_50d` | the extreme over the n sessions before the session (the session excluded): the level a breakout or breakdown close must clear | a gap among those n sessions |
| `sessions_since_high_20d` | sessions since the highest high of the last 20 (the latest of equal highs; 0: today) | a gap among the last 20 sessions |
| `close_range_pos` | (close - low) / (high - low) of the session's bar | the bar has no range |
| `mom_12_1` | close 21 sessions earlier / close 252 sessions earlier - 1: the 12-month return with the last month skipped (Jegadeesh-Titman) | a gap among the last 253 sessions, or a shorter history |
| `ret_z_20d` | the session's one-session return / the sample standard deviation of the 20 one-session returns before it | a gap among the last 22 sessions, a shorter history, or those 20 returns were all equal |
| `close_streak` | signed consecutive sessions, ending on the session, with the close above the previous close (positive) or below it (negative); 0 when unchanged | no bar on the previous session |
| `sma20_streak` | signed consecutive sessions, ending on the session, with the close above its 20-session mean (positive) or below (negative); 0 when equal | the session's 20-session mean is unknown |
| `tight_range_sessions` | consecutive sessions, ending on the session, on which (high_20d - low_20d) / close was at most tight_range_pct (0.15): the length of the base | the session's 20-session range is unknown; 0 when the session itself is not tight |

A streak counts only while every session in it has a bar (and, for `sma20_streak`, a known
mean); it is capped by the 253 sessions read.

Worked examples: 60 closes rising every day give `close_streak` 59 and `sma20_streak` 41
(the mean exists from the 20th session); `ret_z_20d` with 20 prior returns alternating +1% /
-1% (sample stdev 0.01026) and a +3% session is 2.92; a 2% daily range with one spike high 30
sessions ago gives `tight_range_sessions` 10 (the spike left the 20-session window 10
sessions ago).

## `relative_strength@v1` (relative/)

Inputs: `bars/1d` (every instrument, the session plus 252 earlier sessions), `instruments/symbol_ids`
(finds SPY and the eleven sector ETFs by ticker: a lookup, never a population), `universe`
(the population of the percentiles) and `instruments/company` (the SEC sector). Params
`min_members` (200), `min_coverage` (0.9) and `min_sector_etfs` (6). One row per instrument with a bar on the session,
the ETFs and SPY included.

An n-session return is close / close n sessions earlier - 1 and is known only when all n + 1
closes exist: a gap makes it null (UNKNOWN), never a shorter window. The sector -> ETF map is
`SECTOR_ETFS` (the sector names are the SIC heuristic's, `vendors/sec/sic.py`): Technology XLK,
Health Care XLV, Financials XLF, Consumer Discretionary XLY, Consumer Staples XLP, Energy XLE,
Industrials XLI, Materials XLB, Utilities XLU, Real Estate XLRE, Communication Services XLC.

| Column | Definition | Null when |
|---|---|---|
| `rs_spy_63d`, `rs_spy_252d` (>= -1) | (1 + the instrument's n-session return) / (1 + SPY's) - 1 | either return is unknown, or SPY is not in the symbol map |
| `rs_line_high_252d` (flag) | the line close / SPY close is at its highest of the last 252 sessions, today included (a tie counts) | the line is unknown on a session among the 252, or SPY is not in the symbol map |
| `rs_spy_trend_20d` | `rs_spy_63d` today - `rs_spy_63d` 20 sessions earlier (above 0: relative strength improving) | either is unknown (84 closes of the instrument and SPY must be whole) |
| `ret_5d_pctile`, `mom_pctile_63d`, `mom_pctile_252d` (0..1) | the share of universe members with a known n-session return strictly below the instrument's, among members with a known one | no universe snapshot on or before the session, fewer than `min_coverage` of its members have a bar on the session (a partial day), fewer than `min_members` members have the return, or the instrument's return is unknown |
| `sector_etf` | `SECTOR_ETFS[sector]` | the company snapshot on or before the session has no sector for the instrument, the universe lists it as an ETF (a fund's SIC code is not a sector), or the sector has no ETF |
| `sector_ret_63d` (>= -1) | the sector ETF's 63-session return | `sector_etf` is null, or the ETF is not in the symbol map or has no complete window |
| `rs_sector_63d` (>= -1) | (1 + the instrument's 63-session return) / (1 + `sector_ret_63d`) - 1 | `sector_ret_63d` is null, or the instrument's return is unknown |
| `sector_rank_63d` (1..11) | the rank of the instrument's ETF among the 11 by 63-session return: 1 the strongest; ties share the better rank | `sector_ret_63d` is null, or fewer than `min_sector_etfs` of the 11 ETFs have a complete window |

The population rule is `market_breadth@v1`'s: the members are the STOCK rows (common stocks
and ADRs) of the universe snapshot the session sees; with none on or before the session (a
later list would count today's survivors) every percentile is null. An instrument's own row is
ranked whether or not it is a member (an ETF, or a stock outside the universe, is placed
among the members); a member is counted only with a complete window for that column, so a
name without one is neither below nor above anything. "Strictly below" makes the best member
read (n - 1) / n, never 1, and ties share the lower rank. The sector comes from the company
snapshot on or before the session (`data.reference.companies`' rule: none before the first,
never a later one). `ret_5d_pctile` uses the 5-session return, 63 sessions is a quarter (as the
relative-strength columns; `price_stats` has 60).

Expression features (`price.toml`): `rs_spy_positive` (`rs_spy_63d` > 0), `rs_improving`
(`rs_spy_trend_20d` > 0) and `sector_leader` (`sector_rank_63d` <= 3).

Worked example: SPY 100 -> 110 over 63 sessions (+10%), a stock 100 -> 121 (+21%):
`rs_spy_63d` = 1.21 / 1.10 - 1 = 0.10. A month earlier the stock stood +10% against SPY's +5%
over its own 63 sessions: 1.10 / 1.05 - 1 = 0.0476, so `rs_spy_trend_20d` = 0.10 - 0.0476 =
0.0524 (improving). With five members whose 63-session returns are -10%, 0%, 0%, 5% and 21%,
the stock's `mom_pctile_63d` is 4 / 5 = 0.8, a member at 0% reads 1 / 5 (its tie is not below
it) and a non-member at +100% reads 5 / 5. If its sector is Technology and XLK is +10% while
XLV is -5%: `sector_etf` XLK, `sector_ret_63d` 0.10, `rs_sector_63d` 0.10 and
`sector_rank_63d` 1 (XLV is 2).

## Levels (`levels/`), volume at price, options

`pivot_strength@v1`, `retest@v1` and `gaps@v1` are built; their definitions, null rules and
worked examples are in [swing.md](swing.md) (with `swing_levels@v1`, which they build on). The
rest is planned; each lands with its own section here (definitions, null rules, a worked
example) in the PR that builds it.
