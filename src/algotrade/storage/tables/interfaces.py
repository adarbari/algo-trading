"""Storage protocols. Every backend implements all of them and passes tests/contract/storage."""

from collections.abc import Sequence
from datetime import date, datetime
from typing import Protocol

import pandas as pd

from algotrade.storage.locks import Lock
from algotrade.storage.runs import RunRecord


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
