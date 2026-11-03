# Bought option history: HistoricalOptionData Level 2 (ADR 0084)

End-of-day option chains from 2002 to the purchase date, bought once ($1,495), kept in a store of
their own on the external drive. **Personal licence**: nothing built from it may be shown to a
viewer without that licence, and no outcome, feature or verdict is derived from it yet (the licence
gate PR of ADR 0084 decision 1 comes first). The nightly product keeps serving the free Cboe chains
(`chains/*`); the two are never merged.

## What is stored (`option_history/*`, partition = session)

| Table | Rows | From |
|---|---|---|
| `option_history/quotes` | every listed contract of every underlying at the 16:00 New York snapshot: bid, ask, last, volume, open interest, the vendor's IV and delta (cross-check only), the underlying's price; `instrument_id` is the OSI contract id the Cboe pull uses, `symbol` the vendor's underlying, `underlying_id` an index id or the listing's id as of the session (null when none, counted) | `options_*.csv` |
| `option_history/underlying` | the underlying's day (OHLCV; the vendor's adjusted close is never stored) | `stockquotes_*.csv` |
| `option_history/stats` | the vendor's 30-day IV, volume and open interest by side | `optionstats_*.csv` |
| `option_history/dividends`, `/splits` | the vendor's facts, partition = ex-date; a later check compares them with `events/dividend` and `events/split` | the `stockhistory` zip |

Adjusted series (a root other than its underlying, `AAPL1`) are excluded and counted; nothing else is
filtered. `knowledge_ts` is the write instant. Read only through `algotrade.data.option_history`,
importable only by ingestion's import and checks.

## Runbook (the day the files are bought)

1. **Download** from your HistoricalOptionData.com account: the Level 2 daily or monthly zips (the
   monthly ones hold `L2_options_<date>.csv`, `L2_stockquotes_*`, `L2_optionstats_*`) and the
   `stockhistory` zip, into one folder on the drive, any depth, e.g. `/Volumes/<drive>/hod`. Keep
   the zips: they are the raw and the only way to replay an import (back them up).
2. **Point at the drive** in `.env`: `ALGOTRADE_OPTION_HISTORY_URL=file:///Volumes/<drive>/option-history`.
   The directory must exist (the drive mounted) and be formatted APFS or HFS+ (file locks, atomic renames).
3. **Mark it once**: `algotrade-ingest run option-history-import --init`. It writes
   `.algotrade-option-history` after probing a lock and a rename; an unmounted drive then fails
   instead of filling the boot disk.
4. **Look before you load** (the only samples seen are 2019): a dry run over one early and one
   transition month, and read the counts (`osi_mismatch`, `nonstandard_series`, `assumed_time`):
   `algotrade-ingest run option-history-import --source-dir /Volumes/<drive>/hod --from 2002-02-01 --to 2002-02-28 --dry-run`
   and the same for 2009-12 and 2010-02.
5. **Import everything** (the one command; resumable, one committed run per session, the nightly
   keeps running beside it; run it detached, a full import takes hours):

   ```bash
   nohup algotrade-ingest run option-history-import --source-dir /Volumes/<drive>/hod > var/logs/option-history-import.log 2>&1 &
   ```

   Run it again after a crash or a newly downloaded month: sessions already held (same zip-member
   checksum) are skipped; `--force` re-imports. Each session's counts are in its run record
   (`option-history-session`), in the history store, not on the admin pages.
6. **Trust check before any evidence**: load the Treasury curve back to 2002 (`algotrade-ingest rates
   --from 2002-01-01`) and the Cboe benchmark levels (`algotrade-ingest run macro`), then
   `algotrade-ingest run option-history-put-check`. Tolerance, fixed in ADR 0084 before the full run:
   RMS of the daily return difference at most 5 basis points, cumulative gap at most 100 basis
   points a year. A miss is reported, never tuned away.

## Option trade outcomes from the history (E5, ADR 0088 decision 11), the day after the import

Personal licence, owner-only evidence. Nothing here runs before the import and the trust check
(steps 5 and 6 above) are done, and before the main store holds what the engine needs from the
range start: Tiingo bars to 2002, `forward_returns@v2`, `rates/treasury` and `events/dividend`
(D8 loaded them from 2002-01-02; the task refuses a missing session of bars or the curve and says
which).

1. **Dry look**, one year first (this measures the batch time the plan estimated at 0.5 to 1.7 h a
   pass; the figures go in the PR or the status log, estimated against measured):

   ```bash
   algotrade-ingest run option-history-outcomes --from 2008-01-02 --to 2008-12-31 --batch 20
   ```

   It writes `outcomes/option/structure_pnl@v2` rows (`price_source = option_history`, licence
   `personal`) for the index underlyings and `SPY QQQ IWM` (`--symbols` names others; single names
   wait for the listing history of PR #968), only for windows entered before 2026-10-02 (the Cboe
   chains own the table from there). Read the summary record `option-history-outcomes-summary`:
   `coverage` and `refused` empty, `batches`, `rows`, `seconds`, `waited_for_nightly`.
