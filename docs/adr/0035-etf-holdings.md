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
   different U.S. company: Roche `ROP` and Roper, Telus `T` and AT&T). State Street's workbook
   has no exchange or country column, so its rule is an equity line with a ticker, in USD,
   with a nine-character security id of either form: a CUSIP, or a CINS (letter first), which
   is what companies listed here but domiciled abroad print (Linde `G54950103`, Accenture,
   Chubb, Medtronic, Eaton and ~25 more S&P 500 members; requiring a digit unlinked them).
   N-PORT prints no tickers, so its lines are linked through CUSIPs and CINS codes: the map
   holds only equity lines of issuers that print tickers whose ticker resolved to a universe
   instrument, and it stores that instrument id (not the ticker, which a later listing can
   reuse for another company). A foreign line (Telus is `T` in CAD) never enters it, and a
   line is never linked on the bridge alone without such a match. Cash, futures, bonds and
   unmatched lines keep their name only. A State Street line is called a future or a money
   market sweep by its name only when it has no ticker (a company called Future PLC is not).
5. **Schedule and scope.** Part of the nightly (`etf-holdings`, latest session only): each
   fund has a weekly slot (`refresh_days`), N-PORT funds a 90-day one (their data is
   quarterly), funds an issuer lists but has no file for are retried once a window. The nightly
   reads at most `[etf_holdings] per_night` (200) funds, taken from ONE due list across all
   issuers (never read first, then the oldest read first, issuer priority only breaking ties)
   and cut after that ordering, not per issuer: the first version capped each issuer's list in
   turn, so the daily-file funds used the whole cap and N-PORT was starved. The explicit CLI is
   uncapped. The first pass over ~1,140 funds takes 6 weekday nights at 200 a night. Steady
   state, simulated over a year: ~700 reads a week (661 daily-file funds weekly and 480 N-PORT
   funds every 90 days) against 1,000 of capacity, so a daily-file fund is read every 7 to 8
   days and an N-PORT fund every ~91 days (4 to 5 reads a year). At 100 a night the daily-file
   funds stretch to 18 days between reads and at 150 to 12, which is why the default is 200.
   (The first version of this ADR said "about 12 nights" for the first pass; that counted 100 a
   night and ignored that daily-file funds come due again every week.) The step runs
   after bars and chains. N-PORT is a scope-limited fallback: by default (`fallback_scope = "liquid"`) it is read
   only for ETFs that no daily file covers and that are optionable or trade at least
   `fallback_min_adv_usd` ($5M) a day (`price_stats.adv_usd_20d`, from the latest session that has
   rollups; with none stored, as on a new store, it reads the optionable funds only and the run's stats
   say so: `fallback_adv_missing`).
   `optionable` is the first version's scope; `all` reaches every registered fund, ~4k funds,
   with a first pass of hours; `off` leaves it out. The rest are not read because most of the 3.9k
   funds N-PORT could add are tiny and each costs a few hundred small requests per trust.
   **One broken issuer must not take the cap.** A read that raised (an issuer answering 403, a
   changed layout, an N-PORT report with no period date) is held back like a rejection: the
   fund waits 1 day after its first failure, then 2, 4, 8 ... up to 30 (N-PORT: 30), so a
   lasting fault costs about one request a month per fund; funds whose last read failed sort
   after healthy due funds; and every issuer with funds due is given at least 20% of the
   nightly slots first (`ISSUER_FLOOR`). Before this, a failed fund left no trace, stayed
   "never read" and headed the single list every night: with all 480 iShares funds failing,
   State Street was not read for 275 days and N-PORT about once a year in a simulation. The
   year simulations in `test_etf_holdings_plan.py` (iShares, State Street or N-PORT broken for
   the whole year) keep every healthy daily-file fund at a gap of 8 days and every N-PORT fund
   at 4 reads, with about 16 failed attempts per broken fund over the year. When an issuer's
   fund list cannot be read tonight, its funds are not handed to the next issuer (they would
   be read from months-old N-PORT and hard-rejected as older than the stored daily rows,
   after a header crawl): they are skipped, and the run is PARTIAL with
   `skipped_directory_down` in its stats.
