# ADR 0060: A derived history copy serves long reads of session-grain tables

**Status:** accepted (2026-10-09, owner-approved design). Amends [0006](0006-storage-grains-and-adapters.md)
(physical layout) and [0022](0022-atomic-run-publication.md) (a derived artefact outside a run's
atomic publish, with its own staleness rule); extends [0007](0007-point-in-time-data.md). Does not
change [0036](0036-session-strictness-for-reads.md) (one-session reads keep reading partitions) or
[0005](0005-ingestion-is-the-only-writer.md) (ingestion is the only writer). Code:
`storage/backends/history.py`, `local.py` (`read_range`, `build_history`), `TableStore.build_history`.

## Context
A range read opens one Parquet file per session day. A market table since 1971 is 14,060
partitions: its full read takes 39 s (measured on the real store), and an Explore chart of one
instrument over one year reads 252 partitions of 12,000 rows each to keep 252 rows (0.7 to 1.0 s
for `bars/1d` and `rollups/instrument/price_stats@v2`). Retuning the partition read (ADR 0006's
column pruning, `ParquetFile` + filter) cannot remove the per-file cost.

## Decision
- **A derived copy, one Parquet file per (table, year)**, in `tables/<table>/_history/` (a path
  only `storage/backends/` knows, ADR 0006): zstd, sorted by `(instrument_id, session_date)`,
  row groups of 50,000 rows so a one-instrument read decodes one or two groups (min / max
  statistics prune the rest), `knowledge_ts` and `run_id` kept. A manifest per table lists the
  years built: file, the commit sequence it was built at, row count and the signature of every
  source partition. Files are written to a unique name and the manifest is replaced atomically
  last; a file no manifest names is deleted by the next build.
- **Contents are exactly what a read with `as_of` None resolves**: the rows `select_runs` /
  `merge_rows` (ADR 0007) give each partition at the build's commit sequence, with two hidden
  columns (`__day`, `__pos`) that let a read restore the partition path's row order. The copy
  is a cache of that resolution, never a second source: dropping the folder loses nothing.
- **A read uses it only when it is exact.** `read_range` serves a year from the copy when
  `as_of` is None, there is no `own_run` and the year is fresh for the requested days;
  otherwise it reads the partitions, per year, so one read can mix both. The frame is the same
  (rows, order, dtypes). All reads still capture one commit sequence first (ADR 0022), then check
  freshness, so a read never mixes the copy of one commit with partitions of another.
  An all-instrument read of fewer than 180 days stays on the partitions (the copy would decode
  a year to keep a stretch of it). One-session reads (ADR 0036) are not range reads and are
  unchanged. The memory backend keeps no copy (`build_history` returns `[]`).
- **Staleness rule (exact, per partition), amending ADR 0022.** The commit sequence cannot be the
  rule: it moves on every commit to any table, so every copy would be stale each morning. A
  partition's `_runs.json` is replaced by a rename on every commit, restate and purge, so its
  `(size, content digest)` (not inode or mtime: amended 2026-10-22, a clone or copy changes those and made every copy stale) identifies the version of everything the partition resolves to. The
  manifest holds each source partition's signature (none for a day without one); a copy serves
  the requested days of a year only if each has the recorded signature: a changed, restated,
  purged or new partition, or a store restored from another one with different indexes, fails it and the year reads partitions. A
  pending write changes no index, so it does not invalidate (it is invisible to the read too).
  The check is one `stat` per requested day once a file's digest is held in process (the first check of a file, or of a cloned one, reads it). A non-pending rewrite of a run goes to a new file name so its index entry changes. The build captures the signatures before and after
  reading the partitions and refuses (re-reads at a fresh sequence, `pinned_read`) when a commit
  was applied to an index but not yet published, or a partition changed meanwhile; so a matching
  signature can only mean the index was untouched since a state the build read in full. A copy
  that cannot be read (file gone after a rebuild, damaged) counts as stale. **Schema:** the year
  file holds the union of its partitions' columns, so a column added mid-year would read as nulls
  for earlier days where the partitions have none; the manifest lists the days whose resolved
  schema differs from the file's (`ragged`) and a read serves a year only if none of its
  requested days is ragged.
