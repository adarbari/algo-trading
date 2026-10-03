# ADR 0014: Cboe delayed feed for option chains; limited raw retention

**Status:** accepted (2026-10-02). The packaging note below is done: phase 0.7 split the apps into a uv workspace. Amends [0012](0012-data-vendors.md) and [0006](0006-storage-grains-and-adapters.md).

## Context
IBKR cannot pull end-of-day chains for about 4.2k underlyings a night: historical
requests are capped at 60 per 10 minutes, and quotes are fetched per contract. The
existing `liquidity_screen.py` already used Cboe's public delayed-quotes feed, which
returns a whole chain (quotes, OI, IV, Greeks) plus the underlying's `iv30` in one request.

## Decision
- The Cboe delayed feed is the **primary source for option chains and per-underlying
  `iv30`**, behind the standard source interface (`sources/cboe.py`). IBKR moves to futures,
  cross-checks and execution.
- Fail closed: only 404 means "no chain". 403 and 5xx are errors, and a run where more than
  25% of optionable names return no chain is PARTIAL.
- Raw responses (about 1–3 GB/day uncompressed) are gzip-compressed and kept for a
  **retention window** (default 90 days, `purge-raw`) instead of forever. Normalized
  Parquet tables are kept forever.
- Apps are separate top-level packages in one distribution for now
  (`algotrade_ingestion`). A uv workspace split happens when an app needs dependencies
  the others must not have (for example FastAPI for `apps/api`).

## Consequences
- The full optionable universe is covered nightly (about 10–20 minutes with 4 workers),
  and IV history accumulates from the first run.
- The feed is not a licensed product and may change or disappear. The fallbacks are
  Massive (paid) and Schwab. Switching is a new source module plus config.
- Replays are only possible inside the raw retention window.
