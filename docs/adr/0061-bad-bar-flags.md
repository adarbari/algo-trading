# ADR 0061: Bad bars are flagged, and reads drop the flagged ones

**Status:** accepted (2026-10-09, architect plan; the read path and the trusted-segment rule are
for architect review). Amends [0008](0008-backtests-read-only-from-stores.md) (what a read serves
when a stored bar is wrong) and [0016](0016-four-data-layers.md) (a read-time correction besides
splits and dividends); extends [0007](0007-point-in-time-data.md) (raw rows are never edited).
Code: `tasks/maintenance/bar_quality.py`, `data/prices.py`.

## Context
Early Tiingo bars of some names carry absurd closes with no split event: `EQ:TIINGO:US000000045374`
0.0015 -> 42.7 (13,777x, 2020-09-29), `EQ:BBG009NMGXS6` 0.001 -> 15.78 (11,850x, 2021-11/12),
`EQ:BBG02029KQD1` 2,000x (2020-08), `EQ:BBG021DN5TF5` 20,000x (2019-06). They became 25,735
forward outcomes above +300% at h = 60 since 2018, which the edge harness would read as winners.

## Decision
- **Raw bars are never edited.** A detector writes `events/bar_flag` (key `instrument_id` +
  `ts`, the bar's close; `reason` `BELOW_FLOOR` | `BAD_OHLC` | `UNEXPLAINED_JUMP`, `detail`,
  `status` `FLAGGED` | `CLEARED`; the latest row per key wins, so a later `CLEARED` retracts).
  The table is a fact of record about the stored bar: no `known_from`, read by event date.
- **Reads drop flagged bars** as splits are applied (ADR 0016): `bars`, `adjusted_bars`,
  `session_bars` and `window_closes` read the flags with the same `as_of` as the bars (`as_of`
  is the one pin: no knowledge leak) and drop the FLAGGED rows. A dropped bar is a missing bar,
  never a zero return. `SessionBars.flagged` lists `(instrument, session)` of what went; a
  backtest (`load_price_data`) that would lose a bar raises `MissingDataError` naming the flag
  (ADR 0008: missing data is an error).
- **What is flagged**, by `[quality]` thresholds in `sources.toml`: a close below
  `min_bar_close` (or not positive); high below low or close outside low..high; a one-day close
  ratio above `max_bar_jump` either way with no `events/split` row of the instrument within
  `split_window_sessions` bars cuts the series, and every segment but the trusted one is
  flagged. The trusted segment holds the most `source = "massive"` bars, none: the one holding
  the latest bar; a tie goes to the later segment. A one-bar spike that returns to its level is
  flagged alone. Zero volume is not flagged. The task FAILS (publishes nothing) when over
  `max_bad_bar_share` of the bars read are flagged.
- **Task** `bar-quality --from D [--to D]` (single run, rerunnable: it writes only changes and
  `CLEARED` rows for bars no longer flagged). Judgement is within the range read, so a rebuild
  reads from the first stored session.

## Q2: flags travel with the bars, outcomes say UNMEASURED (2026-10-09)
- `bars-history` stages the flags of the names it fetched (the detector over the stored bars plus
  the rows it adds, with the splits it stages) and publishes them with the same run's bars, all
  or none; a flag found is a WARN in the run stats, never a failure. A nightly `bar-quality` step
  (after `bars` and `corporate-actions`, which explain real splits) checks the trailing 60
  sessions; an `UNEXPLAINED_JUMP` flag is cleared only by a run that starts at the instrument's
  first bar.
- `outcomes/instrument/forward_returns@v2` (the grain is renamed: the v1 table is a different
  schema and is never read again; nothing is deleted by this change). A name with a flagged bar
  in S..T (S included: a flagged S is eligible) has `outcome_status = UNMEASURED`,
  `outcome_reason = BAD_BAR`, and null returns (`fwd_return`, `fwd_max_return`,
  `fwd_max_drawdown` are nullable). The harness excludes it like a screen it could not measure
  (`excluded_coverage`, "unmeasured, not a miss"); the winners labels count it as no row. The
  acceptance check FAILS a COMPLETE row over `[quality] max_bounded_return` at a horizon of at
  most 60 sessions (a bad bar no flag explains).
- Rollups: a dropped bar is a missing bar, so a window needing it is null by each group's gap
  rule; groups that tolerate a few missing bars (52-week range, volume profile) use the others.

## Consequences
## Consequences
The trusted-segment rule can flag good bars when a name's only Massive bars are on the wrong
side of a real jump; the flag's `detail` names the trusted segment and a later `CLEARED` row
corrects it.
