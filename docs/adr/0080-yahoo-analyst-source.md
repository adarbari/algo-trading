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

## PR B design (built 2026-10-23, see the amendment below)
The reader chooses the vendor per (name, kind), FMP first: FMP's row set wins when its status is OK
or STALE; the other vendor's rows and its coverage markers for that (name, kind) are dropped, so a
flip from Yahoo to FMP leaves no mixed history. The groups move to `analyst_estimates@v2`,
`analyst_targets@v2` and `analyst_revisions@v2` with a `*_source` string column (`fmp` / `yahoo`);
revisions are null until 90 days of the new vendor's rows exist after a flip (sooner if it had already been fetching the name). Yahoo's and FMP's EPS
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

## Amendment 2026-10-23: PR B, the reader (built)
- **Choice.** `analyst_status.choose_vendor` resolves each name for FMP and for Yahoo from the frame
  the session sees (point in time, no look across names): FMP when OK or STALE, else Yahoo when it
  has a row or a non-FAILED marker (status not NOT_FETCHED), else FMP. `effective_snapshots` keeps
  only the chosen vendor's rows of the kind and its coverage markers (relabelled `fmp`, so the rest
  of the group reads as before); `history_of_chosen` does the same for the revisions' history from
  the estimates' `estimates_source`, so after a flip the new vendor's revisions are BUILDING /
  NO_PRIOR until its own snapshots span the windows (90 days, sooner if it had already been
  fetching the name). A fitness test checks every group
  reads through them.
- **Versions.** `analyst_estimates@v2`, `analyst_targets@v2`, `analyst_revisions@v2` (v1 in
  `SUPERSEDED`), each with `estimates_source` / `targets_source` / `revisions_source` (fmp / yahoo;
  fmp for a name neither has reached). Every v1 column is unchanged. The preset `eps_revision_up`
  gains v2 (v1 is immutable and names the superseded fields); `target_upside_high` and the forward
  formulas are expression features and moved by name. Ratings stay Finnhub-only (`@v1`, `personal`).
- **Licence of a mixed column (the decision).** A feature's licence is static per column, and the
  gate (0069) tests `licence in held`, so a column that holds FMP's value for one name and Yahoo's
  for another cannot carry two. Every column of the three groups carries the stricter, `yahoo`
  (`LICENCES` is ordered `open < personal < yahoo`; `strictest` takes the highest; expression
  features inherit it). `yahoo` is held by the owner only (`config/site/users.toml`,
  `DEFAULT_USERS`); nobody holds `personal` without `yahoo`, so no viewer loses a value they could
  read, but FMP-derived analyst values are now gated by `yahoo` too. A field the catalogue does not
  resolve fails closed to the strictest licence.