- **Building** is `TableStore.build_history(table, years)`: make the copy hold exactly these years
  and be current. A year whose signatures still match is kept; others are rebuilt, the rest
  removed; -> the years built. Ingestion calls it after its commits (a later change adds the
  workflow step); a build is outside any run's publish and needs no lock beyond a per-table build
  lock. Which tables and years are built is a configuration of that step: every market table in
  full, and the instrument tables the Explore charts read for the last two years (disk budget).

- **The nightly step (`history-copy`).** A non-critical `NIGHTLY` step, last (after the screens,
  descriptions and verify) and latest-session-only, `needs` bars, rollups and market-rollups, so
  every publish of the copied tables has committed and no commit contends for the build's
  fallback hold of the commit lock (13-48 s on the real store). Tables are site config
  (`nightly.toml [history_copy]`): every table under `market_prefix` for all years, the listed
  `instrument_tables` for the last `recent_years` calendar years. A table is skipped with a
  WARN when free disk is below `free_disk_floor_gb` plus the table's current copy (a rebuilt year
  exists twice), or when the event and instrument copies already hold `budget_gb` (a table not yet copied
  is not started; a table is added to the list only after its size is measured). Reads need no
  change: a skipped or failed night leaves a copy that reads detect as stale.

## Consequences
- Measured on the real store (read-only; copy written to a temp directory): `market_trend@v2`,
  all 56 years: built in 48 s, 1.9 MB (partitions 123 MB), full-history read 1.4 s (39 s from
  partitions), one-year read 17 ms (0.8 s). `bars/1d` 2025-2026: 13 s, 176 MB, 30-47 ms
  (0.9-1.0 s). `price_stats@v2` 2025-2026: 13 s, 280 MB, 20-26 ms (0.7-0.8 s). The copy frame
  equals the partition frame on that data.
- Disk: about 90 to 140 MB per instrument table-year (more for wide tables); the two-year,
  2 GB budget holds around seven wide instrument tables, so the step lists them.
- `TableStore.size(table)` counts the copy's bytes too (it is under the table's folder). A build
  deletes the temp file a crashed build left.
- A build holds one year of one table in memory (the sort); ingestion builds tables one after
  another.
- Two code paths return the same frame, kept equal by a property test (random runs, restates,
  partitions changed after the build, ranges, filters, columns) and a stale-fallback unit
  suite. A new way to change a partition without replacing its index would break the rule: the
  contract tests of `tests/contract/storage/` and the property test are where to see it.

## Amendment (2026-10-17): every instrument rollup is copied; short reads probe days
Explore's Features tab asks six `InstrumentHistory` requests of three months, one per 60 fields:
with only `bars/1d` and `price_stats@v2` copied, each read one whole-market partition per session
for every other table (0.35 to 1.5 s a request, 5.8 to 7.1 s a ticker on the real store, measured
with the response cache bypassed). The copy now covers **every instrument rollup group** (and
`bars/1d`), the last `recent_years` years: measured 1.34 GB for the 43 added tables (a build of
all of them takes about 3 minutes; the largest are `trend_stats@v2`, 328 MB, and `bands@v2`,
223 MB), 1.8 GB with the earlier two, inside the budget, which is raised to `budget_gb = 2.6` (2026 is 80% elapsed: the copies reach about 2.0 GB by year end, and a skipped table would silently slow Explore). A history request of 60 fields
falls to 0.11 to 0.2 s (0.3 to 0.4 s for the expression features, which also read the sessions of
the `exists()` groups; those are now kept per published state in `ctx.cache`). The tables are
listed in `nightly.toml`; `tests/unit/config/site/test_nightly.py` fails when a registered group
is missing, so a new group is copied from the start. A read still falls back to the partitions for
a year whose copy is stale, so nothing changes for correctness.