2. **Everything**, detached (hours; resumable: a window end already written for the same positions
   and the same history import is skipped, `--force` rewrites):

   ```bash
   nohup algotrade-ingest run option-history-outcomes --from 2002-01-02 --to 2026-10-01 > var/logs/option-history-outcomes.log 2>&1 &
   ```

   It takes no run lock for the whole run: each batch is computed under the `ingest-tree` lock with
   no run open, then published under the ingest lock for that one publish (`wait=False`, retried a
   minute later), and never starts or publishes between the session close plus `settle_minutes` and
   `data_deadline` of an exchange day (`config/site/nightly.toml`, pacific time): the nightly runs
   beside it and waits at most one retry.
3. **PUT replication through the engine** (needs the `index_put_write` rows of step 2 and the PUT
   level, `algotrade-ingest run macro`):

   ```bash
   algotrade-ingest run option-history-put-engine-check --from 2008-01-02 --to 2026-09-01
   ```

   With more than one stored SPX position it lists the `position_key`s: name one with `--position`.
   Tolerance: the cumulative gap at most 100 bp a year (ADR 0084); the rows hold no daily marks, so
   the RMS is of roll-to-roll returns and reported only (`option-history-put-check` keeps the daily
   5 bp test).

## Chain feature groups from the history (F7, ADR 0088 decision 11), after the outcomes

The nine chain groups (`iv30`, `iv_history`, `implied_move`, `option_liquidity`, `iv_term`, `skew`,
`nearest_expiry`, `put_wing`, `call_wing`) for the sessions before 2026-10-02, written to the
**history root** under the same names (personal licence; read only through the splice,
`data/option_history/splice.py`, by the cross-section harness). Same pure computes as the nightly,
same runner; the chain tables of a history session are built from the history's quotes and the
vendor's IV and delta are never fed in. The Treasury curve, dividend yield and earnings come from
the main store (the same D8 coverage as the outcomes). One year first, then everything (batches of `--batch`, default 250 sessions, each a committed run
under the history store's lock and the `ingest-tree` lock; resumable: a session whose partition
was computed from the import now stored is skipped, a re-imported one recomputes, `--force`
recomputes all; the nightly keeps running):

```bash
algotrade-ingest run option-history-features --from 2008-01-02 --to 2008-12-31
nohup algotrade-ingest run option-history-features --from 2002-01-02 --to 2026-10-01 > var/logs/option-history-features.log 2>&1 &
```

The run record lists, per group, sessions, rows, skipped, `no_input` sessions and seconds (estimated
3-6 GB on the drive for all nine groups; measured on the first year). Single-name rows rest on the
importer's as-of-session `underlying_id`; names that died have none until PR #968's listing history.

## First replication of Cboe's PUT index (the 2019-08 sample, measured 2026-10-25)

One roll only: the sample holds 22 sessions (2019-08-01 to 08-30), so the put sold at the 2019-08-16
roll (SPX root, expiry 2019-09-20, strike 2890 against the index at 2888.68, premium 60.40 at the
16:00 mid) is marked each session to 08-30 (10 sessions after the roll) and set against the published
`PUT` level over the same dates; the July roll's put cannot be priced (no July quotes), and no put
expired in the window, so settlement is not exercised. Rate: the 3-month par yield of 2019-08-16
(1.87%, Treasury's own file; the stored `rates/treasury` starts 2024-01-02).

| | simulated (mid) | simulated (bid) | published |
|---|---|---|---|
| cumulative return 08-16 to 08-30 | +97.7 bp | +97.7 bp | +97.4 bp |
| cumulative gap | +0.35 bp | +0.35 bp | |
| RMS of the daily return difference | 11.3 bp | 11.5 bp | |
| largest daily difference | 27 bp (08-23), 19 bp (08-26) | 28 bp | |
| correlation of daily returns | 0.989 | 0.989 | |

The level agrees (0.35 bp over 14 days), the days do not: 11 bp RMS against the 5 bp tolerance of ADR
0084 (7.7 bp without 08-23). The two worst days are a pair, 08-23 (SPX -2.6% on the afternoon's tariff
news: the simulated put lost 116 bp, the index more) and 08-26 (the rebound): the signature of a mark
taken at another instant than the vendor's 16:00 quote, not of a wrong strike or carry (the carry of
14 days is about 7 bp in all). **Likely causes, unproven until the full run:** Cboe marks and rolls on
its own prices (a roll-time average, a settlement-time mark), not a 16:00 mid; the stand-ins named in
ADR 0084 decision 6; Cboe accrues the 3-month auction rate, not the par yield. This pass proves the
reader and the engine run on the vendor's files and agree on the level; it is not the trust check
(that needs the full history, many rolls, the SOQ settlement and `rates/treasury` back to 2002).
