# ADR 0035: ETF holdings from issuer files, with SEC N-PORT as the universal fallback

**Status:** proposed (2026-10-05; a new data source and a new grain, so it needs owner
review). Extends [0012](0012-data-vendors.md), [0013](0013-universe.md) and
[0027](0027-vendor-sources-shared-package.md).

## Context
Explore should show what an ETF holds: its top ten companies with their weights, the number of
holdings and the date they are as of. Only SPY's holdings were fetched, as a membership list
(S&P 500), not stored as holdings. Probed on 2026-10-05:

| Source | Coverage | Lag | Verdict |
|---|---|---|---|
| State Street (SPDR) daily workbook, one URL per fund, listed by its public fund finder | 181 SPDR ETFs: SPY, the sector funds, DIA, MDY, bond and international funds | 1 day | use |
| iShares `latest-holdings.csv` on each fund page, listed by the product screener | 526 listed funds (480 in our universe); the metal trusts (SLV) have no file | 1 day | use |
| SEC N-PORT-P (`data.sec.gov` + `Archives`), series from `company_tickers_mf.json` | every registered fund: Vanguard, Invesco QQQ, Schwab, ARK, most others. Not unit trusts (SPY, DIA) or commodity and crypto trusts | 60 to 150 days, quarterly | use as fallback |
| Vanguard fund pages | a single-page app; its data API answers HTML, no file | n/a | skip (N-PORT covers it) |
| Invesco `dng-api.invesco.com` | HTTP 406 for a non-browser client | n/a | skip; we do not impersonate a browser (N-PORT covers QQQ) |
| ARK `assets.ark-funds.com` | a daily CSV, but its robots.txt disallows all crawlers | n/a | skip, honour robots.txt |
| Massive / Nasdaq free tiers | no ETF holdings endpoint found | n/a | skip |

## Decision
1. **One shape, issuers as adapters.** `HoldingsSource` (`framework/base.py`) is a source with a
   directory request (which funds it publishes) and one request per fund returning the shared
   holdings frame (`framework/holdings.py`: weight as a fraction, ticker, name, asset class,
   security id). Adapters: `ssga_holdings`, `ishares_holdings`, `sec_nport_holdings` (one
   vendor folder each; the SEC one in `vendors/sec`). Another issuer is one more adapter.
2. **Priority, not merging.** A fund is read from the first adapter that lists it: the issuer's
   own daily file, then N-PORT. No averaging of sources.
3. **A new grain, `holdings/etf`:** one row per fund x holding x as-of date, ranked by weight,
   the largest `[etf_holdings] keep_top` (100) kept, every row carrying the file's total line
   count. `as_of` is the issuer's date; the partition is the session of the run that read it.
   Runs merge (a run reads a few funds); readers take each fund's latest `as_of` from its
   latest run (`data.funds.holdings`), so a shorter re-read cannot leave stale ranks behind.
4. **Linking.** The holding's ticker resolves to an instrument id only through `SymbolResolver`
   and only when the issuer says it is a U.S. listing (a foreign line's local ticker can be a
   different U.S. company: Roche `ROP` and Roper). N-PORT prints no tickers, so its lines are
   linked through the CUSIPs that State Street prints beside tickers. Cash, futures, bonds and
   unmatched lines keep their name only.
5. **Schedule and scope.** Part of the nightly (`etf-holdings`, latest session only): each
   fund has a weekly slot (`refresh_days`), N-PORT funds a 90-day one (their data is
   quarterly), funds an issuer lists but has no file for are retried once a window. About 100
   funds a night. N-PORT is a scope-limited fallback: by default it is read only for optionable
   ETFs that no daily file covers (`fallback_scope`; `all` reaches every registered fund, ~4k
   funds, with a first pass of hours; `off` leaves it out), because most of the 3.9k funds it
   could add are tiny and each costs a few hundred small requests per trust.
6. **Manners.** Each issuer has its own pace (`[ssga]`, `[ishares]` 1 s; SEC 0.2 s with the
   contact User-Agent), raw files are kept 14 days (SEC 7), and the issuers' robots.txt files
   were read; a site that disallows crawlers is not used.
7. **API and web.** `GET /instruments/{id}/holdings?top=10` returns the top N, the total, the
   as-of date and the source; an unknown instrument is 404, a non-ETF or an ETF with nothing
   stored is 200 with an empty list. The web shows it in the `holdings-panel` widget.

## Consequences
- Coverage (2026-10-02 universe, 5,730 active ETFs): daily files 661 funds (11.5%: State
  Street 181, iShares 480), N-PORT listed for 3,949 more; the default run covers 1,141 funds
  (19.9%) and 630 of the 767 optionable ETFs (82%). A 53-fund real sample read every daily
  file and found an N-PORT filing for 32 of 33 funds. N-PORT is months old; the answer says so
  through `as_of` and `source`.
- Not covered: unit trusts and commodity or crypto trusts outside State Street and iShares
  (GLD, SLV, bitcoin trusts), ETNs, and funds whose N-PORT lookup finds no filing.
- The issuers' sites are not licensed APIs; they can change a layout or block us. Adapters are
  tested against recorded responses, each fund is an isolated item, and a changed file makes
  one fund fail, not the run. The terms of use of State Street and iShares were not confirmed
  to permit automated downloads of the public holdings files; the owner should confirm.
- Storage: about 100 rows per fund, 37 bytes a row measured; a full pass over the ~1,100
  covered funds is ~110k rows, ~4 MB. Raw files add about 12 MB a night, kept 14 days.
