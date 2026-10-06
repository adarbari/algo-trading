# ADR 0047: Macro series with vintages

**Status:** accepted (2026-10-06; architect design for the market regime track,
[market-regime-plan.md](../market-regime-plan.md)). Extends [0007](0007-point-in-time-data.md)
(a vintage is not the storage stamp), [0012](0012-data-vendors.md) (free sources first) and
[0039](0039-ingestion-workflows-dependencies-and-acceptance.md) (a non-critical step). Index
levels stored here are named under [0046](0046-market-entity-features-and-non-tradable-ids.md).

## Context
Recession-risk signals (yield curve history, credit spreads, claims, unemployment, NFCI, lending
standards) are economic series from FRED / ALFRED and a few published files (Fed EBP, OFR FSI,
EPU, Shiller). They are released late and revised: a backtest that reads today's value of a 2008
observation cheats. ALFRED gives every vintage of every observation (`realtime_start`).

## Decision
1. **Table `macro/series`**: grain `reference`, runs merge, key (`instrument_id`, `obs_date`,
   `vintage_date`). Columns: `instrument_id` (`MACRO:<id>` or `IDX:<id>`), `series`,
   `obs_date date!`, `vintage_date date!`, `value float64` (null for FRED "."),
   `vintage_kind string!` (`alfred` or `lagged`), plus the point-in-time columns. Partition: the
   run's session.
2. **`vintage_date` is separate from `knowledge_ts`.** `knowledge_ts` stays the storage stamp
   (ADR 0007: when we stored it; the row-stamping step overwrites it anyway). The vintage goes in
   its own column, exactly as `instruments/shares` keeps `filed`.
3. **Registry `config/site/macro.toml [[series]]`**: `key`, `source` (`fred` or `published`),
   `kind` (`macro` or `index`), `cadence`, `release_lag_days`, `pit` (`alfred` or `lag`),
   `transform` (`level`, `yoy`, `diff`), `licence`, `terms`; published files add `url`,
   `date_column`, `value_column`, `parser`. Typed in a new `config/site/macro.py`.
4. **Two adapters, one normalised shape** (`SERIES_COLUMNS`,
   `algotrade_sources/framework/series.py`): `vendors/fred/observations.py` `FredObservations`
   (the full realtime period, one row per value change; key from `ALGOTRADE_FRED_API_KEY`) and
   `vendors/published/csv_series.py` `PublishedSeries`, driven by the registry, with named
   parsers (e.g. `shiller_xls`) in `vendors/published/parsers.py`.
5. **Point in time.** With `pit = "lag"` (unrevised market series, and observations before
   ALFRED's first vintage) `vintage_date = obs_date + release_lag`, flagged `lagged`. The reader
   `data/macro.py` `series_as_of(reader, ids, session, lookback)` returns the latest vintage per
   (id, `obs_date`) with `vintage_date <= session`; a feature input reuses `_Snapshots` sorted on
   `vintage_date`; `Input.ids` lets a group load only its series; `Feature.inputs` accepts
   `series:<KEY>`, checked against the registry by a fitness test.
6. **Nightly.** Task `macro` (`apps/ingestion/.../tasks/macro/series.py`), a non-critical step
   before `market-rollups`. Acceptance `check_macro`: FAIL when more than
   `[quality] max_macro_stale_share` of the series have no observation newer than cadence + lag +
   2 days, or when a series' vintage count drops. Published files refetch by `cadence` until the
   weekly workflow lands. It reuses the Treasury curve's `Source` protocol, `Http`, the limiter,
   the run loop and skip-stored; recent curve slope comes from `rates/treasury`, FRED `T10Y3M`
   being the fallback labelled `curve_source`.

Rejected: `knowledge_ts` = the vintage's `realtime_start` (the plan's first idea: it breaks ADR
0007's meaning and the stamping step overwrites it); one adapter per published CSV (four
near-identical modules).

## Consequences
- A FRED outage or a moved CSV fails only the `macro` step; screens still run and regime inputs
  are UNKNOWN with a reason (ADR 0036).
- A property test checks no session ever sees `vintage_date > session`; the scorecard reports
  which episodes relied on `lagged` values.
- ICE BofA series carry `licence = "personal"` like IBKR features (ADR 0028).
