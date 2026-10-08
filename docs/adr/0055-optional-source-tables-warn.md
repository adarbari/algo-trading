# ADR 0055: A screen that goes without an optional source's table warns, never fails

**Status:** accepted (2026-10-08; owner decision 2026-10-08). Amends
[0030](0030-rule-screener-simplification.md) (when a missing table makes a rule screen PARTIAL)
and [0039](0039-ingestion-workflows-dependencies-and-acceptance.md) (what fails the critical
`screens` step).

## Context
IBKR data (ADR 0028) comes from IB Gateway on the owner's Mac. When the gateway is down for the
latest session, `rollups/instrument/ibkr_iv@v1` has no partition for it. `vrp_scanner` reads
that table, through `feature.vrp_iv30` (`coalesce` of IBKR's IV30 with Cboe's) and directly in a
SCORE criterion. `read_expressions` reports a table as missing whenever a formula takes it as an
input, so the run settled PARTIAL (ADR 0030: a table with no rows for the session is never a
clean run), the critical `screens` step FAILED, and every later session was held back until the
step was waived by hand. Yet every value the screen needed had a fallback: the screen was
correct without IBKR.

## Decision
1. **A feature group may be optional**: `FeatureGroup.optional = True` says its source may be
   absent for a session without making the screens that read it incomplete. `ibkr_iv@v1` is the
   first. It is a property of the group (where its data comes from), not of its licence and not
   of `architecture/tables.toml`. `FeatureSet.optional_tables()` lists their tables.
2. **Coverage counts required tables only.** `settle_coverage` splits the session's missing
   tables into required and optional (`split_missing`); only a required one makes the run
   PARTIAL. No new `RunCoverage` value: an optional miss is not a state of the run. The run
   record keeps them apart: `missing_tables` (required, as before) and
   `missing_optional_tables` (audit only).
3. **The nightly warns.** The `screens` step carries one WARN check `optional_sources` per
   screener that went without an optional table; it SUCCEEDS when every job is COMPLETE.
4. **Values stay honest.** A value read from the absent table is UNKNOWN with its reason (ADR
   0036); a criterion over it behaves as missing data does under ADR 0030 (SCORE: no points).
5. **Fitness** (`tests/architecture/test_features.py`): every expression feature that reads an
   optional group still has a value when that table is absent and the required ones are stored
   (a `coalesce` or an `is_null` branch to a required table), and no site preset's HARD
   criterion reads an optional group's field directly (it would reject every row while the run
   reads COMPLETE).

## Consequences
- An IB Gateway outage no longer holds back the nightly; the report shows it as a warning on
  `screens` (and on the `ibkr-iv` step, already SKIPPED with a WARN).
- A new optional source is one flag on its group; the fitness tests then check every formula
  and site criterion over it.
- Only screen coverage changes. The selection audit and the Builder preview still list the
  optional table among the session's missing tables (neither grades a run), and a backtest
  over a session without it still raises (ADR 0008: missing data is an error). The typed read
  model shows only the required `missing_tables`; the optional ones are in the run's audit.
- A user's own screen with a HARD criterion directly on an optional field is not checked by the
  fitness test: on a session without the source it rejects every row and says why per row
  (`no <field>`), but the run is COMPLETE. The Builder may warn about it later.
- The `rollups` and `market-rollups` steps warn (never fail) for each rollup group that had no
  input for a session of the run (`check_rollup_inputs`, read from the run record's stats), so
  an empty optional partition such as `ibkr_iv@v1` is visible in the nightly report when it
  happens (2026-10-06: the rollups ran before `ibkr-iv` succeeded and nothing said so).
