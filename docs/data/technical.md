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

## Where the columns live

`features/rollups/price/` is at its module cap, so the new kinds get their own folders (one
folder per kind of thing; `architecture/layout.toml`):

| Group | Folder | Columns | Status |
|---|---|---|---|
| `bands@v1` | `price/` | `close_std_20`, `ema_20`, `bb_width_pctile_252d`, `band_walk` | built |
| `trend_stats@v1` | `price/` | `ret_120d`, `ret_252d`, `mom_12_1`, `ret_z_20d`, `close_streak`, `sma20_streak`, `tight_range_sessions` | built |
| `swing_levels@v1` | `levels/` (moved from `price/`) | unchanged | planned |
| `pivot_strength@v1` | `levels/` | `resistance_touches`, `support_touches`, `resistance_age`, `support_age`, `pivot_structure` | planned |
| `retest@v1` | `levels/` | `breakout_date`, `breakout_level`, `sessions_since_breakout`, `retest_state` | planned |
| `gaps@v1` | `levels/` | `gap_open_pct`, `gap_above`, `gap_above_date`, `gap_below`, `gap_below_date` | planned |
| `volume_profile@v1` | `levels/` | `poc_252d`, `value_area_high`, `value_area_low`, `hvn_above`, `hvn_below`, `lvn_above`, `lvn_below`, `volume_near_close_share`, `profile_status` | planned |
| `anchored_vwap@v2` | `price/` | v1 + `avwap_swing_low`, `avwap_swing_high` | planned |
| `relative_strength@v1` | `relative/` | `rs_spy_63d`, `rs_spy_252d`, `rs_line_high_252d`, `mom_pctile_63d`, `mom_pctile_252d`, `sector_etf`, `sector_ret_63d`, `rs_sector_63d`, `sector_rank_63d` | planned |
| `chain_flow@v1`, `flow_history@v1`, `skew@v1`, `skew_history@v1`, `implied_move@v1`, `iv_term@v1` | `positioning/` | [positioning.md](positioning.md) | planned |
| `call_wing@v1` | `options/` | the covered-call mirror of `put_wing@v1` | planned |
| `dividend_schedule@v1` | `corporate/` | `next_ex_date`, `next_div_amount`, `days_to_ex_date` | planned |

Formulas over stored columns are expression features (computed on read):
`config/site/features/bands.toml` (bands, channels, z-scores, stretches),
`swing.toml` (level distances and setups), `price.toml` (relative strength),
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

Inputs: `bars/1d`, the session plus 270 earlier sessions (252 bandwidths of 20 closes each,
and the EMA warm-up).

| Column | Definition | Null when |
|---|---|---|
| `close_std_20` | sample standard deviation (ddof 1) of the last 20 closes, the session included | a gap among the last 20 sessions, or a shorter history |
| `ema_20` | exponential moving average of the close, alpha 2 / 21, seeded with the mean of the first 20 closes of the consecutive run of bars ending on the session (at most the last 150 sessions; the seed's weight after 130 more bars is under 1e-5) | fewer than 20 consecutive bars ending on the session |
| `bb_width_pctile_252d` | share of the 252 sessions before the session whose Bollinger bandwidth (4 x close_std_20 / sma_20) was strictly below the session's: 0.05 is a squeeze (narrower than 95% of the year), 0.95 an expansion | the session's bandwidth is unknown, or fewer than 240 of the 252 sessions before have one |
| `band_walk` | signed count of consecutive sessions, ending on the session, with the close above the upper Bollinger band (positive) or below the lower (negative); 0 inside the bands | the session's bands are unknown (the count stops at the first session without bands) |

Expression features (`bands.toml`), with `k = 2` (Bollinger) and `m = 2` (Keltner, over
`atr_14`; the classic uses ATR(10): same reading, one window fewer to store):
`bb_upper`, `bb_lower`, `bb_width`, `bb_pct_b`, `kc_upper`, `kc_lower`, `kc_position`,
`bb_squeeze` (both Bollinger bands inside the Keltner channel: the TTM squeeze), `price_z_20d`
((close - sma_20) / close_std_20), `stretch_sma20_atr`, `stretch_sma50_atr` ((close - SMA) /
atr_14), `donchian_pos_20d` ((close - low_20d) / (high_20d - low_20d)).

Worked example: closes 100, 101, ..., 119 (20 bars): sma_20 109.5, close_std_20 5.916;
bb_upper 121.33, bb_lower 97.67, bb_width 0.2161, bb_pct_b (119 - 97.67) / 23.66 = 0.9014,
price_z_20d 1.606.

## `trend_stats@v1` (price/)

Inputs: `bars/1d`, the session plus 252 earlier sessions. Param `tight_range_pct` (0.15).

| Column | Definition | Null when |
|---|---|---|
| `ret_120d`, `ret_252d` | close / close n sessions earlier - 1 | a gap among the last n + 1 sessions, or a shorter history |
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

## Levels (`levels/`), volume at price, relative strength, options

Planned; each lands with its own section here (definitions, null rules, a worked example) in
the PR that builds it.
