# ADR 0084: Bought end-of-day option history (HistoricalOptionData Level 2): a personal-licence store beside the Cboe chains

**Amended by [0088](0088-setups-as-positions-and-rules.md)** (proposed, 2026-11-01): derivations from the bought history (the one personal-derived-data rule, two derivations, the import allowance extended to them).

**Status:** proposed (2026-10-25; architect-reviewed once, findings applied). The owner chose the
vendor after comparing HistoricalOptionData Level 2 ($1,495 once, 2002 to present) with ORATS ($599, 2007 on).
Extends [0006](0006-storage-grains-and-adapters.md) (a grain), [0007](0007-point-in-time-data.md)
(history bought later), [0012](0012-data-vendors.md) / [0014](0014-cboe-options-source.md) (our own IV and
Greeks), [0018](0018-figi-instrument-ids.md) (ids), [0027](0027-vendor-sources-shared-package.md) (a vendor
folder) and [0069](0069-data-licence-gate.md) (the personal licence). **Amends** (decision 1, effective only
when its gate PR lands) [0064](0064-edge-evidence-series-and-trade-ledger.md) and
[0083](0083-workflow-first-trader-site.md). The nightly Cboe pull is untouched.

## Context
Setups on options (put writing on indexes and ETFs, a VIX-curve filter, covered calls that skip earnings,
conditional earnings premium selling) cannot be believed on our own chains, stored from 2026-10-02: a verdict
needs years, through 2008 and 2020, and names that later died. No free source gives survivorship-free
chains. HistoricalOptionData ("HOD", DeltaNeutral LLC) sells one file set per session: `options_<YYYYMMDD>.csv`
(every listed contract of about 4,300 underlyings at 16:00 New York: bid, ask, last, volume, open interest, its
own IV and delta; 0.9 M rows a day in 2019), `stockquotes_*` (the underlying's OHLCV), `optionstats_*` (30-day IV,
volume and open interest by side) and a one-off `stockhistory` set (dividends, splits, daily history); daily
zips, or monthly zips whose members carry an `L2_` prefix. It states that delisted symbols and corporate-event
contracts are kept and its bid and ask are raw 16:00 quotes, what the close-based harness reads. Measured on the
free samples (2019-08): 23% zero bids, no crossed quote, vendor IV above 12 at the 99th percentile. The two
file variants differ (a monthly file has `OptionExt` / `AKA` for `Blank` / `Alias`, a date-only `DataDate`, and
`stockquotes` adds an `adjustedclose` computed at download time, a lookahead we never store). The history is
about 115 GB zipped (400 to 500 GB as CSV) and will sit on an external drive. Ongoing data stays the free
Cboe pull; no recurring licence is bought. Only 2019 samples were available: the 2002-2009 files (OSI symbols
began in 2010) are first checked after purchase (decision 5).

## Decision
1. **Licence `personal`, and what that requires.** HOD's terms are personal, non-commercial use. Every table
   below says so in `tables.toml`. The first build reads the history only to import and to check it, and derives
   nothing: no outcome, feature or verdict is built from it. Before any is, a gate PR amends 0064 and 0083: an outcome
   table records a `licence`, the trial licence of 0064 includes the licence of the outcome's source, and a
   verdict resting on personal evidence is hidden from, and adds no Ideas picks for, a viewer without that
   licence (today the gate looks only at the screen's fields, so an open-licence Cboe screen over personal
   evidence would be shown to everyone). Owner decision, recommended: owner only until the owner has read
   HOD's terms on derived statistics and says otherwise. The repo is public: **test fixtures are synthetic
   rows in HOD's format, never the vendor's sample rows.**
2. **A separate grain and store, `option_history/*`.** Tables `option_history/quotes`, `/underlying`, `/stats`,
   `/dividends`, `/splits` (grain `option_history`; not `history/`, which names ADR 0060's derived copy).
   `chains/*` is not used: its readers take, per session, the run with the latest `knowledge_ts`, so importing
   a session Cboe already stored (2026-10-02 on) would replace the rows the product serves; its status and tier
   rows (ADR 0054) mean nothing for a bought file; six billion rows do not fit the main store. The two sources
   are never merged on read. The owner runs a one-off comparison over the overlap (about 17 sessions: mid, spread,
   open interest by contract), never nightly. Contract ids are the ones the Cboe pull uses
   (`OPT:<root><yymmdd><C|P><strike x 1000, 8 digits>`), built from the file's own expiry, type and strike
   columns; a vendor symbol whose suffix disagrees is counted (`osi_mismatch`), never trusted.
3. **Point in time (ADR 0007, no exception).** `session_date` is the `DataDate` day and must be an exchange
   session (a file that is not one FAILS its item); `ts` is the file's own time (a monthly file has none: 16:00,
   flagged `assumed_time`) in New York time, stored UTC; `knowledge_ts` is the write instant (we could not know
   a row before we stored it), `as_of` pins the version, and every evidence run built later records the
   history run ids it read. The history store is read **only** through `algotrade.data.option_history`
   (one reader, one `HistoryUnavailable` error, filtering on `symbol` because `underlying_id` can be null), and
   that package is importable only by the ingestion app's import, its verification checks and (later) the
   derivation of a history-fed outcome table in the *main* store, which is where `services/evaluation` reads
   it under ADR 0053 (`outcomes/option/structure_pnl` with a `chain_source`, a later amendment). Enforced by an
   import-linter `protected` contract, a fitness test copied from the outcomes quarantine, and a test that only
   ingestion calls the new `config/env` getter.
