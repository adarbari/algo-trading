# ADR 0034: Instrument descriptions: a capped nightly pull into `instruments/description`

**Status:** proposed (2026-10-05; a new data source decision, held for owner review). Extends
[0012](0012-data-vendors.md) (Massive and SEC are used for a new dataset) and fills the
planned `description` column of [layers.md](../data/layers.md) in a table of its own.

## Context
The Explore Overview tab needs a short plain-text description of every ticker, stocks and ETFs
alike. Nothing stores one. Checked live on 2026-10-04 with the repo's Massive key (free tier):

- Massive's ticker overview (`GET /v3/reference/tickers/{ticker}`) returns `description`,
  `homepage_url` and `total_employees` for stocks and ADRs (AAPL, KO, PLTR, TSM). For ETFs
  (SPY, QQQ, XLK, ARKK, JEPI, BITO) it answers 200 with identity fields only: no description.
- It is one request per ticker. The free tier is 5 requests a minute, shared with the nightly
  bars. The universe holds about 5.7k stocks and ADRs and 5.7k ETFs, so asking for all of them
  takes about 37 hours; a full nightly refresh is impossible and must never starve the bars.
- For ETFs the SEC publishes the prospectus "investment objective" as XBRL text, free and
  official: `company_tickers_mf.json` (fund ticker to series) and the quarterly Mutual Fund
  Prospectus Risk/Return Summary Data Sets (one zip of about 80 MB per quarter). A fund appears
  in a quarter only if it filed a prospectus then.

## Decision
1. **A new L1 table `instruments/description`**, one row per instrument (`description`,
   `description_source`, `homepage_url`, `total_employees`, `filed`, `accn`, `fetched_on`),
   written by one task, `descriptions` (`tasks/profile/descriptions.py`). It is not a column of
   `instruments/reference` (a full snapshot that `universe-build` rebuilds every night; a second
   producer is not allowed, and a vendor text that changes once a year does not belong in a
   nightly snapshot) and not of `instruments/company` (keyed by CIK, and most ETFs have none).
   Runs are increments that merge, like `instruments/shares`: only rows fetched or changed are
   stored, and reads take the latest row per instrument (`data.reference.descriptions`). A
   ticker the vendor has no text for is stored as a marker without text, so it is not asked
   again before its refresh.
2. **Stocks and ADRs: Massive's overview, capped.** At most `[massive] descriptions_per_night`
   (100, about 21 minutes) tickers a night, in the existing fetch order (`priority_symbols` and
   S&P 500 members, then by liquidity, then the rest: `option_chains.prioritise`), each asked
   again only after `descriptions_refresh_days` (365) on a slot day by key (`refresh.due_keys`).
   The step runs after bars and the screens, so it never delays them. S&P 500 is covered in
   about 5 nights and all stocks in about 57; a hand run (`algotrade-ingest descriptions
   --limit N`) speeds that up.
3. **ETFs: the SEC prospectus objective.** The task reads the last `[sec_edgar] fund_quarters`
   (6) completed quarters, each once (a finished run's item `fund:<quarter>` marks it read; a
   quarter not published yet answers 404 and is tried again the next night), keeps the latest
   filing per series and stores it for every ETF whose ticker is in the fund map. The text is
   an investment objective, not a marketing description, and is labelled
   `description_source = sec_fund_objective`.
4. **Surface.** `GET /instruments/{id}` already returns `reference` as a dict; the explore
   service adds `description`, `description_source`, `homepage_url` and `total_employees` to it
   (`None` when nothing is stored). No schema, route or web change is needed.
5. **Nightly only; no on-demand fill from the API.** An API write for "the ticker the user
   opened" would be a fourth write path into reference data (ADR 0005, 0028, 0029, 0033 allow
   three narrow ones), and each request waits up to 12.5 s on the Massive limiter the nightly
   bars use, so a few page views could starve them. Instead the same task fills named tickers
   by hand (`--symbols AAPL,KO`) and the priority order puts the names people open first.

## Consequences
- Expected coverage (measured 2026-10-05 on the local universe): ETFs 74% from 5 quarters
  (4,267 of 5,764) and 76% from 11; the rest are funds that are not in the SEC fund map or
  file no such exhibit (commodity and currency trusts, unit trusts such as SPY, ETNs). Stocks
  reach 100% of the Massive-known tickers after the backfill; warrants, units, rights,
  preferreds and notes get none.
- Time to fill: ETFs in one run (about 90 seconds for 6 quarters, ~0.5 GB downloaded, kept as
  raw for 7 days); stocks 5.7k requests, about 20 hours, or 57 nights at the default cap.
- Massive's terms for showing its descriptions are not verified; this is a personal tool.
  Switching the stock source later changes one source, not the table.
- A fund the SEC fund map lists after its quarter was read stays without text until the next
  forced reread (`--force`); the texts lose some apostrophes in the SEC's XBRL.
- A read opens one small file per night that wrote rows (a year of nights is about 1 second for
  the whole table), so the explore service reads the table once per publish and serves every
  instrument page from that. If that grows, compact the table.
- The `profile` task domain is new; `refresh.py` and `prioritise` are shared with it
  (`[[shared]]` in `architecture/layout.toml`).
