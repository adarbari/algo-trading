# ADR 0022: A run's table writes publish atomically

**Status:** accepted (2026-10-03). Extends [0007](0007-point-in-time-data.md) (how runs
combine, what `as_of` sees) and [0010](0010-jobs-model.md) (runs and recovery). Code:
`storage/backends/` (`local_index.py`, `memory.py`, `run_selection.py`),
`tasks/framework/run.py` (`IngestRun`), `storage/tables/result_writer.py`.

## Context
A run writes several tables. Until now each write was visible the moment it landed. On
2026-10-02 a universe build wrote `instruments/reference` and `universe`, then failed at
`instruments/symbol_history`: the two tables it had written stayed live, so the reference
snapshot came from an unfinished run and disagreed with the symbol history.

## Decision
- **All or nothing per run.** Every table write of an `IngestRun` is **pending**: the
  files are written, but no read sees them. When the run finishes COMPLETE or PARTIAL,
  `commit_run` makes every partition it wrote visible at once; a FAILED run (an exception,
  or an explicit `failed`) drops them (`abort_run`). The writing run reads its own pending
  writes through `run.reader` (`StoreReader.including`; rollups read the rollups they just
  computed). Generic in storage (`TableStore.write(..., pending=True)`, `commit_run`,
  `abort_run`, `recover_runs`, `pending_runs`, `purge_pending_before`); every backend
  passes `tests/contract/storage/test_atomic_runs.py`.
- **Local mechanism.** A pending write appends to the run's journal
  (`tables/_txn/pending/<run>.jsonl`). A commit, under the store's commit lock: (1) writes
  a commit marker `_txn/commits/<run>.json` with the next commit sequence number (the
  decision point); (2) adds the run's entry (`seq`, `visible_at`, and the version it
  replaces as `prev`) to every touched partition's `_runs.json` under its index lock;
  (3) writes `_txn/seq` (the visibility point); (4) removes the marker and files no entry
  refers to. A read captures `seq` before opening any index and ignores later entries
  (falling back to `prev`), so one read (`read`, `read_range`) never sees half a commit. A
  resumed run (same run id) writes its new version under a fresh file name, so the
  committed version stays readable until the new one commits. Memory: the same, under one
  lock.
- **Crash recovery is deterministic.** A commit that reached its marker is completed by
  `recover_runs` (idempotent; every later commit or abort completes it first); until then
  no read sees it. A run that crashed before its marker is rolled back: at startup, under
  the ingest lock (where `JobRunner.recover` already runs), `recover_unpublished` drops the
  pending writes of every run whose record is RUNNING or FAILED (`IngestRun` saves a
  RUNNING record on entry), and marks a run completed by recovery PARTIAL (`recovered`).
  Pending writes with no record (a service run that died) are left to retention: the
  purge task aborts pending runs last written before the staging cutoff.
- **`as_of`: a run is known from its commit.** Rows keep `knowledge_ts` = when they were
  stamped (unchanged); the index records `visible_at` = the commit time, and a read pinned
  at `as_of` sees a run only if `visible_at <= as_of`. A backtest pinned at its launch time
  therefore never sees a run that committed after it started, even if its rows were written
  before. Ordering between runs is still by `knowledge_ts` (ADR 0007). Entries written
  before this ADR have no `visible_at` and count from `knowledge_ts`.
- **Services.** `ResultWriter.publishing(run_id, at)` gives backtests the same guarantee
  for their several result tables. Screens write one table, already atomic.
- Kept: chains staging and resume (staged items publish into the pending run at the end),
  restating runs, merge vs snapshot, the one-ingest-run lock.

## Consequences
- A failed build leaves the previous snapshot in force; re-running the build supersedes it.
- Cross-call consistency: two separate reads at `as_of = None` can straddle a commit; a
  reader pinned at `as_of` sees a consistent cut except for a commit in flight at the
  moment `as_of` was taken (its `visible_at` precedes the end of its apply by milliseconds
  to seconds). `dates()` may list a new partition of an in-flight commit whose read is
  still `None`.
- Files of a crashed run stay on disk, invisible, until recovery or retention removes them.
- The index format gains optional fields; old indexes read unchanged.
