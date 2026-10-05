# Swing levels and momentum (SW track)

Support, resistance and momentum from stored daily bars, plus earnings dates and chain open
interest for two of them. Each feature is one sentence the owner can check against a chart.
Roadmap: SW0 to SW4 in [roadmap.md](../roadmap.md); every column's generated entry is in
[features.md](features.md).

## Where the columns live

`features/rollups/` was at its 10-module cap, so it is split by kind (`price/`, `options/`,
`corporate/`) rather than re-versioning `price_stats@v2` (a `v3` would cascade to
`dividends@v2`, `fundamentals@v2` and `div_yield@v1` for no change in their values). New
groups:

| Group | Folder | Columns |
|---|---|---|
| `momentum@v1` | `price/` | `atr_14`, `rsi_14`, `ret_5d`, `rel_volume`, `high_20d`, `low_20d`, `high_50d`, `low_50d`, `prior_high_20d` |
| `swing_levels@v1` | `price/` | `swing_high`, `swing_high_date`, `swing_low`, `swing_low_date` |
| `anchored_vwap@v1` | `price/` | `avwap_earnings`, `avwap_anchor_date` |
| `oi_walls@v1` | `options/` | `wall_status`, `call_wall`, `call_wall_oi`, `put_wall`, `put_wall_oi` |

A formula over stored columns is an expression feature in `config/site/features/swing.toml`
(computed on read): `atr_pct`, `range_20d_pct`, `trend_state`, `dist_to_resistance`,
`dist_to_support`, `dist_to_resistance_atr`, `dist_to_support_atr`, `breakout_20d`,
`pullback_to_sma20`. Reused, not repeated: `price_stats` `close`, `sma_20/50/200`,
`high_52w`, `low_52w`, `ret_20d/60d`, `hv20/30`.

## Shared rules

- Bars are `bars/1d` split-adjusted as of the session (prices divided and volume multiplied
  by later splits up to the session, never after it), as `price_stats` reads them.
- Windows are exchange sessions. A window statistic is null (UNKNOWN), never a shorter
  window, unless every session in it has a bar. Null is never zero.
- Point in time: the value for session d uses bars up to d only, so appending later bars
  never changes it, and a backfill equals the nightly value.
- Rows exist only for instruments with a bar on the session (chain groups: a chain or an
  underlying quote on the session).

## Definitions

**`atr_14`** (usd per share). True range `TR_t = max(H_t - L_t, |H_t - C_t-1|, |L_t -
C_t-1|)`. Wilder smoothing: seed with the mean of the first 14 TRs, then `ATR_t = (13 x
ATR_t-1 + TR_t) / 14`. The recursion runs over the consecutive bars ending on the session,
at most the last 150 sessions (a fixed warm-up so the value depends on bars up to d only; the
seed's weight after 136 steps is (13/14)^136, about 4e-5, so it matches a charting tool's
full-history value to that tolerance). Null with fewer than 15 consecutive bars (14 TRs).
Example: 14 TRs of 1.00 then a TR of 15.00 gives `(13 x 1 + 15) / 14 = 2.00`.

**`rsi_14`** (0 to 100). Close changes over the same run; Wilder averages of gains and losses
(seed: the mean of the first 14, then `(13 x avg + x) / 14`); `RSI = 100 - 100 / (1 +
avg_gain / avg_loss)`; 100 when `avg_loss` is 0 and `avg_gain` is not; null when both are 0
(the price never moved: 0/0 is undefined, not neutral) or with fewer than 15 consecutive
bars. Example: changes alternating +2, -1 for 14 sessions give 1.0 / 0.5, RSI 66.67; a next
change of +3 gives `(13 + 3) / 14` over `6.5 / 14`, RSI 71.11.

**`ret_5d`** (decimal). Close / close 5 sessions earlier - 1; null unless all 6 sessions
have a bar. Example: 100 to 103 is 0.03.

**`rel_volume`** (ratio). Today's volume / the mean volume of the 20 sessions before today
(today excluded, so a spike is measured against normal trading). Null unless all 21 sessions
have a bar, or when that mean is 0. A zero-volume day is 0, not null. Example: prior mean
1.0M, today 1.8M gives 1.8.

**`high_20d`, `low_20d`, `high_50d`, `low_50d`** (usd per share). Highest high / lowest low
over the last 20 (50) sessions, today included (the usual Donchian channel). Null with a gap.

**`prior_high_20d`** (usd per share). Highest high over the 20 sessions before today (today
excluded). Added for `breakout_20d`: today's high is at least today's close, so a close can
never exceed a high that includes today.

**`atr_pct`** (decimal) = `atr_14 / close`. Example: ATR 2.00 at close 100 is 0.02.

**`range_20d_pct`** (decimal) = `(high_20d - low_20d) / close`. Example: 110 and 100 at
close 105 is 0.0952.

