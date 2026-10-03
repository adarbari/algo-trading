# ADR 0007: Point-in-time data and versioned features

**Status:** accepted (2026-10-02); amended 2026-10-02 (restructure R2: what `as_of` means,
the snapshot rule, events by event date)

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
