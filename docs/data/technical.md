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
| | skew, skew rank, expected move, term structure | `skew.skew`, `feature.skew_rr25`, `skew_history.skew_rank_252d`, `implied_move.implied_move`, `feature.term_ratio_30_90`, `feature.term_ratio_next_30` (positioning.md; built) |
| | strike distance from support, / ATR | `feature.put_support_cushion` ((best put strike... see swing.toml: (swing_low - best_put_strike) / close) and `feature.put_support_cushion_atr` (/ atr_14) |
| | covered call: strike above the close, above resistance, premium yield | `call_wing` (`best_call_strike`, `best_call_yield`), `feature.call_otm_pct`, `feature.cc_yield_annualised`, `feature.call_strike_above_resistance`, `feature.cc_resistance_cushion_atr` |
| | ex-dividend before expiry (early assignment, a dividend a put misses) | `dividend_schedule.next_ex_date`, `feature.ex_div_before_expiry` (the put / call wing's target expiry), `feature.ex_div_before_nearest_expiry` |
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
| `ps_ratio`, `net_margin`, `payout_ratio` | `fundamentals.toml` expressions over stored facts | built |
| quarterly EPS and revenue growth yoy (CAN SLIM C / A) | `financials@v2` | built |
| `shares_change_yoy` (buybacks / dilution) | `fundamentals@v3` | built |
| balance-sheet and cash-flow facts (equity, assets, debt, OCF, capex, gross profit) and `roe`, `roa`, `pb_ratio`, `debt_to_equity`, `fcf_yield`, `gross_profitability` | `balance_sheet@v1` (corporate/; the companyfacts document is already fetched whole) | planned |
| unusual options activity at chain level (`unusual_contracts`, `max_vol_oi_ratio`, `unusual_premium_usd`) | `chain_flow@v1` (positioning.md) | planned |
| `iv30_chg_1d`, `iv30_chg_5d` | `iv_history@v3` | planned |
| bar shape (body and wick shares, inside / outside bar) and the six named candles (hammer, shooting star, doji, bullish / bearish engulfing, inside-day breakout) | `candle@v1`, new folder `patterns/` | built |

Left out as window variants or covered: IBD's RS rating (the percentiles cover it), RSI(2),
CCI / MFI / stochastics, Hurst and efficiency ratios, the other TA-Lib candles, chart-pattern
scans (no deterministic daily-bar definition), per-name drawdown and Ulcer index, Amihud.
Needing a new data source (a vendor decision, `add-data-source`, not a feature): short
interest and days to cover (FINRA files, free), float and insider / institutional ownership
(EDGAR Form 4 / 13F), analyst estimates and surprises (forward P/E, PEG, SUE), dark pool.

## Presets

The eight rule screens the owner described (2026-10-06) are site presets
(`config/site/presets/screeners/<id>/v1.toml`, `add-screener`; rule grammar in
[rules.md](../screeners/rules.md)), each criterion a catalogue field with the owner's number
or the field guide's threshold. Each opens with the site base gates (security type, ACTIVE,
price > $5, ADV >= $50M as a soft `LIQUIDITY_RISK` near miss); `feature.liquidity_class` is
not used, because it bundles option liquidity (a liquid stock with no options is LOW) and
these are stock-chart screens. Every criterion is hard unless marked. Where a line has no
field, it is left out and said so in the preset's header comment.

| Preset | Setup (beyond the base gates) | Left out or approximated |
|---|---|---|
| `breakout` | `breakout_magnitude_20d` > 0; `dist_to_high_50d` >= -3%; `ret_5d`, `ret_20d`, `mom_accel_5d` > 0; `rel_volume` > 1.25; `atr_ratio_5_20` >= 1.1; `close_range_pos` > 0.7; `stretch_sma20_atr` <= 3 (soft) | "volume above the 20-session average" (implied by `rel_volume`); the 20 EMA stretch is measured from the SMA20 |
| `pullback` | `ret_20d`, `ret_60d` > 0; `ema_stack` BULL; `stretch_sma20_atr` in [-0.5, 0.5] (soft); `pullback_atr_20d` <= 1.5; `sessions_since_high_20d` <= 10; `volume_ratio_5d_20d` < 1; `dist_to_support_atr` <= 1; `trend_state` UPTREND; `mom_accel_5d` >= -0.03 (soft); `rs_spy_63d` > 0 | the 50-session return is `ret_60d`; the EMA20 distance is from the SMA20; "volume below the advance" is the 5 / 20-day ratio below 1 |
| `support_reversal` | `dist_to_support_atr` < 0.5; `support_touches` >= 2; `ret_5d` < 0; `mom_accel_5d` > 0; `ret_1d` > 0; `close_range_pos` > 0.6; `rel_volume` >= 1; `rs_spy_trend_20d` > 0; `put_support_cushion_atr` >= 1 (score, the put seller's cushion) | none |
| `exhaustion` (reversal) | `ret_5d_pctile` >= 0.9; `stretch_sma20_atr` > 2; `rsi_14` > 70; `rel_volume` > 1.5; `atr_ratio_5_20` > 1.1; `bb_pct_b` >= 0.95; `mom_accel_5d` < 0 | the continuation case is the same screen with `mom_accel_5d` > 0 (copy it in the Builder) |
| `trend_continuation` | `ema_stack` BULL; `ret_20d`, `ret_60d` > 0; `rs_spy_63d` > 0; `pct_vs_ema_20` > 0; `atr_ratio_5_20` >= 0.8 | the 50-session return is `ret_60d` |
| `range_breakout` | `atr_ratio_5_20` <= 0.85; `bb_width_pctile_252d` <= 0.15; `dist_to_resistance_atr` <= 1; `rel_volume` >= 1.2; `mom_accel_5d` > 0 and `ret_5d` > 0 | none (nothing confirms the direction of the break) |
| `failed_breakout` | `breakout_failed` true; `sessions_since_breakout` <= 10 (soft, 5 tolerance); `rel_volume` >= 1.2; `mom_accel_5d` < 0; `dist_to_resistance_atr` <= 1 | "yesterday above the 20-session high, today below" is approximated by `breakout_failed` (any close below the level since the latest breakout of the last 60 sessions) plus the recency gate |
| `oversold_reversal` | `ret_5d_pctile` <= 0.1; `rsi_14` < 30; `dist_to_support` > 0; `pct_vs_sma_200` > 0 (soft, 5 pts) and `trend_state` != DOWNTREND (score); `mom_accel_5d` > 0; `volume_z_20d` >= 2 (`rel_volume` >= 1.5 scores); `ret_1d` > 0 | the "or" in the volume spike: one field gates, the other scores; `dist_to_support` > 0 also drops names at a one-year low (no swing low below) |

A preset is an identification layer, not a trade signal: none checks earnings, news or the
market regime.

## Where the columns live

`features/rollups/price/` is at its module cap, so the new kinds get their own folders (`relative/` holds the groups that compare an instrument with the market, its sector and the universe) (one
folder per kind of thing; `architecture/layout.toml`):

| Group | Folder | Columns | Status |
|---|---|---|---|
| `bands@v2` | `price/` | `ema_10/20/50/200`, `sma_150`, `ema20_slope_5d`, `ema50_slope_10d`, `sma200_slope_20d`, `close_std_20`, `bb_width_pctile_252d`, `band_walk` | built |
| `trend_stats@v2` | `price/` | `ret_1d/3d/10d/120d/252d`, `mom_12_1`, `mom_accel_5d`, `ret_z_20d`, `high_100d`, `low_100d`, `high_200d`, `low_200d`, `prior_high_50d`, `prior_low_20d`, `prior_low_50d`, `sessions_since_high_20d`, `close_range_pos`, `trend_r2_90d`, `reg_slope_90d_ann`, `close_streak`, `sma20_streak`, `tight_range_sessions` | built |
| `candle@v1` | `patterns/` | `body_share`, `upper_wick_share`, `lower_wick_share`, `body_vs_avg_20d`, `bar_relation`, `prev_bar_relation`, `candle` | built |
| `swing_levels@v1` | `levels/` (moved from `price/`) | unchanged | built |
| `pivot_strength@v1` | `levels/` | `resistance_touches`, `support_touches`, `resistance_age`, `support_age`, `pivot_structure` | built ([swing.md](swing.md)) |
| `retest@v1` | `levels/` | `breakout_date`, `breakout_level`, `sessions_since_breakout`, `retest_state`, `failed_breakouts_252d` | built ([swing.md](swing.md)) |
| `gaps@v1` | `levels/` | `gap_open_pct`, `gap_above`, `gap_above_date`, `gap_below`, `gap_below_date` | built ([swing.md](swing.md)) |
| `vol_stats@v1` | `activity/` | `atr_5`, `atr_20`, `hv10`, `hv60`, `hv20_pctile_252d`, `adv_shares_60d`, `volume_pctile_252d`, `pocket_pivot` | built |
| `volume_profile@v1` | `activity/` | `profile_status`, `poc_252d`, `value_area_high`, `value_area_low`, `hvn_above`, `hvn_below`, `lvn_above`, `lvn_below`, `volume_near_close_share` | built |
| `anchored_vwap@v2` | `price/` | v1 + `avwap_swing_low`, `avwap_swing_high` | built |
| `relative_strength@v1` | `relative/` | `rs_spy_63d`, `rs_spy_252d`, `rs_line_high_252d`, `rs_spy_trend_20d`, `ret_5d_pctile`, `mom_pctile_63d`, `mom_pctile_252d`, `sector_etf`, `sector_ret_63d`, `rs_sector_63d`, `sector_rank_63d` | built |
| `chain_flow@v1`, `flow_history@v1`, `skew@v1`, `skew_history@v1`, `implied_move@v1`, `iv_term@v1` | `positioning/` | [positioning.md](positioning.md) | built |
| `call_wing@v1` | `options/` | the covered-call mirror of `put_wing@v1` (shared search in `wing_search`): `wing_status`, `target_expiry`, `target_dte`, `n_unpriced`, `n_strikes`, `wing_oi`, `wing_volume`, `wing_spread_pct`, `delta_band_distance`, `best_call_strike`, `_delta`, `_iv`, `_mid`, `_oi`, `_volume`, `_spread_pct`, `_yield` | built |
| `dividend_schedule@v1` | `corporate/` | `dividend_status`, `next_ex_date`, `next_div_amount`, `days_to_ex_date`, `next_pay_date` | built |
| `financials@v2` | `corporate/` | v1 + `eps_diluted_ttm_year_ago`, `revenue_qtr`, `revenue_qtr_year_ago`, `eps_diluted_qtr`, `eps_diluted_qtr_year_ago`, `qtr_as_of` | built |
| `fundamentals@v3` | `corporate/` | v2 + `shares_outstanding_year_ago` | built |

Formulas over stored columns are expression features (computed on read):
`config/site/features/bands.toml` (bands, channels, z-scores, stretches),
`swing.toml` (level distances, the pullback in ATRs, the 52-week position, the 50-session breakout and
20-session breakdown, the short put's cushion above support), `price.toml` (`rs_spy_positive`,
`rs_improving`, `sector_leader`),
`positioning.toml` (flow ratios, skew, term structure, implied move), `wings.toml` (the covered call's
strike distance and annualised yield, its strike against resistance; its cushion in ATRs is in
`swing.toml` beside the put's), `earnings.toml` (scheduled events against expiries: earnings and
ex-dividend dates).

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

## `candle@v1` (patterns/)

Inputs: `bars/1d`, the session plus 20 earlier sessions. Params (`config/site/rollups.toml`):
`doji_body` (0.1: a body at most this share of the range), `hammer_wick` (2.0: the long wick at
least this many bodies), `small_body` (0.3: the other wick at most this share of the range),
`engulf_min_body` (0.5: an engulfing body at least this many 20-session average bodies). Every
column reads the session's open, high, low and close (and the previous bar where said).

| Column | Definition | Null when |
|---|---|---|
| `body_share` | \|close - open\| / (high - low), 0 to 1 | the bar has no range |
| `upper_wick_share`, `lower_wick_share` | (high - max(open, close)) / range and (min(open, close) - low) / range, 0 to 1 | the bar has no range |
| `body_vs_avg_20d` | \|close - open\| / the mean \|close - open\| of the 20 sessions before; 1 is a usual body | a session among the 20 before has no bar, the history is shorter, or the mean is zero |
| `bar_relation` | INSIDE (high <= previous high and low >= previous low), OUTSIDE (high > previous high and low < previous low), UP_GAP (low > previous high), DOWN_GAP (high < previous low), else OVERLAP; tested in that order | the previous session has no bar |
| `prev_bar_relation` | the same label for the previous session against the one before it | the previous session or the one before has no bar |
| `candle` | the first matching of the order below, else NONE | the bar has no range, or the previous session has no bar |

Precedence of `candle`: (1) BULLISH_ENGULFING: close > open, previous close < previous open,
open <= previous close, close >= previous open, body >= `engulf_min_body` x the 20-session
average body; (2) BEARISH_ENGULFING: the mirror; (3) HAMMER: lower wick >= `hammer_wick` x body,
upper wick share <= `small_body`, body share > `doji_body`; (4) SHOOTING_STAR: the mirror with
the upper wick; (5) DOJI: body share <= `doji_body`; (6) NONE. An unknown average body never
matches an engulfing candle (the bar then reads on to the later tests; the label is not null
for it). The inside-day breakout is not a candle but the expression `inside_day_breakout`
(`ret_1d > 0` and `prev_bar_relation` INSIDE); `strong_close` is `close_range_pos >= 0.7` and
`body_share >= 0.5` (both in `config/site/features/swing.toml`).

Worked example: open 100, high 101.2, low 95, close 101 after 20 sessions of body 1: body
share 1 / 6.2 = 0.16, lower wick 5 (5 bodies, share 0.81), upper wick share 0.03: HAMMER;
`body_vs_avg_20d` 1.0.

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
`call_wing@v1` and `dividend_schedule@v1` are built (their sections are at the end of this page);
`pivot_strength@v1`, `retest@v1` and `gaps@v1` are built; their definitions, null rules and
worked examples are in [swing.md](swing.md) (with `swing_levels@v1`, which they build on). The
rest is planned; each lands with its own section here (definitions, null rules, a worked
example) in the PR that builds it.

## `call_wing@v1` (options/)

The covered call to sell at the 30-60 day expiry, the mirror of `put_wing@v1`: one search
(`options/wing_search.py`) for both rights, so the target expiry (closest to 45 days, standard
monthlies first), our delta (the mid inverted with `quant.implied_vol`, delta from
`quant.black_scholes.greeks`, `q` from `div_yield@v1`), the band distance and the statuses are
the put's. Inputs: the session's chain, the Treasury curve, the underlying quote, `div_yield@v1`.

| Column | Definition | Null when |
|---|---|---|
| `wing_status` | OK / OUTSIDE_BAND / NO_SPOT / NO_CHAIN (no call quotes) / NO_EXPIRY (none 30..60 days out) / NO_STRIKE (no call with our delta in 0.05..0.50) | never |
| `target_expiry`, `target_dte` | the expiry closest to 45 days within 30..60 | NO_SPOT, NO_CHAIN, NO_EXPIRY |
| `n_unpriced` | calls at it without our delta (no two-sided quote, or the inversion failed) | no target expiry |
| `n_strikes`, `wing_oi`, `wing_volume`, `wing_spread_pct` | strikes, open interest, volume and median relative spread of the calls with our delta in 0.15..0.30 (edges included); 0 when none (the spread: null) | no target expiry |
| `delta_band_distance` | the best call's distance from the band: 0 inside, else to the nearer edge | no candidate (NO_STRIKE or no target) |
| `best_call_strike`, `_delta`, `_iv`, `_mid`, `_oi`, `_volume`, `_spread_pct` | the best call: the candidate with the smallest distance, then the highest `best_call_yield`, then the higher open interest, then the higher strike | as the distance |
| `best_call_yield` | mid / the underlying's price: the premium per dollar of stock held, for the period (0.012 is 1.2% for 45 days) | as the distance |

Worked example: spot 100, 45 days, vol 40%, rate 4%: the calls with delta 0.15..0.30 are the
strikes 110..117 (110 is 0.283, 117 is 0.156), the best call is the lowest of them (the highest
premium): strike 110, mid 2.30, `best_call_yield` 0.023, `delta_band_distance` 0. With only 106
and 108 listed (both above 0.30 delta) the best call is 108, the nearer to the band, with
`wing_status` OUTSIDE_BAND and a distance of its delta (0.329) minus 0.30.

Expression features: `call_otm_pct` = (strike - close) / close; `cc_yield_annualised` =
`best_call_yield` x 365 / `target_dte`; `call_strike_above_resistance` = strike above
`swing_levels.swing_high`; `cc_resistance_cushion_atr` = (strike - swing high) / `atr_14`. The
yield and the early-assignment risk are separate questions: `ex_div_before_expiry` says a known
ex-dividend date falls before the target expiry (the dividend can be taken early from a
short call, an in-the-money one most of all).

## `financials@v2` / `fundamentals@v3` (corporate/)

Built from the SEC facts already stored (`instruments/shares`, point in time by filing date;
nothing new is fetched). Expressions over stored columns, no code: `ps_ratio` (market cap /
TTM revenue; null on a missing, zero or stale revenue), `net_margin` (net income / revenue
TTM), `payout_ratio` (`dividends.div_ttm` / EPS TTM: null when the EPS is 0, missing, stale or
an ADR; a negative value is a payer with negative earnings, so a safe-dividend rule is
`between 0 and 0.6`, never a bare `lt 0.6`).

`financials@v2` keeps every v1 column and adds the EPS TTM a year earlier
(`eps_diluted_ttm_year_ago`, the same assembly as `revenue_ttm_year_ago`: four quarters ending
340 to 380 days before the EPS TTM, or the previous fiscal year) and the latest quarter. The
quarter is the newest discrete quarter: a 10-Q's three-month figure as filed, or at a 10-K the
fourth quarter as the annual figure minus the nine months (one tag; both filed within 150 days
of each other, so a restated annual figure is not subtracted from an unrestated nine months),
which is public on the 10-K's filing date. It is null when the annual figure is newer than the
newest quarter (the Q4 cannot be derived: an older quarter would not be the latest), when the
quarter ended more than `stale_days` (480) before the session, and for a concept whose newest
quarter is older than the other's, so `qtr_as_of` is the one quarter every non-null quarter
column describes. `revenue_qtr_year_ago` / `eps_diluted_qtr_year_ago` are the discrete quarter
ending 340 to 380 days before it. Growth expressions: `eps_growth_yoy` (CAN SLIM A),
`revenue_growth_qtr_yoy` and `eps_growth_qtr_yoy` (C). Each is null when the base (the year-ago
EPS, quarterly or TTM) is 0 or negative: a growth rate from a loss is meaningless, so a
turnaround is UNKNOWN, never infinite. `revenue_growth_yoy` is unchanged.

`fundamentals@v3` keeps every v2 column and adds `shares_outstanding_year_ago`: among the facts
filed by the session, the count of the same concept as the current one (a cover count against a
cover count, a weighted average against a weighted average) whose period ended 9 to 15 months
before `shares_as_of`, the one closest to a year, split-adjusted to the session's share terms
(the split lookback covers the window, so a split between the two counts is not read as
dilution); null when there is none. `shares_change_yoy` is the ratio minus one: negative is
buybacks (1 to 5% a year is a steady repurchaser), above 0.10 is dilution. Backfill and
retirement of the v1 / v2 tables: the roadmap's "Backfills pending".

## `dividend_schedule@v1` (corporate/)

The next ex-dividend date known on the session, from the corporate-actions partitions stored by
it (the rules are under `dividend_schedule@v1` rules in [layers.md](layers.md)).

| Column | Definition | Null when |
|---|---|---|
| `dividend_status` | SCHEDULED (an ex-date after the session is known) / NOT_ANNOUNCED | never |
| `next_ex_date` | the earliest ex-date after the session in the rows stored by it | NOT_ANNOUNCED |
| `next_div_amount` | its cash amount per share, in the session's share terms (divided by the splits after the partition that stored it) | NOT_ANNOUNCED |
| `days_to_ex_date` | calendar days to it (>= 1) | NOT_ANNOUNCED |
| `next_pay_date` | its payment date | NOT_ANNOUNCED, or the source gives none |

Worked example: a run on session S stores `ex 2026-11-06, 0.25` for EQ:A. On S - 1 EQ:A is
NOT_ANNOUNCED (nothing stored yet); on S and every later session it is SCHEDULED with
`days_to_ex_date` counting down to 1. If a later run moves the date to 2026-11-13 the next
sessions read the new date, and a recompute of S still reads the old one. A 2:1 split
executing after the partition that holds the latest listing divides the amount by 2 (a later
listing carries the vendor's own number and is used as stored). `ex_div_before_expiry`
(`config/site/features/earnings.toml`) is null while no date is known: a date beyond the
30-day window is not listed yet, so null is never "no dividend".
