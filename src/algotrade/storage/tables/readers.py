"""Generic read-only storage facade: tables, date ranges, partition dates and run records.

No domain rules live here (ADR 0019 R2): which snapshot to read, instruments, universes,
bars, adjustments, events and chains are ``algotrade.data``. Consumers get this class from
``algotrade.data`` and pass it to the functions there.
"""

from collections.abc import Collection, Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.core.model.errors import MissingDataError
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.interfaces import Backend


class StoreReader:
    """``own_run``: also see that run's pending writes (the run reading what it wrote before
    it commits, ADR 0022); ``None`` (the default) sees committed data only."""

    def __init__(self, backend: Backend, own_run: str | None = None) -> None:
        self._backend = backend
        self.own_run = own_run

    def including(self, run_id: str) -> "StoreReader":
        """This reader, also seeing ``run_id``'s pending writes."""
        return StoreReader(self._backend, run_id)

    def table(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        return self._backend.tables.read(table, session_date, as_of, instruments, self.own_run)

    def require(
        self, table: str, session_date: date, hint: str, as_of: datetime | None = None
    ) -> pd.DataFrame:
        """Like ``table`` but raises ``MissingDataError`` instead of returning ``None``."""
        frame = self.table(table, session_date, as_of)
        if frame is None:
            raise MissingDataError(table, f"no data for {session_date.isoformat()}", hint)
        return frame

    def table_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        """``columns``: only these (+ ``instrument_id`` and the point-in-time columns)."""
        tables = self._backend.tables
        return tables.read_range(table, start, end, as_of, instruments, self.own_run, columns)

    def visible_seq(self) -> int:
        """The latest committed publish sequence: changes exactly when a commit publishes."""
        return self._backend.tables.visible_seq()

    def runs_generation(self) -> tuple[int, int]:
        """Changes exactly when a run record (a job's too) is saved: the key of a cache over the
        run records, read before them like ``visible_seq`` (ADR 0022)."""
        return self._backend.runs.generation()

    def table_names(self) -> list[str]:
        return self._backend.tables.names(self.own_run)

    def dates(self, table: str) -> list[date]:
        return self._backend.tables.dates(table, self.own_run)

    def latest_date(self, table: str, on_or_before: date | None = None) -> date | None:
        """The last partition date (on or before a date). Picking the snapshot a reader
        should see is ``algotrade.data.reference.snapshot``, not this."""
        dates = [d for d in self.dates(table) if on_or_before is None or d <= on_or_before]
        return dates[-1] if dates else None

    def runs(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        return self._backend.runs.find(job, session_date)

    def runs_of(self, jobs: Collection[str], first: date, last: date) -> list[RunRecord]:
        """The records of any of ``jobs`` for the sessions ``first..last`` in one pass."""
        return self._backend.runs.find_many(jobs, first, last)

    def run(self, run_id: str) -> RunRecord | None:
        """One run record by id (``None`` when there is none)."""
        return self._backend.runs.load(run_id)
