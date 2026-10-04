"""In-memory backend for tests and experiments. Same semantics as the local backend,
including the declared column types (``backends/arrow.py``).

One process only, so thread locks stand in for the local backend's file locks: one around
the run index (writes, commits and read snapshots), and named locks for ``Backend.lock``.
A commit (ADR 0022) happens under that lock, so it is atomic and never left half-applied.
"""

import threading
from collections.abc import Sequence
from datetime import UTC, date, datetime

import pandas as pd

from algotrade.storage.backends.arrow import (
    concat,
    keep_columns,
    parquet_bytes,
    to_arrow,
    to_frame,
)
from algotrade.storage.backends.local_index import safe
from algotrade.storage.backends.run_selection import (
    RunEntry,
    committed,
    concat_frames,
    merge_rows,
    pinned_read,
    run_mode,
    select_instruments,
    select_runs,
    visible_entries,
)
from algotrade.storage.locks import ThreadLock
from algotrade.storage.runs import RunRecord, run_session

Key = tuple[str, date]  # (table, session_date)
_PENDING = "pending"


class MemoryTables:
    """Committed runs per partition (entries + frames by version), and each run's pending
    writes until it commits. One lock makes every write, commit and read snapshot atomic."""

    def __init__(self) -> None:
        self._partitions: dict[Key, dict[str, RunEntry]] = {}
        self._frames: dict[tuple[Key, str, str | None], pd.DataFrame] = {}
        self._pending: dict[str, dict[Key, tuple[pd.DataFrame, bool]]] = {}
        self._touched: dict[str, datetime] = {}  # a pending run's last write (retention)
        self._seq = 0
        self._index_lock = threading.RLock()  # re-entered by a read that waits out commits

    def write(
        self,
        table: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        restates: bool = False,
        pending: bool = False,
    ) -> None:
        copy = to_frame(to_arrow(table, frame))  # stored as the local backend would type it
        key = (table, session_date)
        with self._index_lock:
            if pending:
                self._pending.setdefault(run_id, {})[key] = (copy, restates)
                self._touched[run_id] = datetime.now(UTC)
                return
            entries = self._partitions.setdefault(key, {})
            if not copy.empty:
                entries[run_id] = RunEntry(copy["knowledge_ts"].max(), restates)
                self._frames[(key, run_id, None)] = copy

    def commit_run(self, run_id: str, at: datetime) -> int:
        with self._index_lock:
            writes = self._pending.pop(run_id, {})
            self._touched.pop(run_id, None)
            if not writes:
                return 0
            self._seq += 1
            ref = str(self._seq)
            for key, (frame, restates) in writes.items():
                entries = self._partitions.setdefault(key, {})
                if frame.empty:
                    continue
                known = frame["knowledge_ts"].max()
                entries[run_id] = committed(
                    known, restates, at, self._seq, ref, entries.get(run_id)
                )
                self._frames[(key, run_id, ref)] = frame
            return len(writes)

    def visible_seq(self) -> int:
        with self._index_lock:
            return self._seq

    def abort_run(self, run_id: str) -> int:
        with self._index_lock:
            self._touched.pop(run_id, None)
            return len(self._pending.pop(run_id, {}))

    def pending_runs(self) -> list[str]:
        with self._index_lock:
            return sorted(self._pending)

    def recover_runs(self) -> list[str]:
        """Commits are atomic here, so none is ever left half-applied."""
        return []

    def purge_pending_before(self, cutoff: datetime) -> int:
        with self._index_lock:
            old = [r for r, at in self._touched.items() if at < cutoff]
        for run_id in old:
            self.abort_run(run_id)
        return len(old)

    def _view(
        self, key: Key, own_run: str | None, upto: int | None
    ) -> tuple[dict[str, RunEntry], dict[str, pd.DataFrame]]:
        with self._index_lock:
            entries = visible_entries(self._partitions.get(key, {}), upto)
            frames = {run: self._frames[(key, run, e.ref)] for run, e in entries.items()}
            own = self._pending.get(own_run, {}).get(key) if own_run else None
        if own is not None and not own[0].empty:
            entries[own_run] = RunEntry(own[0]["knowledge_ts"].max(), own[1], ref=_PENDING)  # type: ignore[index]
            frames[own_run] = own[0]  # type: ignore[index]
        return entries, frames

    def _read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None,
        instruments: Sequence[str] | None,
        own_run: str | None,
        upto: int | None,
    ) -> pd.DataFrame | None:
        entries, frames = self._view((table, session_date), own_run, upto)
        runs = select_runs(entries, as_of, run_mode(table))
        if not runs:
            return None
        if len(runs) == 1:
            return select_instruments(frames[runs[0]].copy(), instruments)
        parts = [to_arrow(table, select_instruments(frames[r], instruments)) for r in runs]
        return to_frame(merge_rows(table, concat(table, parts)))

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        own_run: str | None = None,
    ) -> pd.DataFrame | None:
        return pinned_read(
            lambda upto: self._read(table, session_date, as_of, instruments, own_run, upto),
            lambda: self._seq,
            lambda: self._index_lock,
        )

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
        def at(upto: int) -> list[pd.DataFrame]:  # one commit sequence for the whole range
            days = [d for d in self.dates(table, own_run) if start <= d <= end]
            return [
                f
                for d in days
                if (f := self._read(table, d, as_of, instruments, own_run, upto)) is not None
            ]

        frames = pinned_read(at, lambda: self._seq, lambda: self._index_lock)
        if columns is not None:
            frames = [f[[c for c in f.columns if c in keep_columns(columns)]] for f in frames]
        return concat_frames(frames)

    def size(self, table: str) -> int:
        with self._index_lock:
            frames = [f for (key, _, _), f in self._frames.items() if key[0] == table]
        return sum(len(parquet_bytes(to_arrow(table, f))) for f in frames)

    def drop(self, table: str) -> int:
        with self._index_lock:
            keys = [k for k in self._partitions if k[0] == table]
            for key in keys:
                del self._partitions[key]
            for frame_key in [k for k in self._frames if k[0][0] == table]:
                del self._frames[frame_key]
            return len(keys)

    def purge_before(self, table: str, cutoff: date) -> int:
        with self._index_lock:
            keys = [k for k in self._partitions if k[0] == table and k[1] < cutoff]
            for key in keys:
                del self._partitions[key]
            for frame_key in [k for k in self._frames if k[0][0] == table and k[0][1] < cutoff]:
                del self._frames[frame_key]
            return len(keys)

    def dates(self, table: str, own_run: str | None = None) -> list[date]:
        with self._index_lock:
            keys = set(self._partitions) | set(self._pending.get(own_run or "", {}))
        return sorted(d for (t, d) in keys if t == table)

    def names(self, own_run: str | None = None) -> list[str]:
        with self._index_lock:
            keys = set(self._partitions) | set(self._pending.get(own_run or "", {}))
        return sorted({t for (t, _) in keys})


class MemoryRaw:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str, date, str, str], bytes] = {}

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None:
        self._data[(source, dataset, session_date, run_id, safe(key))] = payload

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None:
        return self._data.get((source, dataset, session_date, run_id, key))

    def sources(self) -> list[str]:
        return sorted({k[0] for k in self._data})

    def purge_before(self, cutoff: date, source: str | None = None) -> int:
        old = [k for k in self._data if k[2] < cutoff and source in (None, k[0])]
        for k in old:
            del self._data[k]
        return len(old)


class MemoryStaging:
    def __init__(self) -> None:
        self._data: dict[tuple[str, str], dict[str, pd.DataFrame]] = {}

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None:
        self._data.setdefault((run_id, table), {})[safe(key)] = frame.copy()

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
