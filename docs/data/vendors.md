# Data vendors

Decision record: [ADR 0012](../adr/0012-data-vendors.md). Researched 2026-10-02; re-check
limits and prices before relying on them.

Every vendor sits behind the same source interface in `libs/sources/algotrade_sources/`. Adding or
swapping a vendor never touches storage, features, strategies or the UI.

**Pacing is shared.** Each source is declared once in `sources/framework/registry.py` with its
`config/site/sources.toml` section and a limiter key (`cboe`, `nasdaqtrader`, `ssga`,
`nasdaq`, `ishares`, `massive`, `sec`, `treasury`, `ibkr`, `ibkr_historical`). One limiter per key (`sources/framework/limiter.py`)
spaces requests across every worker thread **and every process** on the machine (a lock file
per key under `[http] limits_dir`, default `var/run/limits/`), so a backfill and the nightly
run never exceed a vendor's limit together. The pace is **adaptive** between the section's
`min_interval_s` (floor) and `max_interval_s` (ceiling): a 429 holds every process for its
`Retry-After` and multiplies the interval by `[http] backoff_factor`; more than
`max_error_rate` errors over the last `error_window` responses slows it down the same way;
`speedup_after` clean responses in a row speed it up by `speedup_factor`, never below the
floor (see [configuration.md](../configuration.md#vendor-pacing)). The IB Gateway session
source (`ibkr`, `ibkr_historical`) is not HTTP and keeps a fixed `min_interval_s`. Retries live in
`sources/framework/http.py`: other failures back off, and one request gives up after
`[http] max_retry_s`. After `[http] breaker_failures` consecutive 403/5xx from a vendor its
circuit opens: the rest of the run's items for that vendor fail at once with
`FETCH_ERROR: <key>: circuit open ...` (run PARTIAL) instead of each burning its retries.

## By use case

| Data | Primary (free) | Alternatives | Notes |
|---|---|---|---|
| Ticker universe | Nasdaq Trader symbol directory (`nasdaqlisted.txt`, `otherlisted.txt`, `options.txt`) | — | Official, free, updated daily |
| S&P 500 membership | SPY daily holdings file (State Street) | — | Membership changes become events |
| ETF holdings (top holdings and weights per fund) | **Issuer daily files**: State Street SPDR workbooks, iShares CSVs; **SEC N-PORT** for the funds they do not cover (ADR 0035) | Vanguard / Invesco / ARK sites (no usable public file, see below) | Proposed, needs owner review of the terms of use |
| Company details (name, SIC, sector, state, fiscal year end) | SEC EDGAR submissions (free; contact email in the user agent) | Massive ticker details | Implemented, phase 1.7 |
| Shares outstanding (market cap) | SEC EDGAR company facts (XBRL; free; same contact and pacing) | Massive ticker details (`share_class_shares_outstanding`) | Implemented, phase 2b.4 |
| Daily stock and ETF bars (swing / momentum) | Massive (formerly Polygon) free tier: all US tickers, 2 years history, 5 calls/min; "grouped daily" = whole market in 1 call | Alpaca (free account), IBKR, Yahoo (unofficial, history backfill only) | |
| IV history / IV rank (enrichment) | **IBKR** (ADR 0028): IB's daily 30-day IV and HV per underlying, years of history; personal-use licence | our IV30 history (from the Cboe chains), the fallback | Implemented: `ibkr_iv@v1`, `iv_rank` with `iv_rank_source` |
| End-of-day option chains | **Cboe delayed-quotes feed** (ADR 0014): whole chain + Greeks + IV + OI and the underlying's `iv30` in one request per underlying; about 4.2k requests a night | IBKR for a focused list / cross-check; Schwab Trader API (free with account; Greeks; all expiries in one call; 120 req/min); Tradier (needs a brokerage account for Greeks); Alpaca (free indicative feed, history from 2024-02); Massive options (paid, from ~$29/mo; licensed fallback) | No free source covers end-of-day chains for the whole universe with history. **We build our own IV history from day one.** |
| Futures (later) | **IBKR** (contracts, history, including recently expired) | Databento (pay-as-you-go history), Massive futures (paid), Yahoo/Stooq continuous (unofficial, unclear rolls) | |
| Risk-free rates (option pricing) | **U.S. Treasury daily par yield curve** (official, free, no key; one CSV per year) | FRED (`DGS*`, needs a key), SOFR (overnight only) | Implemented, phase 2b.1 (ADR 0021) |
| Synthetic | `sources/fixtures/` (golden datasets) | — | Lets the whole pipeline run in CI with no account |

## Cboe delayed-quotes feed (primary for options)

`https://cdn-api.cboe.com/api/global/delayed_quotes/options/<SYMBOL>.json` (index options
use a leading underscore, e.g. `_SPX`). Checked 2026-10-02: SPY returned 13,280 contracts
in about 0.3 s.

| Per contract | bid/ask (+ sizes), last, volume, open interest, IV, delta, gamma, vega, theta, rho, theo |
|---|---|
| Per underlying | price, OHLC, previous close, volume, `iv30` |

Caveats, handled in `libs/sources/algotrade_sources/vendors/cboe/option_chains.py`:

- **Not a licensed product.** It is the undocumented feed behind cboe.com and can change or
  disappear. Check Cboe's site terms; keep Massive or Schwab as the fallback.
- Delayed quotes. The snapshot is taken after the close, so it is valid for end-of-day use.
- `open_interest` is OCC's figure as of the previous session.
- Greeks and IV are Cboe's model values; ours (`quant/`) will cross-check them.
- **Rate limit (measured 2026-10-03, `cdn-api.cboe.com`, our User-Agent):** Cloudflare allows
  about **60 requests per rolling minute**. 1 request/s for 60 s: all 200 (p50 latency 0.45 s);
  2/s: HTTP 429 with body `error code: 1015` after ~13 s; 1.2/s: 429 at request 69 (57 s).
  The 429 carries `Retry-After` of ~47–60 s and the ban lifts after about a minute. We pace
  at `[cboe] min_interval_s = 1.05` (~57/min, just under the limit; 2 workers share the one
  limiter), backing off up to `max_interval_s = 5.0` on 429s or errors and recovering after
  clean streaks: **~75 min for the ~4.2k-underlying universe** (was 1.5 s, ~105 min).
- Fetch order: the configured `[cboe] priority_symbols` (SPY, QQQ, IWM, sector ETFs, VIX
  ETPs...) and S&P 500 members first, then by the latest `liquidity_class@v1` (HIGH, MEDIUM,
  LOW, UNKNOWN) and chain open interest, then the rest alphabetically, so a run cut short
  still has the names that matter (`chains` run stats: `order_tiers`).
  The CDN serves chains from S3, so a symbol with **no published chain answers 403 with S3's
  `AccessDenied` XML**: that one response is read as NO_CHAIN and does not count towards the
  circuit breaker (`missing_chain` in the Cboe adapter). Any other 403 (e.g. a Cloudflare
  block, which is HTML) stays an error, and a run where more than 25% of optionable names
  return no chain is PARTIAL. (Found 2026-10-03: a run of missing symbols had tripped the
  breaker and skipped 815 names, ~84% of which did have chains.)
- Raw responses are about 1–3 GB/day across the universe, so raw retention is limited
  (ADR 0014, `algotrade-ingest purge-raw --keep-days 90`).

## Massive daily bars and corporate actions (implemented, phase 1.4)

Host `https://api.massive.com`; the key (`ALGOTRADE_MASSIVE_API_KEY` in `.env`) is sent as an
`Authorization: Bearer` header, never in URLs, raw files or logs.

| Data | Endpoint | Stored as |
|---|---|---|
| Daily bars, whole market per request | `/v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false` | `bars/1d`, **unadjusted**; invalid rows dropped and counted |
| Splits | `/stocks/v1/splits` (date window, paginated) | `events/split` (ratio = split_to / split_from) |
| Dividends | `/stocks/v1/dividends` (date window, paginated) | `events/dividend` (same ex-date amounts summed) |

Free tier: 5 requests/minute, so requests are spaced 12.5 s apart (`[massive]
min_interval_s`, shared by bars, corporate actions and the ticker list). `algotrade-ingest bars
--from 2024-10-01 --to 2026-10-01` backfills two years (~500 requests, ~1h45m) and resumes
where it stopped; nightly fetches the session's bars and a corporate-action window (-7 to +30
days; `[massive]` in `config/site/sources.toml`). Massive preferred tickers (`KIMpL`) are mapped to the universe's ACT style (`KIM$L`).
Prices are adjusted at read time (`none`, `splits`, `total_return`; setting
`[backtest] price_adjustment`).

## Nasdaq earnings calendar (implemented, phase 1.3)

`https://api.nasdaq.com/api/calendar/earnings?date=YYYY-MM-DD`: free, no key, unofficial
(browser user agent required). One request per date returns every company reporting that day
with timing (pre-market / after hours / not supplied), the EPS forecast and number of
estimates; past dates add the reported EPS and surprise. `algotrade-ingest earnings` stores a
60-day forward window nightly in `events/earnings`, plus the last 7 days (`lookback_days`: those
reports now carry the reported EPS and surprise, and `last_earnings_date` stays current), in the
partition of the run's session, so date changes stay point-in-time; `--start` in the past
backfills. About 2 minutes a night
(requests spaced by `[nasdaq_earnings] min_interval_s`, 0.5 s).

## U.S. Treasury par yield curve (implemented, phase 2b.1)

`https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<year>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<year>&page&_format=csv`:
official, free, no key (checked 2026-10-03: 200 OK, ~20 KB per year, the current year up to
the latest business day; a year with nothing published returns an empty body). One row per
date the bond market was open, newest first: `Date` (MM/DD/YYYY) then constant-maturity par
yields in percent: `1 Mo`, `1.5 Month` (from Feb 2025), `2 Mo` (from Oct 2018), `3 Mo`,
`4 Mo` (from Oct 2022), `6 Mo`, `1 Yr`, `2 Yr`, `3 Yr`, `5 Yr`, `7 Yr`, `10 Yr`, `20 Yr`,
`30 Yr`. Missing cells (tenors not yet published) are left out, not stored as gaps.
`sources/vendors/treasury/par_yields.py` turns each cell into a `rates/treasury` row (tenor,
days, par yield and continuous rate as decimals; conventions in ADR 0021).
`algotrade-ingest rates --from 2024-01-01 --to <date>` backfills with one request per year;
nightly re-checks the last `[treasury] lookback_days` (10) and writes only curve dates not
yet stored. Paced by `[treasury] min_interval_s` (1 s; no published limit). The curve is
published after the close, and the bond market keeps its own holidays (Columbus Day,
Veterans Day), so a session can lack its own curve: `data.rates.curve` uses the latest one.

## ETF holdings (implemented, ADR 0035)

One adapter per issuer behind `HoldingsSource` (`framework/base.py`); the `etf-holdings` task
reads a fund from the first adapter that lists it. Probed 2026-10-05 with the project
User-Agent (SEC: the contact from `ALGOTRADE_SEC_CONTACT`), a handful of requests each, one a
second or slower.

| Issuer | What we read | Coverage | Lag |
|---|---|---|---|
| State Street (SPDR), `[ssga]` | The public fund finder (`/bin/v1/ssmp/fund/fundfinder?country=us&language=en&role=intermediary&product=etfs&ui=fund-finder`, 0.85 MB) lists each fund's `Holdings-daily` workbook path; one `.xlsx` per fund (20 to 190 KB). Equity funds: Name, Ticker, Identifier (CUSIP), SEDOL, Weight, Sector, Shares Held, Local Currency; bond funds: no ticker, ISIN, Par Value | 181 of the 183 US SPDR ETFs: SPY, XL*, DIA, MDY, SPYG... (not GLD, GLDM) | 1 day |
| iShares, `[ishares]` | The product screener JSON (`/us/product-screener/product-screener-v3.1.jsn?...`, 1.9 MB) maps 526 tickers to fund pages; each page offers `<page>/latest-holdings.csv` (a schema.org DataDownload; 0.1 to 4 MB). Weights have two decimals; foreign lines print local tickers (Roche as `ROP`) | 526 listed funds; metal trusts (SLV) answer HTTP 400 | 1 day |
| SEC N-PORT, `[sec_edgar]` | `files/company_tickers_mf.json` (ticker to trust CIK and series), `data.sec.gov/submissions/CIK<cik>.json` (the trust's N-PORT-P list), the filing's `-index-headers.html` (names its series; the list does not), then `primary_doc.xml` (0.1 to 4 MB: name, CUSIP / ISIN, `pctVal` per line; no tickers) | Every registered fund: Vanguard, Invesco QQQ, Schwab, ARK... Not unit trusts (SPY, DIA) or commodity / crypto trusts | 60 to 150 days, quarterly |

Coverage of the 5,730 active ETFs of the 2026-10-02 universe (listed by an adapter's directory):
State Street 181 (3.2%), iShares 480 more (8.4%), so **661 funds (11.5%) have a daily file**;
SEC N-PORT lists 3,949 of the rest, and the default `fallback_scope = "optionable"` reads the 480
of them that are optionable, so the default run covers **1,141 funds (19.9%)**, and **630 of
the 767 optionable ETFs (82%)**. `fallback_scope = "all"` reaches 4,610 funds (80.5%) at the
cost of a long first pass. Not covered by anything: gold and silver trusts outside iShares
(GLD, USO), the VIX ETPs (UVXY, VXX, SVXY, VIXY) and crypto trusts, which hold no securities
lines. A real sample of 53 funds on 2026-10-05 (SPY, QQQ, VOO, VTI, 6 SPDR and iShares funds, 33
optionable N-PORT funds picked at random or by name): every daily-file fund read; N-PORT found
a filing for 32 of 33 (the one miss, NVYY, has no N-PORT filing in its trust's list); as-of dates are 2026-10-01/02 for
daily files and 2026-05-31 to 2026-07-31 for N-PORT (funds with other fiscal years report on
other months). The first N-PORT fund of a large trust costs a few hundred small header
requests (ProShares, Tidal, GraniteShares: 270 to 630 N-PORT filings in the list, about two
minutes), the rest of the trust is free for that run.

Not used, with the reason:

- **Vanguard** (`investor.vanguard.com/.../portfolio-holding/stock`): a single-page app, the API
  path answers the HTML shell. N-PORT covers the funds.
- **Invesco** (`dng-api.invesco.com/.../holdings/fund?idType=ticker`): HTTP 406 for our
  User-Agent. We do not present a browser identity to get past it. N-PORT covers QQQ.
- **ARK** (`assets.ark-funds.com/.../ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv`): a daily CSV, but its
  robots.txt disallows every crawler. N-PORT covers ARKK.
- **Massive / Nasdaq** free tiers: no ETF holdings endpoint.

State Street's and iShares' robots.txt files do not disallow these paths. Neither site's terms
of use were confirmed to allow automated downloads of the public holdings files (the iShares
terms page could not be fetched); the owner should confirm, and `enabled = false` in `[ssga]`
or `[ishares]` turns an issuer off.

Linking: a holding's ticker becomes an instrument id through `SymbolResolver`, only for lines
the issuer says are U.S. listings (iShares: Location United States and asset class Equity;
State Street: local currency USD). N-PORT prints no tickers: its lines are matched by CUSIP to
tickers the State Street files print beside CUSIPs (`data.funds.holdings.known_cusips`), so
SPDR funds are read first. Cash, futures, bonds and unmatched lines keep their name only.

Pacing and cost: `[ssga]` and `[ishares]` 1 s between requests, SEC 0.2 s; raw files are kept
14 days (SEC 7). Each fund is read once a week on its own slot day (`[etf_holdings]
refresh_days`), N-PORT funds once per 30 days at most, funds an issuer lists but has no file
for once a window. The nightly reads the funds due, about a seventh of the covered funds.
Backfill by hand: `algotrade-ingest etf-holdings [--limit N] [--symbols SPY,QQQ] [--force]`.

## SEC EDGAR company details (implemented, phase 1.7)

| Data | Endpoint | Used for |
|---|---|---|
| CIK ↔ ticker ↔ exchange | `https://www.sec.gov/files/company_tickers_exchange.json` (one request) | CIK when the reference has none |
| One company | `https://data.sec.gov/submissions/CIK##########.json` | name, SIC code + description, state of incorporation, fiscal year end, website, former names, exchanges |

Free, no key. SEC's [fair-access policy](https://www.sec.gov/os/accessing-edgar-data) requires
a `User-Agent` naming the requester with a contact email and allows at most 10 requests/second.
The email comes only from `ALGOTRADE_SEC_CONTACT` in `.env`; it is never stored, logged or
committed. Requests are spaced 0.2 s apart (`[sec_edgar] min_interval_s`, shared by the
ticker map and submissions).

`algotrade-ingest company-details [--date D] [--force] [--limit N]` (and the nightly step after
the universe build, skipped unless `[sec_edgar] enabled` and the contact are set) writes a full
`instruments/company` snapshot per session. The CIK comes from the reference (Massive, phase
1.5) or, when missing, from the SEC ticker map (`BRK-B` → `BRK.B`, `ABR-PD` → `ABR$D`).
Incremental: only CIKs never stored or past their refresh slot (once per `refresh_days`, 30,
[spread over the window](#refreshes-spread-over-the-window)) are requested, so the first run
makes ~6k requests (~25 min) and a nightly run about 1/30 of them. 404 (no filings,
common for funds) is counted as `no_submissions`, not a failure; 403 and 5xx are failures
(run PARTIAL). Checked 2026-10-02: 13,295 reference rows, 6,055 distinct CIKs from the SEC
map; most ETFs have no CIK in that map and get no company row (UNKNOWN to selections).

`sector` is a heuristic mapping of SIC code ranges to market sectors (Technology, Health Care,
Financials, …; `sources/vendors/sec/sic.py`), falling back to one sector per SIC division;
`industry` is the SEC's SIC description and `sic_division` the official division.

## SEC EDGAR company facts (implemented, phase 2b.4)

`https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`: every non-dimensional XBRL
fact a company has filed (up to ~5 MB; requested gzip-compressed, ~10x smaller). Same contact
`User-Agent`, `sec` limiter and `[sec_edgar]` section as the other SEC sources
(`sources/vendors/sec/company_facts.py`, source `sec_company_facts`). We keep two concepts:

| Concept | Short name | Kept per filing |
|---|---|---|
| `dei:EntityCommonStockSharesOutstanding` (cover page, as of a date just before filing) | `dei` | each value; several values for one date are classes (companyfacts drops the class labels) and are summed, `class_values` counts them |
| `us-gaap:WeightedAverageNumberOfSharesOutstandingBasic` | `weighted_basic` | the filing's current period: latest period end, then the shortest span (comparatives and year-to-date dropped) |

Every row keeps `filed` (point in time), `period_end`, `form` and `accn`; amendments (10-K/A)
are their own rows with a later `filed`. Zero counts are dropped; a 404 (no XBRL facts, most
funds) is `NO_FACTS`, not a failure.

`algotrade-ingest shares [--date D] [--force] [--limit N]` (nightly after company details)
stores new facts in `instruments/shares` (docs/data/layers.md). The CIK comes from the latest
`instruments/company` snapshot, else the reference. **Classes:** companyfacts has no
class-specific counts, so every instrument of a CIK (GOOGL and GOOG) gets the company total.
Most multi-class issuers no longer tag the cover count, so they fall back to the weighted
average; Berkshire's last facts are from 2015 (class A equivalents), so BRK.A / BRK.B are
`STALE` in `fundamentals@v2`, not wrong.

Checked live 2026-10-03 (closes of 2026-10-02): AAPL 14.594B shares (dei, as of 2026-07-17)
→ $4.87T; KO 4.302B (dei, 2026-04-28) → $368.5B; GOOGL / GOOG 12.151B (weighted basic, Q2
2026) → $4.17T / $4.14T; BRK.B STALE. Four requests took ~0.3 s each.

**Backfill:** `algotrade-ingest shares` once (~6k CIKs at the 0.2 s `sec` pacing plus
download: about 30 to 40 minutes, ~1 GB of gzip raw kept 7 days, `[sec_edgar] raw_retention_days`), then
`algotrade-ingest rollups --from <first session> --to <last session> --only fundamentals@v2`.
A crashed run resumes where it stopped (same session); `--limit N` splits it into chunks.

### Refreshes spread over the window

Incremental SEC tasks (`company-details`, `shares`) refetch a CIK once per refresh window
(`[sec_edgar] refresh_days`, `facts_refresh_days`; 30 days), on the CIK's own slot day
(`crc32(CIK) % window`; `tasks/framework/refresh.py`). After a one-night backfill the CIKs
come due spread evenly over the next 30 nights (~200 a night) instead of all on night 30; a
slot day without a run is picked up by the next run. New CIKs always come first, then the
stalest, so `--limit` works through a backlog oldest first; `--force` refetches all.

## IBKR

### Live verification through IB Gateway (implemented, read-only)

[ADR 0026](../adr/0026-live-verification-ibkr.md). The nightly `verify` task compares a
session's stored values with IBKR's, through a local **IB Gateway** and `ib_async` (the
maintained fork of `ib_insync`). **Read-only by construction**, three layers:

1. `sources/vendors/ibkr/gateway.py` (`IbkrMarketData`) is the only module that imports
   `ib_async`; it exposes market data only and wraps the `IB` object in a guard that raises
   `ReadOnlyViolationError` for anything but the market-data calls it names. It never calls
   `IB.connect` (which syncs positions and account updates even with `readonly=True`): it
   performs only the API handshake.
2. `tests/libs/sources/vendors/ibkr/test_read_only_guard.py` fails on any order or account API reference
   (`placeOrder`, `cancelOrder`, `reqPositions`, `accountValues`, ...) in `src/` or `apps/`;
   an import-linter contract keeps `ib_async` imports in the facade.
3. The gateway's own **Read-Only API** setting (owner setup: README, "Live verification").

| Request (`ctx.sources["ibkr"]`, key) | IB call | Pacing |
|---|---|---|
| `bars/<SYM>`: ~260 daily TRADES bars (split-adjusted by IB) | `reqHistoricalData` | `ibkr` + `ibkr_historical` |
| `iv/<SYM>`: the underlying's 30-day implied vol, daily | `reqHistoricalData` (`OPTION_IMPLIED_VOLATILITY`) | `ibkr` + `ibkr_historical` |
| `div/<SYM>`: IB dividends (past / next 12 months) + close | `reqMktData` tick 456, streamed up to `stream_wait_s`, then `cancelMktData` | `ibkr` |
| `option_params/<SYM>`: listed expirations and strikes | `reqSecDefOptParams` | `ibkr` |
| `option/<SYM>/<expiry>/<C|P>/<strike>`: a snapshot quote | `qualifyContracts` + `reqTickers` | `ibkr` |

- **Pacing** (`[ibkr]`): every message waits `min_interval_s = 0.02` (IB allows 50
  messages/s); every historical request also waits `historical_min_interval_s = 10` (60 per
  10 minutes, never two identical requests within 10 s). Two shared limiter keys, `ibkr` and
  `ibkr_historical`, across threads and processes. About 7 minutes for ~22 names.
- **Market data type** `market_data_type`: 3 delayed (free, the default) or 1 live (needs a
  market data subscription). Historical bars do not depend on it.
- **Session lifecycle**: a `SessionSource` (`sources/framework/base.py`) built unconnected by
  the registry; `probe` checks the port (no API), `opened(source)` connects for the task and
  always disconnects. Gateway down: the nightly step is SKIPPED with
  "IB Gateway not reachable on host:port", never FAILED.
- **Raw**: every answer is saved as JSON under `raw/source=ibkr/dataset=market_data/`,
  kept `raw_retention_days = 30`.
- **Config**: `config/site/sources.toml [ibkr]` (`enabled = false` until the owner sets it
  up), host / port / client id from `ALGOTRADE_IBKR_HOST` / `_PORT` / `_CLIENT_ID`; what is
  verified and the tolerances in `config/site/verification.toml` (configuration.md).

### Enrichment: contract ids and IV history (implemented, read-only)

[ADR 0028](../adr/0028-ibkr-enrichment-source.md). IBKR enriches our own data; nothing it
gives replaces a free source, and what derives from it carries `licence = personal`
(personal-use market data). Same facade, same allowlisted calls (no new IB call was needed):

| Request (key) | IB call | Pacing | Table |
|---|---|---|---|
| `contracts__<SYM>+<SYM>...`: conid, primary exchange, security type, currency | `qualifyContracts` (one call per `contracts_batch` = 25) | `ibkr` (one slot per contract) | `instruments/ibkr_contracts` (task `ibkr-contracts`) |
| `volhist__<SYM>__<CONID>__<from>`: IB's daily 30-day implied vol and historical vol from a date to the session | `reqHistoricalData` x 2 (`OPTION_IMPLIED_VOLATILITY`, `HISTORICAL_VOLATILITY`) | `ibkr` + `ibkr_historical` | `volatility/ibkr_iv30`, `source_kind = history` (task `ibkr-iv --from/--to`) |
| `vols__<SYM>:<CONID>+...`: the IV and HV now | `reqMktData` generic ticks 106 + 104, `iv_batch` = 50 streams together, then `cancelMktData` | `ibkr` | `volatility/ibkr_iv30`, `source_kind = snapshot` (nightly `ibkr-iv`) |
| `quotes__<SYM>__<expiry>__<strike>+...`: the calls and puts of an expiry at those strikes now (bid, ask, last, close, volume, IB's model IV and delta) | `qualifyContracts` (once per contract per session) + `reqMktData` streams (bid and ask, or `stream_wait_s`), then `cancelMktData` | `ibkr` (one slot per contract) | `live/option_quotes` (the API's `/chains/{id}/live`, ADR 0028) |

- **Contracts**: every instrument of the option-chain coverage; new and renamed names the
  same night, the rest once per `contracts_refresh_days = 30` on a slot day by key (like the
  SEC refreshes); a name IB does not know is `NOT_FOUND` (asked again next run). Full snapshot
  per run. About 4.2k contracts in ~170 batches: a few minutes the first time.
- **Pacing, measured 2026-10-03** (paper login, delayed data type 3): a two-year IV or HV
  request answers in under a second; the wait is the limiter. IB's rules: no identical
  request within 15 s, no 6+ for one contract and tick type within 2 s, at most 60 per 10
  minutes (strict for bars of 30 s or less; daily bars are "soft"-throttled, at most 50 open).
  We keep `historical_min_interval_s = 10` for every historical request, so a backfill costs
  **2 requests x 10 s = 20 s per underlying: ~23 h for ~4.2k names** (AAPL + SPY took 33 s).
  It is resumable per underlying (an underlying whose history an earlier finished run fetched
  from the same start or earlier is skipped), `--limit N` caps a run, and the nightly
  continues it for `iv_backfill_per_night = 100` names (~33 min). Lowering
  `historical_min_interval_s` for daily bars would be allowed by IB but is the owner's call
  after watching the `ibkr_historical` pacing stats.
- **Nightly snapshot**: tick 106 (option implied vol of the underlying) works on delayed data
  on a paper login (checked 2026-10-03: AAPL, SPY, MSFT answered within 1 s; HV can lag, so a
  batch waits up to `stream_wait_s` for both). ~4.2k names in batches of 50: a few minutes.
  The snapshot is written to the session; a later history backfill of that session replaces
  it (runs merge per instrument, latest wins).
- **Features**: `ibkr_iv@v1` (IV30 / HV30 and the 252-session rank, percentile and status on
  IB's IV, the `iv_history@v2` rules); `iv_rank` / `iv_percentile` prefer it and fall back to
  ours, `iv_rank_source` says which (`config/site/features/volatility.toml`).
- **Gateway down or `[ibkr]` disabled**: both steps are SKIPPED with a WARN; `iv_rank` falls
  back to ours, labelled `ours`.

## What IBKR gives us

**Good for:**

- **Futures**: contract definitions, roll and expiry information, and historical bars. This
  is the main reason futures can be added later without a new vendor.
- **Option chains on a focused list**: chain structure (expiries and strikes) comes back
  in one call; quotes come with IB-computed IV and Greeks.
- **Stocks and ETF bars**: a second source to cross-check the free vendor.
- **Execution later**: the `Broker` protocol in `execution/` gets an IBKR adapter, so
  paper and live trading reuse strategy and risk code unchanged.

**Limits that shape the design:**

- Historical data pacing: **no more than 60 requests per 10 minutes**, no identical
  requests within 15 s (the `verify` task paces every historical request 10 s apart) ([IB docs](https://www.interactivebrokers.com/docs/tws-api/doc/market-data-historical/historical-data-limitations/pacing-violations-for-small-bars-30-secs-or-less)).
  The IBKR adapter must have a built-in rate limiter and resumable jobs.
- Quotes are per contract, and there is a cap on simultaneous market data lines. Pulling
  ~1M option contracts every night is **not practical**; IBKR suits a curated options
  universe (for example S&P 500 + the most liquid ETFs) rather than every optionable name.
- Needs TWS or IB Gateway running locally (with periodic re-login). The adapter treats
  "gateway down" as a normal, alertable failure.
- Live data needs market data subscriptions (for example the US Securities Snapshot and
  Futures Value Bundle, about $10/mo, waived above a monthly commission threshold); OPRA
  options data is a separate, small add-on. Delayed data is free for many products.
- IB's Greeks come from IB's own model. We still compute Greeks ourselves in `quant/`, so
  the numbers stay consistent if we switch vendors; IB values are kept as a cross-check.

## Options universe coverage

With the Cboe feed the **full** optionable universe (about 4.2k underlyings) is covered
nightly. IBKR is no longer needed for option chains; it remains the plan for futures, for
cross-checks and for execution.
