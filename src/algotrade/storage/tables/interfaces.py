"""Storage protocols. Every backend implements all of them and passes tests/contract/storage."""

from collections.abc import Collection, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from algotrade.storage.locks import Lock
from algotrade.storage.runs import RunRecord


@dataclass(frozen=True)
class CompactionReport:
    """What ``compact_runs`` did (or, in a dry run, would do) to one partition."""

    files_before: int = 0
    files_after: int = 0
    bytes_before: int = 0
    bytes_after: int = 0
    runs_dropped: int = 0
    skipped: str | None = None  # why nothing was changed (never an error)


class TableStore(Protocol):
    """Point-in-time tables partitioned by (table, session_date, run_id).

    Writing the same (table, date, run) again replaces it (idempotent). A different run for
    the same date is kept alongside. Which runs a read at ``as_of`` sees follows the table's
    run mode (``TableSpec.runs``; ``storage/backends/run_selection.py``): a ``snapshot``
    table gives the latest run known at ``as_of``; a ``merge`` table (events) the union of
    the runs known at ``as_of``, the latest run's row winning per table key, starting from
    the latest run written with ``restates=True`` (a rewrite of the whole partition).

    **Atomic runs (ADR 0022).** A write with ``pending=True`` is not visible until
    ``commit_run(run_id, at)``, which makes every partition the run wrote visible at once
    (``at``: what ``as_of`` compares with); ``abort_run`` drops them. A single read never
    sees part of a commit. ``own_run`` lets the writing run read its own pending writes.
    A store crashed mid-commit is completed by ``recover_runs`` (and by the next commit);
    a run that crashed before committing stays invisible until aborted.
    """

    def write(
        self,
        table: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        restates: bool = False,
        pending: bool = False,
    ) -> None: ...

    def commit_run(self, run_id: str, at: datetime) -> int:
        """Publish every pending write of ``run_id`` at once; -> partitions published."""
        ...

    def visible_seq(self) -> int:
        """The latest committed publish sequence (0 before any commit). Read-only: never
        recovers or writes. It rises with every commit that publishes a partition and with
        nothing else, so it is the cache-validity signal for readers (ADR 0022)."""
        ...

    def partition_seq(self, table: str, start: date, end: date) -> dict[date, int]:
        """Per committed partition with ``start <= session_date <= end``, the highest commit
        sequence of any run in its index (a replaced version included; an entry with no
        sequence, from a direct write or before ADR 0022, counts 0). Pending writes are
        ignored. A partition's value rises when a run commits or restates it and the date
        is absent once it is purged: the stamp ADR 0063 compares to know a read is unchanged."""
        ...

    def abort_run(self, run_id: str) -> int:
        """Drop the pending writes of ``run_id`` (and their files); -> partitions dropped."""
        ...

    def pending_runs(self) -> list[str]:
        """Runs with pending writes, committed by nobody yet."""
        ...

    def recover_runs(self) -> list[str]:
        """Complete commits a crash interrupted; -> their run ids. Idempotent."""
        ...

    def purge_pending_before(self, cutoff: datetime) -> int:
        """Abort pending runs whose last pending write was before ``cutoff`` (retention for
        runs that crashed); -> the number of runs aborted."""
        ...

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        own_run: str | None = None,
    ) -> pd.DataFrame | None: ...

    def read_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        own_run: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """All partitions with ``start <= session_date <= end``, each resolved point-in-time
        exactly as ``read`` would (runs merged per partition, not across partitions),
        concatenated in date order, all as of one commit. ``None`` if none exist.
        ``columns``: read only these (a partition without one has none) plus
        ``instrument_id`` and the point-in-time columns."""
        ...

    def read_latest_runs(
        self,
        table: str,
        session_date: date,
        group: Sequence[str] = ("user_id", "config_id"),
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
        own_run: str | None = None,
        upto: int | None = None,
    ) -> pd.DataFrame | None:
        """The rows of each ``group``'s newest run in a partition (ADR 0029 amendment), for a
        table whose runs each hold their group's whole result (``TableSpec.whole_per_group``;
        ``ValueError`` otherwise): what ``read`` then ``last_run_rows`` per group gives, without
        decoding the older runs. The newest run is the latest by (``knowledge_ts``, run id) among
        the runs a read sees (a pending ``own_run`` included; no ``as_of``), chosen from the index
        and the files' footer statistics and read inside one pinned sequence (``upto``: the
        caller's, else a fresh one); a restating run, or a file whose groups the statistics cannot
        name exactly, reads the whole merge and keeps each group's newest run, same rows.
        ``columns`` and ``instruments`` as ``read_range`` / ``read`` (the group columns come with
        them; an ``instruments`` matching nothing: an empty frame). ``None``: no run in the
        partition.
        The newest run is chosen before ``instruments`` filters it, so a group's older run is
        never read for an instrument its newest run dropped."""
        ...

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        own_run: str | None = None,
        columns: Sequence[str] | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """One committed run's own rows of a partition (those stamped with its ``run_id``),
        whether or not it is the partition's latest run and without reading any other run's
        file (ADR 0064). ``None``: the run has no committed rows there (``own_run`` also
        sees that run's pending write). ``columns``: only those (plus ``read_range``'s key and
        point-in-time columns) are decoded; ``instruments``: only their rows (row groups that cannot
        hold them are skipped; ``None`` when it matches none of the run's). Not point-in-time: a
        run is read as it left them."""
        ...

    def build_history(self, table: str, years: Sequence[int]) -> list[int]:
        """Make the table's derived history copy (ADR 0060) hold exactly ``years`` and be
        current, rebuilding only the years whose partitions changed; -> the years built. The
        local backend writes one Parquet file per year that ``read_range`` then serves (same
        rows and order as the partitions); the memory backend keeps no copy and returns ``[]``.
        Not part of a run: ingestion calls it after its commits."""
        ...

    def history_size(self, table: str) -> int:
        """Bytes the table's history copy takes (0 when it has none)."""
        ...

    def history_current(self, table: str, day: date) -> bool:
        """Whether the history copy holds ``day``'s partition as it is now (False: no copy, or
        one built before the partition's last commit; the memory backend has none: True)."""
        ...

    def free_bytes(self) -> int:
        """Bytes free on the volume the store is on (the history build's disk floor)."""
        ...

    def dates(self, table: str, own_run: str | None = None) -> list[date]: ...

    def names(self, own_run: str | None = None) -> list[str]:
        """Every table with at least one partition, sorted."""
        ...

    def size(self, table: str) -> int:
        """Bytes the table's committed partitions take in the store (every run kept)."""
        ...

    def drop(self, table: str) -> int:
        """Delete every committed partition of ``table`` (every run): an admin operation for
        retiring a superseded table (``retire-features``), never part of a run. -> partitions
        deleted."""
        ...

    def purge_before(self, table: str, cutoff: date, keep: Collection[date] = ()) -> int:
        """Delete the committed partitions of ``table`` dated before ``cutoff`` (every run) but
        those dated in ``keep``: retention for tables that are not kept forever (``live/*``,
        the edge ledger, whose kept runs' partitions are spared); -> partitions deleted."""
        ...

    def partition_runs(self, table: str, session_date: date) -> list[str]:
        """The committed runs of one partition, oldest commit first (runs with no commit
        sequence, from before ADR 0022, first). Empty: no such partition."""
        ...

    def purge_runs(self, table: str, session_date: date, runs: Collection[str]) -> int:
        """Delete these committed runs of one partition, files included (an unknown id is
        ignored; a run not named is never touched, so a commit that landed meanwhile is kept);
        committed like ``purge_before`` (the published sequence moves on; a read pinned to an
        older one retries). Raises ``PartitionBusyError`` when a pending run has written to the
        partition (nothing is deleted: try again). -> runs deleted. An admin rewrite
        (``services/feedback/retention.py``), never part of a run."""
        ...

    def sweep_orphans(self, table: str, session_date: date) -> int:
        """Delete the data files of one partition that no run of its index names (what a crash
        between rewriting the index and deleting a file leaves); a pending run's files are never
        touched, nor a file younger than a minute (a direct write about to be indexed). Raises
        ``PartitionBusyError`` when a pending run has written to the partition. The caller must
        hold the table's writers lock (``storage.locks.FEEDBACK_WRITERS``).
        -> files deleted (a backend that keeps no loose files: 0)."""
        ...

    def compact_runs(
        self,
        table: str,
        session_date: date,
        dry_run: bool = False,
        verify: bool = False,
        budget_s: float | None = None,
    ) -> CompactionReport:
        """Replace one merge-table partition's runs by the fewest rows that read the same at every
        ``as_of`` and every pinned sequence (ADR 0078, ``backends/run_compaction.py``). A swap of
        the partition's index, not a commit: ``visible_seq``, ``partition_seq`` and ``dates`` do not
        move, and only a row's stamps can differ. A partition it cannot compact exactly is left
        untouched with ``skipped`` saying why; a result that fails its own verification raises
        ``CompactionVerificationError`` with nothing changed; ``PartitionBusyError`` when a pending
        run wrote to it. The superseded files stay for ``SWAP_GRACE_S`` (a read that resolved them
        finishes) and go with ``sweep_orphans``. ``dry_run``: the report only, from the plan alone
        unless ``verify`` (then the plan is also verified, in memory). ``budget_s`` bounds the
        partition's planning and verifying: over it nothing is swapped and the partition is
        skipped (``skipped`` "verification over budget"). Admin rewrite,
        never part of a run."""
        ...