**`trend_state`** (label UPTREND / DOWNTREND / MIXED). UPTREND when `close > sma_50 >
sma_200`, DOWNTREND when `close < sma_50 < sma_200`, else MIXED (an equality is MIXED). Null
when `sma_50` or `sma_200` is null. Example: 105, 100, 95 is UPTREND; 105, 95, 100 is MIXED.

**Pivots** (`swing_levels`). Pivot width 5 bars each side. Bar t is a swing high when its
high is strictly above each of the 5 highs before it and at least each of the 5 highs after
it (a flat top counts once, at its first bar); a swing low mirrors it with lows. All 11 bars
must exist. A pivot at t is confirmed only at t + 5, so on session d only pivots with t <= d -
5 count. The bars read are the last 252 sessions (d - 251 to d), and a pivot needs its 5 bars
each side among them, so a pivot can be dated d - 246 to d - 5. Example: highs 101, 102, 103, 104,
105, **110**, 105, 104, 103, 102, 101 make a swing high of 110 at the sixth bar, known from the
eleventh bar's session on, not before.

**`swing_high`** (resistance) is the high of the most recent confirmed swing high strictly
above the session's close, with `swing_high_date` its session; null when none in the window
(for example at a one-year high). **`swing_low`** (support) is the low of the most recent
confirmed swing low strictly below the close, with `swing_low_date`. So `swing_high > close
> swing_low` whenever they are not null. Example: confirmed swing highs 110 (30 sessions ago)
and 104 (10 sessions ago): at close 102 resistance is 104; at close 106 it is 110.

**`dist_to_resistance`** = `(swing_high - close) / close`, **`dist_to_support`** =
`(close - swing_low) / close` (decimals, both >= 0). **`_atr` variants** divide the same
difference by `atr_14` instead. Example: swing high 104, close 102, ATR 2.00 gives 0.0196 and
1.00.

**`breakout_20d`** (flag) = `close > prior_high_20d and rel_volume > 1.5`. Example: prior
high 110, close 111, rel_volume 1.8 is true; with rel_volume 1.2 false. Three-valued: false
when either side is false, null when one is unknown and the other is not false.

**`pullback_to_sma20`** (flag) = `trend_state == "UPTREND" and |close - sma_20| <= 1 x
atr_14`. The band is symmetric: a close up to 1 ATR above or below SMA20 counts (edges
included). Above SMA20 by more than 1 ATR is an extended uptrend, not a pullback; below it by
more than 1 ATR is a breakdown risk. Example: SMA20 100, ATR 2.00: closes 98 to 102 qualify,
103 does not.

**`avwap_earnings`** (usd per share). Volume-weighted mean of the typical price `(H + L + C)
/ 3` from the anchor session through the session. The anchor is the most recent report date
known on the session (the `earnings@v1` reading of `events/earnings` snapshots, moved or
cancelled dates dropped) whose anchor session is on or before the session: a report after
the close (`after_hours`) anchors on the next session; before the open (`pre_market`) or
unknown time anchors on the report date's session (an unknown time keeps the report day,
which holds the reaction for a pre-market report). `avwap_anchor_date` is that session. Null
when there is no such report, fewer than 2 sessions from anchor through the session, a
session in that range has no bar, the anchor is more than 126 sessions back, or the volume
sums to 0. Example: a report Monday after the close anchors Tuesday; Tuesday typical 10.00 on
100 shares and Wednesday typical 12.00 on 300 shares give `(1000 + 3600) / 400 = 11.50`.

**`call_wall`, `put_wall`** (usd per share) with `call_wall_oi`, `put_wall_oi` (count). Open
interest is summed per strike across every expiry 1 to 60 calendar days out (expiring today
excluded). The call wall is the strike at or above spot with the most call OI; the put wall
is the strike at or below spot with the most put OI. Ties go to the strike nearest spot.
Spot is the underlying quote captured with the chain. Cboe OI is an end-of-day figure
(OCC updates it once a day, overnight): the walls describe positioning at a close, not
intraday. `wall_status`: NO_SPOT, NO_CHAIN (no quotes for the underlying), NO_EXPIRY (none 1
to 60 days out), NO_OI (no positive OI on either side), PARTIAL (one wall), OK (both). A
missing OI counts as 0 in the sums. Example: spot 100, call OI 500 at 100, 800 at 105, 800
at 110 gives a call wall at 105 (tie, nearer spot); put OI 700 at 95, 300 at 90 gives a put
wall at 95.

## Changes from the proposal

- `prior_high_20d` is stored (needed by `breakout_20d`; the proposal's high_20d includes
  today).
- `atr_pct`, `range_20d_pct` and the distances are expression features, not group columns:
  the repo rule for a formula over stored features.
- Wilder ATR and RSI use a fixed 150-session warm-up instead of the whole history, so a value
  never depends on how far back the store goes.
- RSI is null, not 50, when the price never moved.
