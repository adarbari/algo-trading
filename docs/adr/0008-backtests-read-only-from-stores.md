# ADR 0008: Backtests read only from stores

**Status:** accepted (2026-10-02)

## Context
A backtest that fetches data while it runs is slow, non-deterministic and depends on a
vendor being up.

## Decision
- Backtests (CLI, notebooks or UI-submitted jobs) read only through `storage/readers`.
- Missing data raises a `MissingDataError` naming the dataset, instruments and date
  range, plus the ingestion command that would fill it. Backtests never fetch.
- Every backtest result records the dataset versions and `as_of` it used, so it can be
  reproduced exactly.
- Tests and CI run backtests against a fixture store built from the golden datasets,
  through the same reader code.

## Consequences
- Backfills are an ingestion concern (`ingestion backfill --dataset … --from … --to …`).
- Backtests are deterministic and fast, and can run with no network access.
