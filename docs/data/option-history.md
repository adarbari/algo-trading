# Bought option history: HistoricalOptionData Level 2 (ADR 0086)

End-of-day option chains from 2002 to the purchase date, bought once ($1,495), kept in a store of
their own on the external drive. **Personal licence**: nothing built from it may be shown to a
viewer without that licence, and no outcome, feature or verdict is derived from it yet (the licence
gate PR of ADR 0086 decision 1 comes first). The nightly product keeps serving the free Cboe chains
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
   `algotrade-ingest run option-history-put-check`. Tolerance, fixed in ADR 0086 before the full run:
   RMS of the daily return difference at most 5 basis points, cumulative gap at most 100 basis
   points a year. A miss is reported, never tuned away.

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
0086 (7.7 bp without 08-23). The two worst days are a pair, 08-23 (SPX -2.6% on the afternoon's tariff
news: the simulated put lost 116 bp, the index more) and 08-26 (the rebound): the signature of a mark
taken at another instant than the vendor's 16:00 quote, not of a wrong strike or carry (the carry of
14 days is about 7 bp in all). **Likely causes, unproven until the full run:** Cboe marks and rolls on
its own prices (a roll-time average, a settlement-time mark), not a 16:00 mid; the stand-ins named in
ADR 0086 decision 6; Cboe accrues the 3-month auction rate, not the par yield. This pass proves the
reader and the engine run on the vendor's files and agree on the level; it is not the trust check
(that needs the full history, many rolls, the SOQ settlement and `rates/treasury` back to 2002).
