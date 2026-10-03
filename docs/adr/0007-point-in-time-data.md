# ADR 0007: Point-in-time data and versioned features

**Status:** accepted (2026-10-02); amended 2026-10-02 (restructure R2: what `as_of` means,
the snapshot rule, events by event date); amended 2026-10-03 (how runs combine: event runs
merge)

## Context
Vendors revise data, index membership changes, and feature logic evolves. Without
point-in-time data, backtests silently use information that was not available at the time.

## Decision
- Every market and feature row has `ts` (event time), `knowledge_ts` (when we learned
  it), `source` and `run_id`.
- Readers accept `as_of`. **`as_of` is a version pin**, not a simulated "what we knew on
  D": a backtest reads data as stored at its launch time (`as_of` = launch time) and
  records that `as_of` and the run ids it read (`data_versions`) on its result, so it can be
  reproduced exactly after later ingestion runs or corrections. Tests inject the clock.
- Three times, three meanings: `ts` / `session_date` is the market date (when it happened),
  `knowledge_ts` is when we stored it, `as_of` picks the stored version.
- Snapshot tables (`instruments/reference`, `instruments/company`, `universe`,
  `instruments/id_map`) are read with one rule, `algotrade.data.reference.snapshot`: the
  latest snapshot on or before D, else the earliest available, flagged `pre_snapshot`. A
  backtest that starts before the first reference snapshot runs, but records
  `survivorship_bias: true` and the snapshot date (the instrument list is from later), and
  the CLI warns.
- Events are read by **event date** (`ts`), from whichever partition stored them (a backfill
  stores old splits in today's partition), keeping the latest `knowledge_ts` per event.
  True "known at the time" for events needs domain dates (declaration / announcement) and
  is a later refinement; until then a backtest sees every split and dividend in its window
  as stored at launch.
- Corrections are appended with a later `knowledge_ts`, never overwritten.

### How runs combine

A partition (`table`, `session_date`) can hold several runs. Each table declares how they
combine (`TableSpec.runs` in `storage/tables/schemas.py`); storage applies it
(`storage/backends/run_selection.py`, the one owner), so `table` / `table_range` already
return the combined view and every backend agrees (`tests/contract/storage/`).

- **`snapshot`**: every run is the partition's full contents, so the latest run known at
  `as_of` replaces the others. Reference, company, universe, bars (a re-fetched
  session replaces the earlier fetch), chains, rates, rollups, catalogues and results.
- **`merge`**: every run is a window or an increment, so a read unions all runs known at
  `as_of` and, per table key (`instrument_id`, `ts`, + `change`), the latest run's row
  wins. All `events/*` tables: the corporate-actions backfill (26 months) and the nightly
  -7..+30-day window land in the same session's partition, and picking one run hid the
  backfill (2026-10-03: AAPL / KO showed no trailing dividends). Also the cumulative
  instrument tables `instruments/id_map` and `instruments/symbol_history`, on their own key
  (`TableSpec.key`), so a partial re-run cannot hide recorded upgrades or history (ADR 0018).
- **Restating runs.** A run written with `restates=True` (`IngestRun.rewrite`, used by
  `migrate_ids`) holds the whole merged view as of its write; reads at or after it start
  from it, so rows it replaced (e.g. old symbol ids) are not resurrected. Reads pinned
  before it still see the old union. The flag lives in the partition's run index; plain
  runs keep the original index format.
- **No deletes yet.** Under `merge`, a later run that no longer contains an event (a
  cancelled dividend, a rescheduled earnings date within one session) does not remove it;
  a later row for the same key does replace it. Tombstones (an explicit "withdrawn" row)
  are future work, alongside true "known at the time" for events.
- Features are named `name@version`. Changing logic means a new version; old versions
  stay readable until explicitly retired.
- Features are **precomputed nightly** by ingestion. The pipeline takes a period
  parameter, so intraday runs later are a scheduling change.
- Feature definitions are a shared library, so research in `apps/backtest` can compute
  an experimental feature on the fly with exactly the same code.

## Consequences
- Storage is larger (history is kept), which is acceptable at our scale.
- The `FeatureView` handed to strategies and screeners enforces `as_of`, just as
  `MarketView` enforces the cursor today.