class PartitionBusyError(RuntimeError):
    """A pending run is writing to the partition: ``purge_runs`` deleted nothing."""


class RawStore(Protocol):
    """Vendor responses exactly as received (ADR 0006), kept for a retention window."""

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None: ...

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None: ...

    def sources(self) -> list[str]:
        """Every source with stored responses, sorted."""
        ...

    def purge_before(self, cutoff: date, source: str | None = None) -> int:
        """Delete responses for sessions before ``cutoff`` (only ``source``'s when given).
        Returns the number of responses removed."""
        ...


class StagingStore(Protocol):
    """Per-item scratch space for resumable jobs; published to a TableStore at the end."""

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None: ...

    def keys(self, run_id: str, table: str) -> list[str]: ...

    def collect(self, run_id: str, table: str) -> pd.DataFrame | None: ...

    def exists(self, run_id: str) -> bool:
        """Whether the run still has scratch (dropped on commit, or purged by retention)."""
        ...

    def clear(self, run_id: str) -> None:
        """Drop one run's scratch (no-op when it has none)."""
        ...

    def purge_before(self, cutoff: date) -> int:
        """Drop scratch of runs whose session (from the run id) is before ``cutoff``.

        Finished runs drop their own scratch (``IngestRun``, when nothing is left to retry);
        this removes what unfinished runs left behind.
        Ids not made by ``new_run_id`` are kept. Returns the number of runs removed."""
        ...


class RunStore(Protocol):
    def save(self, record: RunRecord) -> None: ...

    def load(self, run_id: str) -> RunRecord | None: ...

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]: ...

    def find_many(self, jobs: Collection[str], first: date, last: date) -> list[RunRecord]:
        """The records of any of ``jobs`` for the sessions ``first..last``, by start time: one
        pass over the store, not one per job."""
        ...

    def generation(self) -> tuple[int, int]:
        """A token that changes whenever a record is saved and only then (a read never moves it):
        a cache over the run records is valid while it is equal. Read it before the records it
        guards (ADR 0022); it says nothing about which record changed."""
        ...


class Backend(Protocol):
    @property
    def tables(self) -> TableStore: ...

    @property
    def raw(self) -> RawStore: ...

    @property
    def staging(self) -> StagingStore: ...

    @property
    def runs(self) -> RunStore: ...

    def lock(self, name: str) -> Lock:
        """A named exclusive lock shared by everyone using this store (e.g. ``ingest``: one
        writing ingestion run at a time). Local: a file lock; memory: a thread lock."""
        ...
