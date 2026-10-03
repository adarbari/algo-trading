"""In-memory backend for tests and experiments. Same semantics as the local backend,
including the declared column types (``backends/arrow.py``).

One process only, so thread locks stand in for the local backend's file locks: one around
each partition's run index, and named locks for ``Backend.lock``.
"""

import threading
from collections.abc import Sequence
from datetime import date, datetime

import pandas as pd

from algotrade.storage.backends.arrow import concat, to_arrow, to_frame
from algotrade.storage.backends.run_selection import (
    RunEntry,
    concat_frames,
    merge_rows,
    run_mode,
    select_instruments,
    select_runs,
)
from algotrade.storage.locks import ThreadLock
from algotrade.storage.runs import RunRecord, run_session


class MemoryTables:
    def __init__(self) -> None:
        self._data: dict[tuple[str, date], dict[str, pd.DataFrame]] = {}
        self._restating: set[tuple[str, date, str]] = set()
        self._index_lock = threading.Lock()

    def write(
        self,
        table: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        restates: bool = False,
    ) -> None:
        copy = to_frame(to_arrow(table, frame))  # stored as the local backend would type it
        with self._index_lock:
            self._data.setdefault((table, session_date), {})[run_id] = copy
            if restates:
                self._restating.add((table, session_date, run_id))
            else:
                self._restating.discard((table, session_date, run_id))

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        stored = self._data.get((table, session_date), {})
        entries = {
            run: RunEntry(f["knowledge_ts"].max(), (table, session_date, run) in self._restating)
            for run, f in stored.items()
            if not f.empty
        }
        runs = select_runs(entries, as_of, run_mode(table))
        if not runs:
            return None
        if len(runs) == 1:
            return select_instruments(stored[runs[0]].copy(), instruments)
        parts = [to_arrow(table, select_instruments(stored[r], instruments)) for r in runs]
        return to_frame(merge_rows(table, concat(table, parts)))

    def read_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        days = [d for d in self.dates(table) if start <= d <= end]
        return concat_frames(
            [f for d in days if (f := self.read(table, d, as_of, instruments)) is not None]
        )

    def dates(self, table: str) -> list[date]:
        return sorted(d for (t, d) in self._data if t == table)

    def names(self) -> list[str]:
        return sorted({t for (t, _) in self._data})


class MemoryRaw:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str, date, str, str], bytes] = {}

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None:
        self._data[(source, dataset, session_date, run_id, key)] = payload

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None:
        return self._data.get((source, dataset, session_date, run_id, key))

    def purge_before(self, cutoff: date) -> int:
        old = [k for k in self._data if k[2] < cutoff]
        for k in old:
            del self._data[k]
        return len(old)


class MemoryStaging:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], dict[str, pd.DataFrame]] = {}

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None:
        self._data.setdefault((run_id, table), {})[key] = frame.copy()

    def keys(self, run_id: str, table: str) -> list[str]:
        return sorted(self._data.get((run_id, table), {}))

    def collect(self, run_id: str, table: str) -> pd.DataFrame | None:
        parts = [f for _, f in sorted(self._data.get((run_id, table), {}).items()) if not f.empty]
        return pd.concat(parts, ignore_index=True) if parts else None

    def clear(self, run_id: str) -> None:
        for k in [k for k in self._data if k[0] == run_id]:
            del self._data[k]

    def purge_before(self, cutoff: date) -> int:
        old = {r for r, _ in self._data if (s := run_session(r)) is not None and s < cutoff}
        for run_id in old:
            self.clear(run_id)
        return len(old)


class MemoryRuns:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def save(self, record: RunRecord) -> None:
        self._data[record.run_id] = record.to_json()

    def load(self, run_id: str) -> RunRecord | None:
        text = self._data.get(run_id)
        return RunRecord.from_json(text) if text else None

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        records = [RunRecord.from_json(t) for t in self._data.values()]
        hits = [r for r in records if r.job == job and session_date in (None, r.session_date)]
        return sorted(hits, key=lambda r: r.started_at)


class MemoryBackend:
    def __init__(self) -> None:
        self.tables = MemoryTables()
        self.raw = MemoryRaw()
        self.staging = MemoryStaging()
        self.runs = MemoryRuns()
        self._locks: dict[str, ThreadLock] = {}
        self._guard = threading.Lock()

    def lock(self, name: str) -> ThreadLock:
        """The same lock object for a name, for as long as this backend lives."""
        with self._guard:
            return self._locks.setdefault(name, ThreadLock())
