# ADR 0013: The universe

**Status:** accepted (2026-10-02); amended by [0015](0015-configs-selections-users.md): the universe is coverage, and strategies select from it. Amended 2026-10-18 (owner-approved; docs/decisions/log.md): coverage adds closed-end funds (below). Detail: [docs/data/instruments.md](../data/instruments.md).

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

## Amendment (2026-10-18): closed-end funds
- Coverage adds **closed-end funds (CEFs)**: `security_types` in `config/site/universe.toml` gains
  `CEF` (the vendor's `FUND` type, stored in the reference as `CEF`). About 330 active funds.
- A CEF is a **NAV-priced fund, not an ETF**: it has no creation or redemption, so its price
  drifts from its net asset value. Its `security_type` stays `CEF`; its universe `asset_class` is
  `ETF` (the stock/fund split), so it never joins a stock population (breadth, relative
  strength, analyst coverage). Operating-company features do not apply (`OPERATING_TYPES`).
- Bars already exist (the nightly Massive grouped-daily resolves every listed ticker; Tiingo
  `bars-history` fetched them back to 2010), so the Tiingo symbol budget is unchanged (nightly
  bars are Massive's). Cost: about +330 universe rows a session, about +3% storage.
- The first universe snapshot with CEFs is the first build after this change. Earlier sessions
  keep the old snapshot; before it, the listing history reads a delisted CEF as an ETF, so a
  rule `security_type eq CEF` is survivors only there (ADR 0053 `today_flag`), and about 37
  live CEFs listed as Stock on NYSE are missing too; sessions 2026-10-02 to 2026-10-17 have no CEF
  universe or outcome rows until the backfills run.

## Consequences
- About 10k+ instruments for bars and about 4.2k optionable underlyings, so storage is
  partitioned by time rather than by ticker (ADR 0006).
