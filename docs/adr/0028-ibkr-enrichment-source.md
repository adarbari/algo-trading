# ADR 0028: IBKR as an enrichment source (read-only, personal licence, labelled fallbacks)

**Status:** accepted (2026-10-03, owner-approved: IV rank uses IBKR's IV history where
available, ours as the fallback, always labelled with its source; IBKR strictly read-only).
Extends [0026](0026-live-verification-ibkr.md) (the read-only facade, session sources),
[0023](0023-feature-store.md) (feature metadata, expression features) and
[0012](0012-data-vendors.md) (IBKR as a secondary source). Code:
`libs/sources/algotrade_sources/vendors/ibkr/`, `apps/ingestion/.../tasks/reference/ibkr_contracts.py`,
`tasks/market/ibkr_iv.py`, `src/algotrade/data/volatility.py`,
`src/algotrade/features/rollups/ibkr_iv.py`, `config/site/features/volatility.toml`. Vendor
notes and owner commands: [docs/data/vendors.md](../data/vendors.md#ibkr).

## Context
Our IV rank (`iv_history@v2`) ranks our own IV30, computed from the nightly Cboe chains; it
needs 60 sessions before it shows a rank and 252 before it is FULL, so it is UNKNOWN for
months after a name starts trading options or after we start collecting. IB publishes a
daily 30-day implied volatility of each underlying's options (and a 30-day historical
volatility) going back years, through the same read-only gateway the live verification uses.
That data is licensed for the account holder's personal use, unlike our own computations.

## Decision

### Read-only, unchanged
Every request goes through the facade (`gateway.py`, ADR 0026) and only through calls
already on its allowlist: `qualifyContracts` (contract ids), `reqHistoricalData`
(`OPTION_IMPLIED_VOLATILITY`, `HISTORICAL_VOLATILITY` daily bars), `reqMktData` /
`cancelMktData` (generic ticks 106 and 104: the underlying's option implied vol and
historical vol, streamed). No call was added; order and account calls stay blocked (tested),
and the AST guard is unchanged. Tick 106 was confirmed on delayed market data (type 3) on a
paper login on 2026-10-03.

### Two tables, one producer each
- `instruments/ibkr_contracts` (task `ibkr-contracts`, `tasks/reference/`): per instrument of
  the option-chain coverage, IB's `conid`, primary exchange, security type, currency and
  `resolved_at`. Snapshot runs (rows carried forward). New optionable names and renamed
  symbols are resolved the same night; every other name once per `[ibkr]
  contracts_refresh_days` (30) on its own slot day (`refresh.due_keys`), so the monthly
  refresh is spread over the month. Read through `data.reference.ibkr_contracts`.
- `volatility/ibkr_iv30` (task `ibkr-iv`, `tasks/market/`): instrument x session,
  `iv30_ibkr`, `hv30_ibkr`, `source_kind` (`history`: IB's daily bar; `snapshot`: the value
  streamed after the close). Merge runs: the latest run's row wins per instrument, so a later
  history backfill replaces a snapshot. Read through `data.volatility.ibkr_iv30` and the
  feature input of the same name.

### Pacing, backfill and the nightly
IBKR's historical-data rules: no identical request within 15 s, no 6+ requests for one
contract and tick type within 2 s, at most 60 requests per 10 minutes (the last is enforced
strictly for bars of 30 s or less; larger bars are "soft"-throttled, at most 50 open at once).
We keep the conservative shared limiter `ibkr_historical` (`historical_min_interval_s = 10`,
i.e. 60 per 10 minutes) for every historical request, the live verification's included.

- A **backfill** (`algotrade-ingest run ibkr-iv --from D1 --to D2`) makes ONE request per
  series per underlying for the whole range (2 requests: IV and HV). At 10 s each that is
  20 s per underlying: the ~4.2k optionable names take **about 23 hours**. It is resumable
  per underlying, within a run (`resume`) and across runs (an underlying whose history an
  earlier finished run fetched from the same start or earlier is skipped), and `--limit N`
  caps a run, so the owner spreads it over nights or a weekend.
- The **nightly** step (`ibkr-iv`, after `chains` and `ibkr-contracts`, before `rollups`)
  streams every underlying's IV and HV in batches of `[ibkr] iv_batch` (50; paper accounts
  have about 100 market-data lines), paced by the general limiter (50 messages/s): a few
  minutes for 4.2k names. It then backfills the history of up to `[ibkr]
  iv_backfill_per_night` (100) underlyings that have none yet (new names; the initial
  backfill spread over nights), about 33 minutes. Both IBKR steps are SKIPPED with a WARN when
  `[ibkr]` is disabled or the gateway is down; the email shows IBKR IV coverage, backfill
  progress (pending, estimated hours left) and the `ibkr` / `ibkr_historical` pacing.

### Features: IBKR first, ours as the fallback, always labelled
- Group `ibkr_iv@v1` (window kind): `iv30_ibkr`, `hv30_ibkr`, `iv_rank_252d_ibkr`,
  `iv_percentile_252d_ibkr`, `history_days_ibkr`, `rank_status_ibkr`, with exactly the rank
  rules of `iv_history@v2` (same function, same 60 / 252 thresholds in `rollups.toml`).
- Expression features (`config/site/features/volatility.toml`): `iv_rank` =
  `coalesce(ibkr rank, our rank)`, `iv_percentile` likewise, and `iv_rank_source` (`ibkr`,
  `ours`, or null when neither has a rank). A consumer that shows `iv_rank` shows its source.
  When IBKR is down for a session, `ibkr_iv@v1` has no rows for it and the fallback applies
  with the label `ours`.

