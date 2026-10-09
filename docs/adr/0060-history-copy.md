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
  `(inode, mtime_ns, size)` identifies the version of everything the partition resolves to. The
  manifest holds each source partition's signature (none for a day without one); a copy serves
  the requested days of a year only if each has the recorded signature: a changed, restated,
  purged or new partition, or a restored store, fails it and the year reads partitions. A
  pending write changes no index, so it does not invalidate (it is invisible to the read too).
  The check is one `stat` per requested day. The build captures the signatures before and after
  reading the partitions and refuses (re-reads at a fresh sequence, `pinned_read`) when a commit
  was applied to an index but not yet published, or a partition changed meanwhile; so a matching
  signature can only mean the index was untouched since a state the build read in full. A copy
  that cannot be read (file gone after a rebuild, damaged) counts as stale.
- **Building** is `TableStore.build_history(table, years)`: make the copy hold exactly these years
  and be current. A year whose signatures still match is kept; others are rebuilt, the rest
  removed; -> the years built. Ingestion calls it after its commits (a later change adds the
  workflow step); a build is outside any run's publish and needs no lock beyond a per-table build
  lock. Which tables and years are built is a configuration of that step: every market table in
  full, and the instrument tables the Explore charts read for the last two years (disk budget).

## Consequences
- Measured on the real store (read-only; copy written to a temp directory): `market_trend@v2`,
  all 56 years: built in 48 s, 1.9 MB (partitions 123 MB), full-history read 1.4 s (39 s from
  partitions), one-year read 17 ms (0.8 s). `bars/1d` 2025-2026: 13 s, 176 MB, 30-47 ms
  (0.9-1.0 s). `price_stats@v2` 2025-2026: 13 s, 280 MB, 20-26 ms (0.7-0.8 s). The copy frame
  equals the partition frame on that data.
- Disk: about 90 to 140 MB per instrument table-year (more for wide tables); the two-year,
  2 GB budget holds around seven wide instrument tables, so the step lists them.
- A build holds one year of one table in memory (the sort); ingestion builds tables one after
  another.
- Two code paths return the same frame, kept equal by a property test (random runs, restates,
  partitions changed after the build, ranges, filters, columns) and a stale-fallback unit
  suite. A new way to change a partition without replacing its index would break the rule: the
  contract tests of `tests/contract/storage/` and the property test are where to see it.
