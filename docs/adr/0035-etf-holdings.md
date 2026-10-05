# ADR 0035: ETF holdings from issuer files, with SEC N-PORT as the universal fallback

**Status:** accepted (2026-10-05; owner review of the new source and grain done). Extends [0012](0012-data-vendors.md), [0013](0013-universe.md) and
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
   the largest `[etf_holdings] keep_top` (100) kept (by the size of the weight, so a big short
   or swap line ranks with the big longs), every row carrying the fund's number of positions
   (cash, futures and FX lines are stored but not counted). `as_of` is the issuer's date;
   `filed` is the date the data became public when later (an N-PORT filing) and a read for an
   earlier date never shows the row; the partition is the session of the run that read it.
   Runs merge (a run reads a few funds); readers take each fund's latest `as_of` from its
   latest run (`data.funds.holdings`), so a shorter re-read cannot leave stale ranks behind.
4. **Linking.** The holding's ticker resolves to an instrument id only through `SymbolResolver`
   and only when the issuer says it is a U.S. listing (a foreign line's local ticker can be a
   different U.S. company: Roche `ROP` and Roper). N-PORT prints no tickers, so its lines are
   linked through CUSIPs: the map holds only equity lines of issuers that print tickers whose
   ticker resolved to a universe instrument, so a foreign line (Telus prints as `T`) never
   enters it, a line is never linked on the bridge alone without such a match, and CINS codes
   (letters first) are not looked up. Cash, futures, bonds and unmatched lines keep their name
   only.
5. **Schedule and scope.** Part of the nightly (`etf-holdings`, latest session only): each
   fund has a weekly slot (`refresh_days`), N-PORT funds a 90-day one (their data is
   quarterly), funds an issuer lists but has no file for are retried once a window. The nightly
   reads at most `[etf_holdings] per_night` (100) funds, new and stalest first (the explicit
   CLI is uncapped), so the first pass over ~1,140 funds takes about 12 nights; the step runs
   after bars and chains. N-PORT is a scope-limited fallback: by default it is read only for optionable
   ETFs that no daily file covers (`fallback_scope`; `all` reaches every registered fund, ~4k
   funds, with a first pass of hours; `off` leaves it out), because most of the 3.9k funds it
   could add are tiny and each costs a few hundred small requests per trust.
6. **A bad read never replaces a good one.** A workbook with no `Weight` column is a parse
   failure; a weight that does not read drops the line (never 0); a new read is rejected, and
   last read's rows stay, when its weights do not add up to about 100% (not checked for
   leveraged, inverse and N-PORT funds; iShares weights come from market values, so for them
   this only catches a changed layout), when its number of positions fell below half of the
   last read, or when its as-of date is older. A rejected read is a FAILED item (the run is
   PARTIAL) and is retried on the next run.
7. **Manners.** Each issuer has its own pace (`[ssga]`, `[ishares]` 1 s; SEC 0.2 s with the
   contact User-Agent), raw files are kept 14 days (SEC 7), and the issuers' robots.txt files
   were read; a site that disallows crawlers is not used.
8. **API and web.** `GET /instruments/{id}/holdings?top=10` returns the top N, the total, the
   as-of date and the source; an unknown instrument is 404, a non-ETF or an ETF with nothing
   stored is 200 with an empty list. The web shows it in the `holdings-panel` widget.

## Consequences
- Coverage (2026-10-02 universe, 5,730 active ETFs): daily files 661 funds (11.5%: State
  Street 181, iShares 480), N-PORT listed for 3,949 more; the default run covers 1,141 funds
  (19.9%) and 630 of the 767 optionable ETFs (82%). A 53-fund real sample read every daily
  file and found an N-PORT filing for 32 of 33 funds. N-PORT is old: filed 60 to 150 days after the period, and a 90-day
  refresh slot that ignores filing dates can add up to 90 more, so up to ~240 days after the
  period; the answer says so through `as_of` and `source`.
- Not covered: unit trusts and commodity or crypto trusts outside State Street and iShares
  (GLD, SLV, bitcoin trusts), ETNs, and funds whose N-PORT lookup finds no filing.
- The issuers' sites are not licensed APIs; they can change a layout or block us. Adapters are
  tested against recorded responses, each fund is an isolated item, and a changed file makes
  one fund fail, not the run. The owner accepted State Street's and iShares' terms of use for
  these public holdings files (2026-10-05) and kept `fallback_scope = "optionable"`.
- Storage: about 100 rows per fund, 37 bytes a row measured; a full pass over the ~1,100
  covered funds is ~110k rows, ~4 MB. Raw files add about 12 MB a night, kept 14 days.
- Known limits and follow-ups: N-PORT filers that print tickers skip the CUSIP bridge, and the
  `invCountry == US` test keeps US-listed companies domiciled abroad (LIN, ACN, MDT, CB, ETN)
  name-only; if the State Street fund finder is down, optionable SPDR funds are read from
  N-PORT (months old) until it is back; every night `holdings_status` and `known_cusips` read
  the whole table over 550 days (cheap at ~110k rows, worth a narrower read if it grows);
  rows stored before the CUSIP map was restricted to resolved equity lines (none exist outside
  development stores) would need a one-off clean-up of `holdings/etf`; a rejected read is
  retried on every run and uses a `per_night` slot.
