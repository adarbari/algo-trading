# ADR 0012: Several data sources, free first, IBKR for derivatives

**Status:** accepted (2026-10-02). Detail: [docs/data/vendors.md](../data/vendors.md).

## Context
We need end-of-day data for options, swing/momentum (stocks and ETFs) and, later, futures,
and we want to avoid paid data for now.

## Decision
- Every vendor implements one source interface in `apps/ingestion/sources/`, and every
  adapter is tested against recorded responses (no network in CI).
- Universe: Nasdaq Trader symbol directory + SPY holdings.
- Daily stock and ETF bars: Massive free tier first, with Alpaca / IBKR as cross-checks.
- Options: **IBKR** for a liquid tier (S&P 500 + liquid ETFs). The full optionable
  universe (about 4.2k) needs a bulk source (Massive paid or Schwab); this is still open.
- Futures (later): IBKR, with Databento as the history backfill option.
- We compute IV and Greeks ourselves (`quant/`) and keep vendor values as a cross-check.
  We store our own option snapshots from day one to build IV history.

## Consequences
- IBKR adapters need rate limiting, resumable jobs and gateway-health alerts.
- IV-rank style screeners only become meaningful after about a year of our own history.