Two read-path changes ride along, neither a layout change: `LocalTables.read_range` probes the
days of a range of 31 days or fewer (one `stat` of the day's index each) instead of listing every
partition of the table (75 ms for `price_stats@v2`'s 4,200); and `instrument_view` reads only the
asked instruments' rows of a rollup (a partition with none of them is read whole, so "no row" and
"no partition" stay distinct) and joins all of a table's columns at once.

## Amendment 2026-10-19: the serving release (proposed, ADR 0077)
See [0077](0077-serving-release.md): a pinned read serves the copy only when every requested day's `partition_seq` is at most `upto`; releases retain the versions they name.

## Amendment 2026-10-22: events tables are copied, every year
**Why.** An instrument's events page (`InstrumentEvents`, `data.events.read_events`) reads each events
table over all time for one name. Events are partitioned by day, so that is one file per
partition per run: `events/fund_nav` holds 5,737 day partitions (9,617 files, 84 MB, 1.3 M rows for
280 closed-end funds) and cost 2.14 s for any instrument, 0 rows for a non-fund; `short_interest`
(211 partitions), `short_volume` (252) and `insider_transaction` (137 MB in 2 partitions, decoded
whole for one name) 0.1 to 0.25 s each. `events/filing_text` is left out of the read
(`data.events.NO_INSTRUMENT_ROWS`), not copied.

**Decision.** `nightly.toml [history_copy] event_tables` lists events tables copied for **every
year they have partitions** (an events read is over all time, like a market table), by the same
`build_history`, with the same layout, signature rule, memo (#814, #824), ragged-day rule and
fallback. Nothing in the read path changes: `read_range` serves an events table from the copy for
`as_of` None, no `own_run`, an instrument filter picking the row groups whose `instrument_id`
min / max can hold the id (`arrow.row_groups_holding`); a year whose signatures differ (a restated
or new ingest day) reads its partitions. A table must store `instrument_id`
(`tests/unit/config/site/test_nightly.py`; a table without the column is skipped with a WARN).

**Point in time.** The copy holds the rows `select_runs` / `merge_rows` resolve per ingest-day
partition, with `known_from` and `knowledge_ts` as stored; `read_events` applies `known_from <=
S` and the latest-version rule on the frame it gets, so the frame from the copy equals the
partition frame (`tests/unit/storage/backends/test_history_events.py`: a restated day, a second
run, a row known later, `through` before and after it). Events tables differ from market tables in no way the build handles: a restatement is a later
run in the partition of its `session_date` (often an old one: that year's signature changes and
the year is rebuilt, the others kept); several runs of a day resolve per `run_mode` as for any
table; `known_from` is data, never part of the copy's key.

**Size and build cost (measured on the clone, 2026-10-22).** Copies: `fund_nav` 3.2 MB (23 years),
`short_interest` 37.8, `short_volume` 32.0, `insider_transaction` 157.0 (6.4 M rows), `filing`
29.6: 260 MB in all. One build of the five from scratch: 20.8 s, peak RSS 3.1 GB (the insider
year sorts in memory; the nightly rebuilds the current year of `insider_transaction`,
`short_volume`, `short_interest` and `filing` in full, about 17 s and the same 3 GB, a few
minutes inside the nightly's last, non-critical step). Reads, `InstrumentEvents` for AAPL on the
clone, response cache off: first call 20.9 s to 2.0 s; the five tables alone, AAPL: 4.8 s cold /
2.9 s warm to 0.78 s / 0.14 s; a closed-end fund (ASA): 3.4 s / 2.7 s to 0.26 s / 0.13 s. The
other events tables (`dividend`, `earnings`, `split`, `reference_change`, ...) are under 9 MB in
at most 14 partitions and read in under 0.03 s: not copied. `budget_gb` rises from 2.6 to 3.0
(2.3 GB of instrument copies + 0.26 GB, with year-end growth; the event copies are built after
the instrument ones, so they never displace an Explore copy); free disk fell 16.45 to 16.20 GiB.

**Known cost.** Validating a year checks every calendar day's partition signature: an all-time read
checks about 8,400 days of `fund_nav` (one `stat` each once digests are held; the first read in a
process reads each day's `_runs.json`, about 1 to 2 s cold). A per-year digest from a persisted
per-table dates index removes it (follow-up, not part of this amendment); the copy already removes
the per-file Parquet opens that dominate warm.

## Changing the signature or format

A change to the manifest signature or the copy's format ships its rebuild in the same PR, with a
fitness test over an old-format store (`.claude/skills/add-dataset`, "Changing a derived store").
