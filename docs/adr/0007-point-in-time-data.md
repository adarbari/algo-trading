# ADR 0007: Point-in-time data and versioned features

**Status:** accepted (2026-10-02)

## Context
Vendors revise data, index membership changes, and feature logic evolves. Without
point-in-time data, backtests silently use information that was not available at the time.

## Decision
- Every market and feature row has `ts` (event time), `knowledge_ts` (when we learned
  it), `source` and `run_id`.
- Readers accept `as_of`. Backtests for date D read with `as_of` set to the end of D.
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