4. **Rows and ids.** Kept: bid, ask, last, volume, open interest, the vendor's IV and delta (a cross-check
   only), `UnderlyingPrice` (SPXW has no `stockquotes` row). Dropped: `Exchange`, `Blank`/`OptionExt`,
   `Alias`/`AKA`, gamma, theta, vega, `adjustedclose` (we compute ours from bid and ask, ADR 0021, downstream).
   Nothing is filtered (zero bids stay) except the **non-standard series**: a root different from its
   underlying (`AAPL1` after a split) is excluded and counted, as the Cboe pull does. `underlying_id` resolves
   as of the session through `SymbolResolver.from_listings(listings, S)` (the listing history, strict: never
   the `EQ:<symbol>` fallback, never the earliest snapshot for an earlier date) and is null with a counted
   reason when unknown; the index underlyings (SPX and SPXW, RUT and RUTW, NDX and NDXP, VIX and VIXW, XSP,
   OEX, XEO, DJX, BKX, SOX, OSX) map to `IDX:<key>` through a declared table in the vendor adapter, the `root`
   column keeping AM and PM settlement apart.
5. **Storage and import.** Parquet through `storage/backends` only, one partition per session, snapshot runs,
   sorted by `(symbol, expiry, strike)` in row groups of 65,536 rows clustered by `symbol`, kept forever; 10.8 MB
   a day measured on one 2019 session (zstd), so roughly 70 to 90 GB in all. The store is its own root at
   **`ALGOTRADE_OPTION_HISTORY_URL`** (`config/env.py`; unset: unavailable, never a default under `var/`) and
   must hold a sentinel file `.algotrade-option-history` (made by `--init`, which also probes that the drive
   supports file locks and atomic renames), checked before the backend opens, because the lock creates missing
   directories: an unmounted drive must not fill the boot disk. `option-history-import <folder>` takes the
   history backend's own lock and runs `recover_unpublished` against it, never the main ingest lock
   (the nightly keeps running); one committed run per session (a bad day fails its item, not 6,000
   sessions); a session whose published run holds the same zip-member CRC is skipped, a changed CRC is a newer
   run; where a daily and a monthly zip hold one session the later-named zip wins. It SUCCEEDS or FAILS by
   its acceptance check (zero rows, a mixed day, a non-session day, options without `stockquotes`, nothing
   imported while files existed). `--dry-run` parses and reports and stores no data (it needs the initialised drive and saves only its batch run record, counting `parsed`, not `imported`): the first run after purchase
   is a dry run over one 2002 month, then 2009 / 2010, to see the symbol and column variants. It runs detached
   (`nohup`, a status file under `var/logs/`), is in no workflow, and its run records live in the history store
   (the admin pages do not show them). The raw store is not used: the zips are the raw and the only way to
   replay an import, so the owner backs them up; each run record names the zip, member, size and CRC.
6. **First use: the trust check.** Before any evidence from the history is believed, a verification check
   (`tasks/verification/`, reading the history through the reader, result in its run record) replicates Cboe's
   PUT index (sell the at-the-money SPX put each monthly roll, T-bills as collateral from `rates/treasury`,
   which must reach back to 2002) and compares it with the stored level (`macro/series` `PUT`, `WPUT`, `BXM`,
   `BXMD`, `CNDR`, Cboe static files, personal licence). Three things a close-based file cannot match are named
   up front: Cboe sells on a roll-time average (about 11:30 to 12:00 New York), not the close, so the close quote
   is a stand-in (and the 3-month par yield, simple, actual / 360, stands in for the auction rate Cboe accrues); an SPX put expires on the AM opening settlement (SOQ) price, not the 16:00 quote; a monthly
   expiry falls on a Saturday before 2015. **Tolerance, fixed before the full run:** the RMS of the daily return
   difference is at most 5 basis points and the cumulative gap at most 1% a year; a miss is reported, never
   tuned away. BXM follows PUT.
7. **Cross-check of corporate actions.** HOD's dividends and splits are stored as the vendor's facts
   (`option_history/dividends`, `/splits`; partition = ex-date, runs merge) for a later verification check against
   `events/dividend` and `events/split`; they never enter those tables (not built in this PR).

## Consequences
- A second store root to mount, back up and not lose; every consumer opens it through one reader.
- Backtests of chains over 2002 to 2026 become possible only through a derived main-store outcome table, which
  needs the licence gate (decision 1) first.
- Reading one underlying over 6,000 partitions opens 6,000 files; unmeasured on the drive (`[I]`): measure a
  full-history one-name read after the import; a per-year copy (ADR 0060) is the fix if it is slow.
- Risks: snapshot semantics before 2008 may differ (the trust check shows it); the vendor may revise past files
  (a re-import is a newer run); ids of long-dead names are often null (the counts are the disclosure); symbol
  changes at the vendor are not reconciled (the contract id, not the symbol, is the join).
