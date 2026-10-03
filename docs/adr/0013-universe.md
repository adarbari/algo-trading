# ADR 0013: The universe

**Status:** accepted (2026-10-02). Detail: [docs/data/instruments.md](../data/instruments.md).

## Context
We want to cover options trading, swing/momentum trading and, later, futures across a broad
US universe, without survivorship bias.

## Decision
- The universe is S&P 500 constituents ∪ all Nasdaq-listed stocks ∪ **all ETFs on any US
  exchange, including leveraged and inverse ETFs**. Futures roots are added later.
- Saved as a dated snapshot each day to avoid survivorship bias. Index membership changes
  are stored as events.
- Leveraged and inverse ETFs are flagged from a curated override file. Name heuristics
  only *suggest* candidates for review.
- Each instrument carries an optionable flag (from Nasdaq Trader `options.txt`), which
  decides which tier of option ingestion covers it.

## Consequences
- About 10k+ instruments for bars and about 4.2k optionable underlyings, so storage is
  partitioned by time rather than by ticker (ADR 0006).