### Licence tags
`Feature` gains `licence`: `open` (our computation from free data, the default) or
`personal` (derived from a personal-use market-data licence). Every `ibkr_iv@v1` feature is
`personal`; an expression feature takes the most restrictive licence of its inputs, so
`iv_rank`, `iv_percentile` and `iv_rank_source` are `personal`. The licence is in the feature
catalogue (`docs/data/features.md`) and the API's `/features` output. Today there is one
user (the account holder); when there are others, the API will hide `personal` features from
users other than the owner (a later change, recorded here).

### Live option quotes in the API
(Owner-approved 2026-10-03, PR B.) Screener candidates and the Explore chain show live
quotes: `GET /chains/{id}/live?expiry=D[&strikes=K...]` reads the calls and puts of one
expiry from IB Gateway, directly from the API process, through the same facade
(`IbkrMarketData.option_quotes`: `qualifyContracts` once per contract per session, then a
`reqMktData` stream per contract until each has a bid and ask or `stream_wait_s` passes, then
`cancelMktData`; all already on the allowlist, still no order or account call). Streams, not
snapshot requests: IB serves delayed data (type 3) to streams only (error 10090 for
snapshots, seen on the paper login 2026-10-03); outside trading hours only last, close,
volume and IB's model IV / delta arrive.

- **Session.** The API builds the `ibkr` session source from the registry (shared,
  cross-process limiters) with its own client id (`ALGOTRADE_IBKR_API_CLIENT_ID`, default
  `ALGOTRADE_IBKR_CLIENT_ID` + 1). One `SessionThread` (`sources/framework/session_thread.py`)
  owns it: nothing connects until the first request; a failed open or a lost session makes
  requests fall back at once for `[ibkr] live_retry_s`; a request waits at most
  `live_timeout_s`. No worker or queue process: the read is synchronous, in the request.
- **Cache.** An answer is reused for `live_cache_s` (60 s) per (underlying, expiry,
  strikes), in process (`services/live/quotes.py`, status `CACHED`). A request names at most
  `live_max_strikes` strikes (default: the `live_strikes` nearest the underlying), all of
  them in the stored chain, which supplies the contract ids.
- **Degrading, never failing.** `[ibkr]` disabled or not configured, the gateway down, busy
  or slow, or any other feed error: the answer is the stored delayed chain for the same
  strikes, `source = stored`, with `status` DISABLED / UNAVAILABLE / ERROR and a `detail`.
  The page always renders. A 404 only for an underlying or expiry the stored chain lacks.
- **The API's one write (amends ADR 0005 and 0024).** Each live answer is recorded,
  asynchronously, to `live/option_quotes` (contract x time taken; `session_date` = the
  exchange session it was taken in; `knowledge_ts` = when; `source = ibkr`). A bounded queue
  and one recorder thread (`services/live/recorder.py`) write each batch as one run, pending
  until it commits (ADR 0022); a full queue drops a snapshot (logged), a failed write is
  logged, and neither touches the response. Only `live/*` tables, only through
  `storage/tables/live_writer.py` (`LiveWriter` refuses any other table), enforced by two
  import contracts ("Live quotes write only live/* tables...", "Only the live-quotes recorder
  imports the live writer") and `ownership.toml` (`live-option-quotes`). Market and feature
  data remain the ingestion app's alone. The recorder's thread and the session thread are
  app infrastructure, not jobs: they are the two `allowed` exceptions to `job-execution` in
  `ownership.toml`. Recorder runs get run ids from `storage.runs` but no run records. `data.chains.live_option_quotes` reads them back;
  backtests never do (live rows are not point-in-time history of the stored chain), and like
  every IBKR-derived value they carry the personal-use licence.

### Share-class share counts: not available from IBKR (probed 2026-10-03)
Question (PR C): can IBKR give class-level share counts (BRK.A / BRK.B, GOOG / GOOGL) to take
precedence over the SEC company total in `instruments/shares`? Probe on the paper login
(client id 18, 5 read-only requests): `qualifyContracts` (BRK B, GOOGL) resolved both;
`reqFundamentalData(ReportSnapshot)` for each and `reqMktData` generic tick 258
(fundamental ratios) on BRK B all failed with IB error 10358 "Fundamentals data is not
allowed" (empty answers). IB's Reuters/Refinitiv fundamentals are not entitled on this
account, and contract details carry no share counts. **Decision: no IBKR share-count
ingestion.** `instruments/shares` stays SEC-only (company facts; every class of a CIK gets
the CIK's facts). `reqFundamentalData` was added to the facade's allowlist only for the
probe and was not committed: the allowlist is unchanged. Revisit only if the owner adds a
fundamentals entitlement (and then check its licence for personal use), or with another
class-level source.

## Consequences
- IV rank is available from day one for names IB covers, labelled `ibkr`; ours remains the
  fallback and the cross-check, labelled `ours`.
- A full backfill is a long, resumable job (about 23 hours at the default pace); the nightly
  grows by a few minutes for the snapshot plus up to ~33 minutes of capped backfill.
  Lowering `historical_min_interval_s` for daily bars is possible under IB's rules but is the
  owner's call after watching the pacing stats.
- Data derived from IBKR is personal-use: it must not be exposed to other users without
  revisiting this ADR.
- The API is no longer strictly read-only: it appends the live quotes it served to `live/*`
  (and nothing else). `live/option_quotes` grows with use (a few hundred rows a minute at
  most while a page refreshes), so it is kept for 7 days (`sources.toml live_retention_days`,
  default 7): the nightly `purge-raw` task deletes its partitions dated before
  `session - 7` (`TableStore.purge_before`); no other table is touched.
