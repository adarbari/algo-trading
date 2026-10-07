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
| | EMA 10 / 20 / 50 / 200, SMA 150 | `bands` `ema_10/20/50/200`, `sma_150` (the 30-week average Minervini and Weinstein threshold; EMA 5 and SMA 5 / 10 / 100 left out: one short and one long average each is enough to state alignment; SMA 10 is `ema_10`'s twin) |
| | slopes | `bands` `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d` |
| | EMA alignment | `feature.ema_stack` (BULL / BEAR / MIXED over EMA 20 / 50 / 200; `trend_state` is the SMA version) |
| | distance from moving averages | `feature.pct_vs_sma_20/50/200`, `feature.pct_vs_ema_20/50/200`, `feature.stretch_sma20_atr`, `feature.stretch_sma50_atr` |
| Momentum | returns 1 / 3 / 5 / 10 / 20 / 60 / 120 / 252 | `trend_stats` `ret_1d`, `ret_3d`, `ret_10d`; `momentum.ret_5d`; `price_stats.ret_20d/60d`; `trend_stats` `ret_120d`, `ret_252d`, `mom_12_1` |
| | momentum acceleration | `trend_stats` `mom_accel_5d` (ret_5d today minus ret_5d five sessions earlier; negative = deteriorating) |
| | relative strength vs SPY / sector, percentile ranks | `relative_strength@v1` (planned): `rs_spy_63d`, `rs_sector_63d`, `rs_spy_trend_20d` (improving / deteriorating), `ret_5d_pctile`, `mom_pctile_63d`, `mom_pctile_252d` |
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
| | momentum deterioration / recovery | `trend_stats.mom_accel_5d`; `relative_strength.rs_spy_trend_20d` (planned) |
| Breakout quality | above the 20 / 50-session high, magnitude, volume | `feature.breakout_20d`, `feature.breakout_50d`, `feature.breakout_magnitude_20d`, `momentum.rel_volume`, `trend_stats.close_range_pos` |
| | ATR expansion | `feature.atr_ratio_5_20` |
| | follow-through, failed-breakout history | `retest@v1` (planned): `sessions_since_breakout`, `retest_state`, `failed_breakouts_252d` |
| Volume / liquidity | dollar volume, relative volume | `volume.dollar_volume`, `price_stats.adv_usd_20d`, `momentum.rel_volume`, `volume.volume_z_20d` |
| | volume trend / acceleration / percentile, turnover | `vol_stats` (planned) `adv_shares_60d`, `volume_pctile_252d`; `feature.volume_trend_20_60`; `feature.turnover_20d` (adv_shares_20d / shares_outstanding) |
| Market / sector regime | SPY / QQQ trend, market volatility, breadth | `market_trend@v2`, `market_breadth@v1`, `regime@v3` (`market.*`); IWM through `cross_asset.iwm_vs_spy` |
| | sector momentum, sector relative strength | `relative_strength@v1` (planned): `sector_etf`, `sector_ret_63d`, `sector_rank_63d`, `rs_sector_63d` |
| Options | IV, IV rank, IV percentile, IV / HV, IV - HV spread | `iv30`, `iv_rank`, `iv_percentile`, `iv_hv_ratio`, `iv_hv_spread`, the `vrp_*` set |
| | OI, option volume, spread, delta, DTE | `option_liquidity`, `put_wing`, `oi_walls`, `nearest_expiry` |
| | skew, expected move | `skew@v1`, `implied_move@v1` (planned, positioning.md) |
| | strike distance from support, / ATR | `feature.put_support_cushion` ((best put strike... see swing.toml: (swing_low - best_put_strike) / close) and `feature.put_support_cushion_atr` (/ atr_14) |
| Catalyst / risk | days to earnings | `earnings.days_to_earnings`, `feature.earnings_before_expiry` |
| | historical, worst and average earnings moves; news / catalyst flags | EV track (`own_sensitivity`: `move_multiple_median`, `down_move_worst_pct`, 8-K item flags); not duplicated here |

## Survey of other systems (2026-10-06)

A survey of the feature sets of TA-Lib, QuantConnect, Qlib, WorldQuant's alphas, Finviz,
TradingView, thinkorswim, Trade Ideas, TrendSpider, Minervini / IBD, Clenow, Connors and the
options screeners (Market Chameleon, Barchart, OptionStrat) against this catalogue (the full
table: `out/feature-gap-survey.md` in the working tree). What it adds to the track, by cost:

| Add | Where | Status |
|---|---|---|
| `sma_150` and `pct_vs_sma_150` (Minervini's template, Weinstein's 30-week average) | `bands@v2` | built (TA track 1b) |
| `trend_r2_90d`, `reg_slope_90d_ann`, `clenow_momentum_90d` (Clenow's trend quality and pace) | `trend_stats@v2` | built (TA track 1b) |
| `pocket_pivot` (Morales and Kacher) | `vol_stats@v1` | built |
| `ps_ratio`, `net_margin`, `payout_ratio` | `fundamentals.toml` expressions over stored facts | planned |
| quarterly EPS and revenue growth yoy (CAN SLIM C / A) | `financials@v2` | planned |
| `shares_change_yoy` (buybacks / dilution) | `fundamentals@v3` | planned |
| balance-sheet and cash-flow facts (equity, assets, debt, OCF, capex, gross profit) and `roe`, `roa`, `pb_ratio`, `debt_to_equity`, `fcf_yield`, `gross_profitability` | `balance_sheet@v1` (corporate/; the companyfacts document is already fetched whole) | planned |
| unusual options activity at chain level (`unusual_contracts`, `max_vol_oi_ratio`, `unusual_premium_usd`) | `chain_flow@v1` (positioning.md) | planned |
| `iv30_chg_1d`, `iv30_chg_5d` | `iv_history@v3` | planned |
| bar shape (body and wick shares, inside / outside bar) and the six named candles (hammer, shooting star, doji, bullish / bearish engulfing, inside-day breakout) | `candle@v1`, new folder `patterns/` | planned |

Left out as window variants or covered: IBD's RS rating (the percentiles cover it), RSI(2),
CCI / MFI / stochastics, Hurst and efficiency ratios, the other TA-Lib candles, chart-pattern
scans (no deterministic daily-bar definition), per-name drawdown and Ulcer index, Amihud.
Needing a new data source (a vendor decision, `add-data-source`, not a feature): short
interest and days to cover (FINRA files, free), float and insider / institutional ownership
(EDGAR Form 4 / 13F), analyst estimates and surprises (forward P/E, PEG, SUE), dark pool.

## Presets

Once the inputs above exist, the eight rule screens the owner described (breakout, pullback,
support reversal, exhaustion, trend continuation, range breakout, failed breakout, oversold
reversal) are site presets in `config/site/presets/` (`add-screener`), each criterion a
catalogue field with its guide threshold. They are the last PR of the track; a preset that
needs a field this table marks planned waits for that field.

## Where the columns live

`features/rollups/price/` is at its module cap, so the new kinds get their own folders (one
folder per kind of thing; `architecture/layout.toml`):

| Group | Folder | Columns | Status |
|---|---|---|---|
| `bands@v2` | `price/` | `ema_10/20/50/200`, `sma_150`, `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d`, `close_std_20`, `bb_width_pctile_252d`, `band_walk` | built |
| `trend_stats@v2` | `price/` | `ret_1d/3d/10d/120d/252d`, `mom_12_1`, `mom_accel_5d`, `ret_z_20d`, `high_100d`, `low_100d`, `high_200d`, `low_200d`, `prior_high_50d`, `prior_low_20d`, `prior_low_50d`, `sessions_since_high_20d`, `close_range_pos`, `trend_r2_90d`, `reg_slope_90d_ann`, `close_streak`, `sma20_streak`, `tight_range_sessions` | built |
| `swing_levels@v1` | `levels/` (moved from `price/`) | unchanged | planned |
| `pivot_strength@v1` | `levels/` | `resistance_touches`, `support_touches`, `resistance_age`, `support_age`, `pivot_structure` | planned |
| `retest@v1` | `levels/` | `breakout_date`, `breakout_level`, `sessions_since_breakout`, `retest_state` | planned |
| `gaps@v1` | `levels/` | `gap_open_pct`, `gap_above`, `gap_above_date`, `gap_below`, `gap_below_date` | planned |
| `vol_stats@v1` | `activity/` | `atr_5`, `atr_20`, `hv10`, `hv60`, `hv20_pctile_252d`, `adv_shares_60d`, `volume_pctile_252d`, `pocket_pivot` | built |
| `volume_profile@v1` | `activity/` | `profile_status`, `poc_252d`, `value_area_high`, `value_area_low`, `hvn_above`, `hvn_below`, `lvn_above`, `lvn_below`, `volume_near_close_share` | built |
| `anchored_vwap@v2` | `price/` | v1 + `avwap_swing_low`, `avwap_swing_high` | built |
| `relative_strength@v1` | `relative/` | `rs_spy_63d`, `rs_spy_252d`, `rs_line_high_252d`, `mom_pctile_63d`, `mom_pctile_252d`, `sector_etf`, `sector_ret_63d`, `rs_sector_63d`, `sector_rank_63d` | planned |
| `chain_flow@v1`, `flow_history@v1`, `skew@v1`, `skew_history@v1`, `implied_move@v1`, `iv_term@v1` | `positioning/` | [positioning.md](positioning.md) | planned |
| `call_wing@v1` | `options/` | the covered-call mirror of `put_wing@v1` | planned |
| `dividend_schedule@v1` | `corporate/` | `next_ex_date`, `next_div_amount`, `days_to_ex_date` | planned |

Formulas over stored columns are expression features (computed on read):
`config/site/features/bands.toml` (bands, channels, z-scores, stretches),
`swing.toml` (level distances, the pullback in ATRs, the 52-week position, the 50-session breakout and
20-session breakdown, the short put's cushion above support), `price.toml` (relative strength),
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

## `bands@v2` (price/)

Inputs: `bars/1d`, the session plus 399 earlier sessions (the EMA run, and 252 bandwidths of
20 closes each).

| Column | Definition | Null when |
|---|---|---|
| `close_std_20` | sample standard deviation (ddof 1) of the last 20 closes, the session included | a gap among the last 20 sessions, or a shorter history |
| `sma_150` | mean close over the last 150 sessions (the 30-week average) | a gap among them |
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

## `trend_stats@v2` (price/)

Inputs: `bars/1d`, the session plus 252 earlier sessions. Param `tight_range_pct` (0.15).

| Column | Definition | Null when |
|---|---|---|
| `ret_1d`, `ret_3d`, `ret_10d`, `ret_120d`, `ret_252d` | close / close n sessions earlier - 1 | a gap among the last n + 1 sessions, or a shorter history |
| `mom_accel_5d` | ret_5d today - ret_5d five sessions earlier | a gap among the last 11 sessions |
| `high_100d`, `low_100d`, `high_200d`, `low_200d` | the extreme over the last n sessions, the session included | a gap among the last n sessions |
| `prior_high_50d`, `prior_low_20d`, `prior_low_50d` | the extreme over the n sessions before the session (the session excluded): the level a breakout or breakdown close must clear | a gap among those n sessions |
| `sessions_since_high_20d` | sessions since the highest high of the last 20 (the latest of equal highs; 0: today) | a gap among the last 20 sessions |
| `close_range_pos` | (close - low) / (high - low) of the session's bar | the bar has no range |
| `trend_r2_90d`, `reg_slope_90d_ann` | the R-squared and the annualised slope (exp(slope x 252) - 1) of the least-squares line through the log close over the last 90 sessions (Clenow); `clenow_momentum_90d` is their product | a gap among the last 90 sessions; r2 also when the close never moved |
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

## `vol_stats@v1` (activity/)

Inputs: `bars/1d`, the session plus 272 earlier sessions.

| Column | Definition | Null when |
|---|---|---|
| `atr_5`, `atr_20` | Wilder ATR over n, as `momentum.atr_14` (seeded with the first n true ranges of the consecutive run ending on the session, at most 150 sessions) | fewer than n + 1 consecutive bars |
| `hv10`, `hv60` | close-to-close realised vol over n log returns, annualised by 252 (`quant.realized_vol`) | a gap among the last n + 1 sessions |
| `hv20_pctile_252d` | share of the 252 sessions before the session whose hv20 was strictly below the session's | the session's hv20 unknown, or fewer than 240 of the 252 have one (one gap voids 21 windows) |
| `adv_shares_60d` | mean share volume over the last 60 sessions | a gap among them |
| `volume_pctile_252d` | share of the 252 sessions before the session whose volume was strictly below the session's | fewer than 240 known |
| `pocket_pivot` | the close rose and the volume beat every down-close session's volume among the 10 before (Morales and Kacher); false on a down day or with no down day to beat | a gap among the last 12 sessions |

Expression features: `atr_ratio_5_20` (expansion above 1), `hv_ratio_10_60` (`volatility.toml`);
`volume_trend_20_60`, `turnover_20d` (adv_shares_20d / shares_outstanding; `volume.toml`).

## `volume_profile@v1` (activity/)

A daily-bar approximation of a volume profile. Inputs: `bars/1d`, the session plus 251 earlier
sessions; `momentum@v1` (atr_14). Params (`rollups.toml`): `bins` 50, `value_area` 0.70,
`hvn_factor` 1.5, `lvn_factor` 0.5, `min_bars` 240.

Each bar's volume is spread evenly over the `bins` equal price bins between the window's lowest
low and highest high that its [low, high] overlaps (a bar with no range goes to its bin). Then:
`poc_252d` the centre of the fullest bin (ties: nearest the close); the value area grows from
that bin one neighbour at a time towards the fuller side until it holds `value_area` of the
volume (`value_area_low` / `value_area_high` are its outer edges); `hvn_above` / `hvn_below` the
centre of the nearest bin strictly above / below the close's bin with at least `hvn_factor` x
the mean bin volume, `lvn_*` with at most `lvn_factor` x; `volume_near_close_share` the share
of volume in bins whose centre is within one atr_14 of the close. `profile_status` is OK,
FEW_BARS (under `min_bars` bars) or NO_RANGE (one price all year); every value is null unless
OK. Expression features: `in_value_area`, `dist_to_poc` (`swing.toml`).

Worked example (10 bins over 100..110): one-bin bars of 300 at 102-103, 250 at 103-104, 200 at
107-108, 20 at 105-106, 20 at 100-101, 10 at 109-110, close 105.5: POC 102.5; value area
102..106 (300 + 250 = 550 of the 560 needed, then the fuller neighbour, bin 4 with 0, then bin
5 with 20); HVN above 107.5, below 103.5; LVN above 106.5, below 104.5; within one ATR (1.0)
of the close 20 / 800 of the volume.

## `anchored_vwap@v2` (price/)

v1's `avwap_earnings` and `avwap_anchor_date` plus `avwap_swing_low` and `avwap_swing_high`:
the VWAP of the typical price from the session of `swing_levels@v1`'s swing low / high through
the session (null without that pivot, with fewer than 2 sessions, a gap or no volume in the
range). The bars read grow to 252 sessions so a pivot anywhere in `swing_levels`' window can
anchor. v1 is superseded; retire it after the backfill.

## Levels (`levels/`), relative strength, options

Planned; the levels groups are specified in [swing.md](swing.md) by the PR that builds them;
relative strength and the options groups land with their own sections here.
