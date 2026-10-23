# ADR 0080: Yahoo as a second analyst source, stored first and read later

**Status:** accepted (2026-10-22; owner decisions in session: two PRs, the new licence tag `yahoo`
held only by the owner; the architect reviewed the plan). Extends
[0068](0068-analyst-data-vendors.md) and [0027](0027-vendor-sources-shared-package.md); follows the
licence rule of [0028](0028-ibkr-enrichment-source.md) and the optional-step rule of
[0055](0055-optional-source-tables-warn.md). Code: `libs/sources/algotrade_sources/vendors/yahoo/`,
`tasks/analyst/snapshot.py` (`_yahoo`). This is PR A (store only); the reader is PR B (below).

## Context
FMP's free plan is gated by symbol: 15 of the 104 scope names and 2 of 25 S&P 500 mid-caps answer,
so most names read `NOT_COVERED` in every analyst feature group. Finnhub's free plan serves only
recommendation counts. Yahoo Finance has the missing pieces (targets, forward estimates, counts) for
the names tried (ARX, SSTI, CRWV). Spike 2026-10-22 (yfinance 1.7.0, no key): the package's per-property
calls cost six requests a covered name and 12 to 15 for an unknown symbol (crumb refreshes), but ONE
`quoteSummary` GET with `modules=financialData,earningsTrend,recommendationTrend` returns all three
kinds; 30 requests (10 at 0.5 s, 20 unpaced) all answered 200 with no 429; a bogus symbol 404s after
three requests (the crumb dance); an ETF 404s `No fundamentals data`. There is no published limit
and the endpoint is unofficial; community reports are of 429s per IP under heavy use.

## Decision
1. **Placement (ADR 0027).** A vendor folder `vendors/yahoo/` (by vendor, like `fmp` and `finnhub`;
   not `yfinance`, which would shadow the PyPI package), source `yahoo_analyst`, class `YahooAnalyst`
   (raw source `yahoo`), section `[yahoo]` (every name is `yahoo`; the brief had `[yfinance]`), limiter
   key `yahoo`. `yfinance` is a dependency of `libs/sources` and is imported lazily, on the first
   request, by the vendor's own transport (`SourceSpec.transport`): the API imports the sources
   package and must not load `curl_cffi`. The transport only turns the framework's GET into
   `YfData.get` and maps errors, so retry, pacing and the breaker stay `framework/http.py`'s.
2. **One request a name**, and a floor of `min_interval_s = 1.0` because `YfData`'s hidden crumb
   requests bypass the limiter. 404 (unknown symbol, or no fundamentals) is `rejected`: raised at
   once, read as `NOT_COVERED`, and held four refresh windows (as Finnhub's retry). 401 is an error,
   never a refusal. Cookie and timezone caches live in `[yahoo] cache_dir` (`var/cache/yahoo`).
3. **Licence tag `yahoo`, owner only.** Yahoo publishes no API terms for this use and its terms
   forbid scraping (`docs/edge-ideas/build-plan.md`, `docs/data/vendors.md`: unofficial, grey), so the
   data is personal use of the owner: never served to another viewer, never redistributed. PR A only
   records `licence = "yahoo"` in `[yahoo]`, the run stats and `tables.toml`; the feature `Licence`
   literal, `users.toml` handling and the feature groups are PR B, so nothing reads the rows until
   they exist (the readers filter by `source`).
4. **Fail-soft and capped.** The step stays optional (0055): every error is a `FETCH_ERROR` item and a
   `FAILED` marker (asked again next night); three failed calls in a row (the breaker's 403 / 5xx
   count does not see a 429) stop the step and the names left are `OVER_BUDGET`. `[yahoo] per_night
   = 60`, `refresh_days = 14`, and its own `run_budget_s = 600` so the shared `[fmp] run_budget_s`
   cannot starve it (it runs last). Its calls are not counted in `budget.py` (FMP's alone).
5. **Whom it asks.** Only names whose last FMP outcome is a refusal (`history` drops a name once FMP
   answers it; the end of FMP's 90-day hold does not release it, FMP's budget may delay asking again) or refused
   tonight; never a name FMP answers. With no FMP built, every name FMP never answered. Due names
   largest market cap first.
6. **Snapshots from the first fetch**, no history: Yahoo restates, so as for FMP and Finnhub the
   history that is point in time is the one we store (0068). Rows carry `source = "yahoo"`, plus a
   `kind = "coverage"` marker per attempt. `analyst/estimate_snapshots` gains a nullable
   `currency string` (additive: old partitions read null). A name not in USD stores no estimates,
   and none of the targets when `financialCurrency` is not USD, until the forward formulas handle
   currency; counts are kept. Raw answers are kept `raw_retention_days = 365`: Yahoo cannot replay
   a past day.
7. **The not-covered rule is unchanged.** A name FMP refuses that Yahoo has not yet reached stays
   `NOT_COVERED` (true of FMP); a reader does not look across names or vendors to call it
   `NOT_FETCHED`.

## PR B design (decided now, built later)
The reader chooses the vendor per (name, kind), FMP first: FMP's row set wins when its status is OK
or STALE; the other vendor's rows and its coverage markers for that (name, kind) are dropped, so a
flip from Yahoo to FMP leaves no mixed history. The groups move to `analyst_estimates@v2`,
`analyst_targets@v2` and `analyst_revisions@v2` with a `*_source` string column (`fmp` / `yahoo`);
revisions are null until 90 days of the new vendor's rows exist after a flip. Yahoo's and FMP's EPS
bases differ (which EPS an analyst reports), so the two are never differenced. Ratings stay
Finnhub-only. `parse_targets` gates on `financialCurrency` (the reporting currency), so an ADR such as
TSM loses valid USD targets; PR B should gate on the listing currency instead. The `yahoo` licence is owner-only: the groups carry it and a viewer without it reads
`UNKNOWN`, not the value.

## Consequences
- The store starts collecting Yahoo's view of the refused names now, so PR B has history on day one.
- A new unofficial dependency whose failure only warns; the nightly never depends on it.
- If Yahoo starts blocking, the step stops after three failed calls in a row (`CircuitBreaker.record`
  resets on a 429 and transport errors never reach it, so the breaker cannot be relied on) and
  `per_night` is the knob; nothing downstream
  reads the rows until PR B.