6. **A bad read never replaces a good one, and a real change still gets through.** A workbook
   or CSV that does not say its as-of date, has no table, no `Weight` column or no lines is a
   parse failure (FETCH_ERROR, last read's rows stay), never an empty fund; columns are found
   by their position in the raw row, so an empty header cell cannot shift them; a weight that
   does not read drops the line (never 0). A new read is rejected when its weights do not add
   up to about 100% (not checked for leveraged, inverse and N-PORT funds), when the file's own
   published `Weight (%)` sum is under 97% (iShares: the weights we store come from market
   values and always add up, so a file cut short mid-table would otherwise pass with inflated
   weights; not judged for funds where most lines print 0.00), when its as-of date is older, or
   when its number of positions fell below half of the last read (daily files only; a quarterly
   report is a new document). Weight sums, the published sum and an older date are hard
   rejections: never accepted on their own. The position count is a soft rejection, because a
   fund can really shrink (a rebalance, a merger). It is accepted when three reads in a row
   agree: the two latest outcomes before this read were soft rejections with nothing else
   between (a hard rejection, a missing file or a failed read starts the count over), all
   three counts are below the stored one and within 10% of each other, and either the three
   as-of dates strictly increase (a file that updates daily) or they are one date with one
   count seen on three different run days (a file that updates monthly keeps its date for
   weeks and must still get through). The outcomes are saved as plain fields in each run's
   stats (`fund_events`: kind, as-of date, position count), not read back from item text.
   Until a read is accepted it is a FAILED item (the run is PARTIAL), last read's rows stay,
   and the fund waits before its next try, longer each time in a row (2 days, then 4, 8 ...
   up to 30; N-PORT 30), so a rejection costs a fetch now and then, not one a night, and does
   not refetch the N-PORT list and headers. Without this, a rejected read could never
   succeed: it was retried on every run and compared with the same old rows.
   `algotrade-ingest etf-holdings --force --symbols X` reads a fund and accepts it, checks
   off, for an owner who has looked at the file.
7. **Manners.** Each issuer has its own pace (`[ssga]`, `[ishares]` 1 s; SEC 0.2 s with the
   contact User-Agent), raw files are kept 14 days (SEC 7), and the issuers' robots.txt files
   were read; a site that disallows crawlers is not used.
8. **API and web.** `GET /instruments/{id}/holdings?top=10` returns the top N, the total, the
   as-of date and the source; an unknown instrument is 404, a non-ETF or an ETF with nothing
   stored is 200 with an empty list. The web shows it in the `holdings-panel` widget.
   The panel sizes a short line by its absolute weight, so the total is gross: it reads
   "short lines included" when any listed line is short.
9. **State Street switches and S&P 500 membership.** The SPY membership file and the fund
   files are separate switches: `[ssga] enabled` turns State Street off, `[ssga] etf_files =
   false` turns off only the SPDR fund files (SPY's membership stays on). The membership
   table ends at the first line that has only its first cell (the disclaimer text); a line
   with a blank ticker is skipped as a member and a blank weight does not end the table.
   The universe build refuses a list that is implausibly unlike the last snapshot (100 or
   more members): under 90% of its members, or more than 12 members joining or leaving at
   once. It does not fail: the membership flags of the last snapshot are kept (so no
   `index_change` event is emitted), everything else is built and written, and the step is
   PARTIAL with the reason in its stats (`sp500_held`). `algotrade-ingest universe-build
   --accept-sp500` applies a list that really is that different. A first build has no
   snapshot to compare with, so it can emit no removals and has no absolute floor.

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
  these public holdings files (2026-10-05) and kept `fallback_scope = "optionable"`. The same day
  the default became `liquid`, because the optionable-only scope left liquid non-optionable funds
  without holdings. Measured on 2026-10-05: of the 5,730 ETFs, up
  to 943 non-optionable ones trade at least $5M a day (640 at $10M, 343 at $25M); the ones a daily
  file already covers are in that count and were in scope before.
- Storage: about 100 rows per fund, 37 bytes a row measured; a full pass over the ~1,100
  covered funds is ~110k rows, ~4 MB. Raw files add about 12 MB a night, kept 14 days.
- Known limits and follow-ups: N-PORT filers that print tickers skip the CUSIP bridge, and the
  `invCountry == US` test keeps US-listed companies domiciled abroad name-only on the
  N-PORT lines that do carry a ticker; their State Street lines are linked (decision 4);
  if the State Street fund finder is down tonight, its funds are skipped (decision 5), and a
  fund State Street never listed is read from N-PORT (months old); every night
  `holdings_status` and `known_cusips` read the whole table over 550 days (cheap at ~110k
  rows, worth a narrower read if it grows); rows stored before the CUSIP map was restricted
  to resolved equity lines (none exist outside development stores) would need a one-off
  clean-up of `holdings/etf`; a hard rejection (a weight sum, a cut-short file) is retried at
  2, 4, 8 ... days up to monthly until the issuer fixes the file or the owner forces it;
  `holding_id` is stored as written and the id map's renames (a symbol id upgraded to a FIGI
  id) are not applied to stored holdings, so a holding whose id was upgraded after the read
  keeps the old id until the fund is read again (at most a week for daily files, a quarter
  for N-PORT); `[etf_holdings]` accepts only its own keys and `enabled`, a vendor key such as
  `min_interval_s` there is an error.
