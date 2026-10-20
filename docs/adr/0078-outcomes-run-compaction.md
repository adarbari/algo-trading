# ADR 0078: Outcomes run compaction: a value-exact index swap that moves no sequence

**Status:** accepted (2026-10-19; the owner chose E2 and accepted decision 2 below). Amends
[0022](0022-atomic-run-publication.md) (an index rewrite that changes no value at any `as_of` or
`upto` keeps the sequence) and [0053](0053-edges-hypotheses-outcomes-and-one-harness.md) (what an
outcome row's `knowledge_ts` means). Measurements: `docs/perf/outcomes-compaction-measurement.md`.

## Context
`outcomes/instrument/forward_returns@v2` is 24 GB in 4,222 partitions and about 111,000 files (the
volume was at 92 %). A partition S gets one run per window end T: the nightly recomputes
`RECHECK + 1` window ends (`tasks/derived/outcomes.py`) and each backfill re-runs a T, so old
partitions hold 17 to 32 runs, one file each. Over 20 sampled partitions, 53 % of the bytes are runs
whose every row a later run rewrote, and the rewrites are value-identical.

Two requirements bind the fix. The web must not slow down at any moment: its response caches key on
the **global** `visible_seq()`, which every commit, purge and `remove_runs` bumps. And no harness
answer may change: reads at `as_of` pick runs by `visible_from`, the latest row per key wins, and
ADR 0063 reuses a leg only when `partition_seq` and the recorded `knowledge_ts` agree.

## Decision
1. **Compaction is a compare-and-swap of one partition's index, never a commit.**
   `TableStore.compact_runs(table, day)` (local and memory backends; `StoreWriter` exposes it, only
   ingestion writes) writes the new files under fresh `run=<id>~<hex>` names, verifies them, then
   takes the commit lock, runs recovery, refuses a partition a pending run wrote to
   (`PartitionBusyError`), takes the index lock, and swaps only if the index still equals the one
   it planned from. It never writes `seq`: `visible_seq`, every web cache key and every
   `partition_seq` stay as they were, so the web cannot tell. The pure planner is
   `storage/backends/run_compaction.py`; the swap is `Commits.swap_runs`.
2. **Value-exact (scheme E2).** Take the partition's runs R1..Rn in selection order; the planner
   requires `knowledge_ts` order = `visible_from` order and no restating run, else it skips the
   partition with a reason. Rk is kept only if it adds keys or changes a column other than
   `knowledge_ts` and `run_id` against merge(R1..Rk-1); its new file holds just those rows, copied
   from the source with its schema and zstd. Kept entries keep their `knowledge_ts`, `visible_at`,
   `seq` and run id; Rn is always kept (empty if need be) so the partition's max seq is unchanged.
   Every prefix of the kept runs then has the same values as the original prefix, so every
   `as_of` and every read pinned at any `upto` returns the same values.
3. **An outcome row's `knowledge_ts` is when that value was first known.** A value-identical
   rewrite no longer restamps the row. This is the only observable change: a stamp can be earlier,
   never later, which lets ADR 0063 rule (c) reuse more legs (identical ones).
4. **Old files go 2 minutes after the swap**, so a read that resolved the old names finishes on
   them (else `StaleSnapshotError` and a retry of a whole range read). A crash leaves unindexed
   files, which `sweep_orphans` removes; a second pass finds nothing to do.
5. **The job** `algotrade-ingest run compact-runs --table T [--from D --to D] [--limit N] [--dry-run]`
   (`tasks/maintenance/compaction/`, beside `history_copy`; writes no run). Tables are listed in
   `config/site/nightly.toml [compaction] tables` (merge mode, no history copy: a fitness test; the
   history copy signs the index by inode, mtime and size). One partition at a time, background QoS
   (#734), `limit_threads`, one partition of scratch, refusing below `[resources] min_free_gb`;
   it stops between partitions when the `ingest` lock is held and resumes the next run. Before each
   swap it checks, at every `visible_from`, every `visible_from - 1 us` and `None`: same keys and row
   count, a sorted hash of the columns but the stamps, each row's `knowledge_ts` at or before the
   cut, and that every kept row exists unchanged in its source file.
6. **Stop the fragmentation.** The `outcomes` task writes only rows that are new or whose values
   differ from the stored view (a restating backfill still writes everything). A recheck that
   changes nothing writes no run. `check_outcomes` counts the merged view, so it still passes.
7. **Later, with its own ADR:** pack a partition's kept runs as row groups of one file (1 file per
   partition, still exact) once the backend selects a run by row group.

## Consequences
- Measured on 20 sampled partitions: bytes 115 MB to 55 MB (-52 %), files 505 to 355 (-30 %);
  extrapolated 24 GB to about 11.5 GB. The files drop little because each T's run covers different
  horizons' rows; step 7 is what reaches one file per partition.
- A fitness test stops compaction of a table with a history copy or in snapshot mode.
- Tests (each named in the PR that adds it): values equal at every cut point (no-op rewrites,
  revisions, new keys, a later column); `partition_seq`, `visible_seq`, `dates` unchanged; pending,
  restating or order-mismatch partitions skipped untouched; a commit between plan and swap aborts;
  crash before and after the swap, then sweep; a concurrent `read_range` loop never errors; second
  run a no-op; a read pinned at an old `upto`; `read_outcomes` / `outcome_seqs` / `outcome_stamps`
  equal but for earlier stamps; FULL and incremental `edge_eval` rows identical across compaction;
  the response-cache key unchanged; the writer's no-op re-run writes 0 rows, a delisting 1.
- Ownership: entries in `architecture/data_ownership.toml` (`run_compaction.py`,
  `Commits.swap_runs`) and `ingestion_ownership.toml` (the task), same PR.

## Owner decisions
1. **How exact:** E2 above (exact values at every `as_of`, -52 % bytes) or C1 (one file per
   partition, -67 % bytes, but a historical `evaluate-edges --as-of` inside a partition's write span
   reads empty and would be refused). Recommended: E2, the only one that meets "no harness answer
   changes" literally.
2. **Accept decision 3** (`knowledge_ts` = first known).

## Amendment 2026-10-20: parallel workers, a rolling sweep, three storage fixes
A serial run over ~1,100 `forward_returns@v2` partitions took too long (verification now takes
seconds, #751, so the planning and I/O per partition dominate). Decisions 4 and 5 change as follows;
the rest of the ADR stands.

- **Storage fixes first (blocking).** (a) `Commits.journal` / `pending_item` cached another
  process's journal for ever, so a long-lived worker missed a backfill that staged later, and
  `sweep` (which decides what a pending run staged) could delete a file that backfill had written
  more than 60 s earlier: a commit would then name a missing file. A journal this process did not
  stage is now re-read when `(st_size, st_mtime_ns)` changed (journals are append-only); only the
  staging process keeps its own in memory. (b) `swap_runs` returns `False` when a file the new
  index names (and the old one did not) is missing. (c) `sweep` also removes `.run=*.tmp`
  leftovers older than 60 s (a killed `atomic_write`).
- **Decision 4 (grace and sweep).** `SWAP_GRACE_S` 120 s becomes 30 s: a reader's window from reading
  the index to opening the file is one partition's eager `ParquetFile.read`, measured at 1.5 to 3 s.
  Correctness never depends on it (a lost file is a `FileNotFoundError`, then `StaleSnapshotError`,
  then a retry; after `OPTIMISTIC_TRIES` the read holds `no_commits`, which excludes sweeps).
  `ORPHAN_GRACE_S` stays 60 s. The job sweeps a swapped partition once 30 s + 1 s have passed since
  the parent saw the swap, as the run goes, and once more at the end; `[compaction]
  sweep_grace_seconds` is gone (derived from `SWAP_GRACE_S`), and so are `batch_size` and
  `pause_seconds` (nothing batches or pauses any more).
- **Decision 5 (the job).** `[compaction] workers` (default 4, `--workers N`) `spawn` processes, each
  with its own backend (opened from the data URL), `lower_priority` (the disk policy is per process),
  one Arrow thread (`worker_arrow_threads`), SIGINT ignored, SIGTERM turned into `SystemExit` (the
  partition in flight discards its files, then the worker calls `os._exit(143)`: the pool loop would
  otherwise catch it and wait for more work), exiting when its parent does. **A worker takes no
  lock**: `swap_runs` (a compare-and-swap under the commit lock) and `PartitionBusyError` already
  protect a partition from a writer (a commit after the plan or between verify and swap: "the index
  moved"; a pending run at the swap: `PartitionBusyError`; a run staged after the swap merges on
  top; every case discards the fresh files, counts in `skipped` and is retried next pass). The
  parent holds the `ingest-tree` lock for the whole run and probes the `ingest` lock (taken
  without waiting, released at once) before every dispatch and every sweep: held, it stops
  dispatching, the partitions in flight finish (each bounded by `partition_seconds`) and the rest is
  left for the next run. **`--beside-ingest`** (opt-in, off by default) skips the probe so the job
  runs beside a nightly or a backfill. The risk: it competes for disk and CPU with the ingest, and
  it relies on the journal fix above (without it a worker's stale journal could let a sweep delete
  a backfill's staged file); with the fix, a writer is protected by the swap's refusal. A worker
  silent for `partition_seconds + 60` s stops the run (the pool is terminated); SIGINT / SIGTERM
  stop the dispatch and terminate the workers. Free space: before each dispatch, at least
  `min_free_gb` plus `workers` times the largest partition seen. `--limit` counts partitions
  compacted plus in flight. Only the parent writes stderr (`[wN] day ...`, a summary each minute).
  `--dry-run [--verify]` runs through the same pool and takes no lock.
- **Tests (named in the PR):** a sweep spares a foreign run's file staged after its journal was first
  read (`test_local_index.py`, first); commits during the plan, between verify and swap, and a
  pending run at the swap swap nothing and leave no fresh file; a worker SIGKILLed after writing
  leaves a clean next pass; two worker processes on adjacent days beside a committing writer end
  value-exact with no deadlock; a `read_range` loop under sweeps never raises; the rolling sweep
  never runs before swap + grace (a fake clock, a failing `utime`); an ingest lock taken mid-run
  stops the dispatch and lets the partitions in flight finish; SIGTERM leaves no workers and no
  temp files; a swap naming a missing file is refused.
- **Later, optional:** a job state file of done / no-op digests would skip re-planning (about 26 min
  of planning at 4 workers).
