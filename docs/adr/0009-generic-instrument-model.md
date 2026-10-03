# ADR 0009: A generic instrument model, so futures need no redesign

**Status:** accepted (2026-10-02). Spec: [docs/data/instruments.md](../data/instruments.md).

## Context
We start with stocks, ETFs and options, and futures come later. The architecture must not
change when they arrive.

## Decision
- All data is keyed by `instrument_id`, never by ticker string.
- An instrument has `asset_class`, `parent_id`, `multiplier`, `expiry` / `strike` / `right`,
  `root` / `contract_month`, `calendar`, `tick_size`, ETF leverage flags and validity dates.
- Each instrument's exchange calendar defines `session_date` for every row. Engines
  iterate over sessions.
- Continuous futures are a **derived dataset** with the roll rule recorded in its
  metadata. Rolls and expiries are events.
- P&L and exposure always use `qty × price × multiplier`.

## Consequences
- Known gap: today's `Portfolio`, `PriceSeries` and `MarketView` are keyed by symbol and
  assume multiplier 1. They must switch to `instrument_id` and read the multiplier before
  any options or futures backtest (roadmap phase 0/2).