- **The ledger gate found and fixed.** The edge-trade ledger redacted a column only when its
  recorded licence was `personal` and the viewer lacked `personal`; a `yahoo` column (the analyst
  edges' scores) would have been served to a viewer holding `personal` alone, and the verdict /
  run licence took `min` of the strings. Redaction is now by any recorded licence the viewer does
  not hold, and the run's licence is `strictest`.
- **Currency limitation.** `parse_targets` gates on `financialCurrency` (the reporting currency), so
  an ADR such as TSM loses valid USD targets from Yahoo; a later change should gate on the listing
  currency. Estimates in another currency are dropped, as before.
- **Not done here.** The Financials panel moved to the v2 fields; it does not display the source.
  Showing "from Yahoo" beside a value is a later UI change (a Guide entry exists for each
  `*_source` field).
- **Holding `yahoo` requires holding `personal`** (`UserRecord` refuses otherwise). The ranking makes
  an expression over an IBKR (`personal`) and an analyst (`yahoo`) feature `yahoo`, and the gate
  asks for that exact licence, so a `yahoo`-only holder would otherwise read IBKR values.

## Amendment 2026-10-23b: the whole stock population, a backfill, a wider nightly (PR1 built)
Yahoo answers the small and mid caps FMP's free plan refuses, and no list of "names FMP refuses"
reaches them: after FMP's 90-day hold and its 250-call budget only a few hundred names ever
qualified. The owner wants Yahoo's data for every operating company.
- **Reverses decision 5 ("never a name FMP answers").** The population is the reference snapshot's
  `COMMON_STOCK` and `ADR` rows (`tasks/analyst/population.py`, about 5,600 names; ETFs and
  closed-end funds have no consensus, Yahoo answers 404), not only the scope list or FMP's refusals.
  The reader is unchanged: FMP first, and `effective_snapshots` drops Yahoo's rows for a name FMP
  chose, so a standby row is never served and no licence exposure is added (the columns already
  carry `yahoo`, decision "licence of a mixed column").
- **Changes decision 4's numbers.** `[yahoo] per_night = 360` and `run_budget_s = 900`: after the
  backfill about 5,000 names fall due over `refresh_days` (14), so a night takes 360. A name FMP
  does not answer is asked every `refresh_days` (the reader goes stale at 21 days, so the baseline
  stays at 14 or less); one FMP answers (Yahoo's row is a standby) every `standby_days = 45`. The
  nightly's candidates are every name Yahoo has answered plus FMP's refusals. **A 429 stops the
  step at once** (one, not three; three failed calls in a row still stop it), in the nightly and
  the backfill alike.
- **`analyst-backfill`** (a registry task in no workflow, `tasks/analyst/backfill.py`): one run is
  one batch of `[yahoo] backfill_batch = 500` names, committed, the ingest lock released, so the
  launchd nightly (which exits 3 while the lock is held) is never starved; paced at
  `[yahoo] backfill_min_interval_s = 0.3` (the spike answered 30 requests, 20 of them unpaced in
  0.9 s, all 200; the registry builds the source's shared limiter with that floor for this task
  only, a ceiling of 3 s, doubling on errors and halving after 50 clean calls; the nightly keeps
  its 1 s floor; sequential, no concurrent workers: the staging is not built for them); largest market cap first; resumable with no state of its own (an
  answered name is not due: `snapshot.history` now reads the run records of both task names, the
  200 days before the session, through `find_many`, not every run file). It does nothing, quietly
  (a COMPLETE record, saved nowhere, exit 0), until the nightly of the last closed session is
  complete. `scripts/ops/yahoo_backfill.sh` (the owner starts it, detached; README "Long runs")
  loops it until `due_remaining` is 0. After a 429 the loop waits 60 s, 5 minutes, 30 minutes and gives up after
  three in a row. Estimated cost: about 5,600 calls at 0.3 s plus latency (about 35 minutes) and
  12 batches of start-up and pause (about 6 minutes).
- **Not changed:** `check_analyst_backlog` and `check_finnhub_backlog` measure FMP's and Finnhub's
  coverage of the scope list, which this does not touch; the nightly acceptance check
  (`check_analyst_snapshot`) reads the `analyst-snapshot` run only.
- **PR2 (built, amendment 2026-10-23c below):** the scheduler.

## Amendment 2026-10-23c: a rolling baseline, event pulls and a cool-off (PR2 built)
The flat rule of 2026-10-23b ("asked again after `refresh_days`") put the whole population on
one weekly beat after the backfill: every name was due the same day, 14 days later. The
nightly Yahoo step now schedules by `tasks/analyst/yahoo_schedule.py` (pure; the step only
gathers its inputs and asks).
- **Rolling baseline.** Each name has a stable slot, `sha256(instrument_id) mod cycle`, counted from
  `[yahoo] cycle_anchor` (the backfill's day, 2026-10-23), and is due on that day of every
  cycle: `refresh_days = 14` for a name FMP does not answer, `standby_days = 45` for one FMP
  answers. About 1/14 (1/45) of the population a night, flat; a name keeps its slot whatever its
  history. A missed night is caught up the next (a name whose latest slot day came after its last
  answer, or a full cycle old, is due, stalest first); a name never asked is the stalest.
  It alone serves every name and is the whole schedule of a name with no known report date.
  Every name Yahoo serves stays within 14 days (18 at worst under load) of its last answer; the
  reader goes stale at 21 and the revisions need a snapshot within 7 days of 90 days back.
- **Event pulls on top** (`[yahoo] events_enabled`). Evidence (owner, 2026-10-23): analyst actions
  spike in the 3 days after a report (about 7.4% a day against 1.1% uniform), are flat before
  it, and a quarter's EPS consensus drifts continuously up to it, so estimate drift says nothing
  of timing; the pulls are timed by the report date. **Post:** the day after a report our own
  `earnings@v1` has seen (the session before's partition, point in time; tonight's rollup may not
  exist and a date known only later is never read), and once more about 3 days later only if the
  first pull showed nothing new; new data (a changed fingerprint or a newer analyst action
  date) ends it. **Pre:** one pull in the last week before the expected report (taken 3 days
  before; none if a pull was already made since the window opened): it stores the final
  pre-report consensus and refreshes the date. The date is `earnings@v1` / `earnings_expected@v1`
  of the session before; Yahoo's `calendarEvents` date, which every answer carries, is the
  fallback and the refresh; a date that is not after the session (stale, or past with no report
  seen) is unknown. The first sketch (enable about 83 days after the last pull, try daily until
  new data) guessed the gap; this is timed by the date and stops at the first new data.
- **One ceiling.** `[yahoo] nightly_ceiling = 600` calls a night (owner decision 2026-10-23: 400 saturated at the peak, 600 keeps every gap at 13 days; the 2026-10-23c measurement below was at 400), in this order: names near the
  reader's staleness (18 days, so a busy season never starves the baseline), post pulls, pre
  pulls (each largest market cap first), then the baseline (at most `per_night = 360`, stalest
  first, then largest cap). A small cap past the ceiling falls back to its baseline slot.
- **New-data detection.** The item status is `OK: fp=ab12cd34 next=2026-11-03 act=2026-10-20`
  (`status_label` splits at the colon): a fingerprint of the stable values (target mean, high,
  low; both annual estimates' period, average and analyst count; rating counts), not epsTrend's 7
  / 30-days-ago fields nor the month of the rating bucket; Yahoo's next report date and newest
  `upgradeDowngradeHistory` date. The one request now asks `calendarEvents` and
  `upgradeDowngradeHistory` too (still one request a name); no stored kind changes (the
  dates are item status only), so `history()` needs no store read and stays bounded (the run
  records of the 200 days before the session).
- **Safety.** The first 429 stops the step and records a `yahoo_cooloff` item (`k=` nights in a
  row, `until=`): no call for `2 ** k` nights (k at most 8), the next night's history reads it;
  a night with an answer and no 429 resets k. Three failed calls in a row still stop it. Kill
  switches: `enabled = false` (no Yahoo), `events_enabled = false` (baseline only). Never breaks the
  nightly (the step is optional and fail-soft).
- **Measured (simulation, 5,000 names, 60% reporting within four weeks, the rest spread over
  eight):** peak 325 event pulls a night, the ceiling saturated at the season's peak (mean 399 a
  night over 99 nights), worst gap since a name's last answer 19 days with a ceiling of 400
  (none past 21), 13 days with 600. Off season: about 70 event pulls and 300 baseline pulls.

## Amendment 2026-10-24: ratings and revisions from Yahoo (PR1 built: the columns)

Reverses two settled points: PR B said ratings stay Finnhub-only, and that the revision history is
only what we store. One `quoteSummary` answer already carries both a rating history and an EPS
consensus history; they are kept, labelled by where they come from.

- **Stored (PR1, ingestion).** `analyst/estimate_snapshots` gains four nullable float64 columns,
  `eps_trend_current`, `eps_trend_30d_ago`, `eps_trend_60d_ago`, `eps_trend_90d_ago`, from
  `earningsTrend.trend[].epsTrend` (the 7-day value is not kept). Additive: older partitions and
  FMP rows read null. The recommendation parse returns up to four rows, buckets `0m`, `-1m`, `-2m`,
  `-3m`, `period` the first day of the session's month less k months (UTC); the table key is per
  period, so all are stored. The schedule's fingerprint hashes only the newest month's counts, so a
  month roll or the added months fire no false "new data" pull.
- **Revisions (PR3, `analyst_revisions@v3`).** Taken in-series: `eps_trend_current` less
  `eps_trend_Nd_ago`, never `eps_avg` less `NdaysAgo` (different restatements). `NdaysAgo` is
  Yahoo's restatement as of the fetch day, so its `knowledge_ts` is the fetch day; a
  `revisions_basis` column says `own_snapshots` (our history) or `vendor_trend`. Yahoo has no revenue
  history: revenue revisions stay own-history.
- **Ratings (PR2, `analyst_ratings@v2`).** A `ratings_source` column (`finnhub` / `yahoo`): Finnhub
  first, then Yahoo; the mixed column carries licence `yahoo`. Yahoo's score change is the `0m`
  score less the `-3m` score from the same snapshot, null when `-3m` is missing or a count is 0.
  Buckets are calendar months, so the span is roughly 60 to 120 days. Yahoo ratings go stale at
  `yahoo_stale_days = 60` (a name FMP answers is refreshed by Yahoo only every `standby_days` 45).
- **No re-parse of raw.** A merge store would replace the original rows; the 14-day baseline
  refreshes every name with the new columns soon enough.
