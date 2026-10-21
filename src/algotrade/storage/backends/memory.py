"""In-memory backend for tests and experiments. Same semantics as the local backend,
including the declared column types (``backends/arrow.py``).

One process only, so thread locks stand in for the local backend's file locks: one around
the run index (writes, commits and read snapshots), and named locks for ``Backend.lock``.
A commit (ADR 0022) happens under that lock, so it is atomic and never left half-applied.
"""

import secrets
import threading
from collections.abc import Collection, Sequence
from datetime import UTC, date, datetime

import pandas as pd
import pyarrow as pa

from algotrade.storage.backends.arrow import (
    concat,
    keep_columns,
    parquet_bytes,
    table_spec,
    to_arrow,
    to_frame,
)
from algotrade.storage.backends.local_index import safe
from algotrade.storage.backends.run_compaction import (
    OVER_BUDGET,
    Budget,
    CompactionOverBudgetError,
    kept_entries,
    plan_compaction,
    verify_plan,
)
from algotrade.storage.backends.run_selection import (
    RunEntry,
    committed,
    concat_frames,
    keep_newest_runs,
    max_seq,
    merge_rows,
    newest_run_per_group,
    pinned_read,
    run_mode,
    select_instruments,
    select_runs,
    visible_entries,
)
from algotrade.storage.locks import ThreadLock
from algotrade.storage.runs import RunRecord, run_session
from algotrade.storage.tables.interfaces import CompactionReport, PartitionBusyError
from algotrade.storage.tables.schemas import require_retention

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
        spec = table_spec(table)
        if spec is None or not spec.whole_per_group:
            raise ValueError(f"{table}: a run's file is not its group's whole result")

        def at(seq: int | None) -> pd.DataFrame | None:
            entries, frames = self._view((table, session_date), own_run, seq)
            runs = select_runs(entries, None, run_mode(table))
            if not runs:
                return None
            held = {
                run: None
                if entries[run].restates or any(g not in frames[run].columns for g in group)
                else set(
                    frames[run][list(group)].drop_duplicates().itertuples(index=False, name=None)
                )
                for run in runs
            }
            newest = newest_run_per_group(runs, held)
            if newest is None:  # the same fallback as the local backend: merge, then keep newest
                parts = [to_arrow(table, frames[r]) for r in runs]
                data = merge_rows(table, concat(table, parts)) if len(runs) > 1 else parts[0]
                merged = keep_newest_runs(to_frame(data), group, runs)
            else:
                chosen = set(newest.values())
                found = concat_frames([frames[r] for r in runs if r in chosen])
                merged = found if found is not None else frames[runs[0]].iloc[0:0]
            frame = select_instruments(merged, instruments)
            if columns is not None:
                keep = keep_columns([*columns, *group])
                frame = frame[[c for c in frame.columns if c in keep]]
            return frame.reset_index(drop=True)

        if upto is not None:
            return at(upto)
        return pinned_read(at, lambda: self._seq, lambda: self._index_lock)

    def read_run(
        self,
        table: str,
        session_date: date,
        run_id: str,
        own_run: str | None = None,
        columns: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        def at(upto: int) -> pd.DataFrame | None:
            _, frames = self._view((table, session_date), own_run, upto)
            frame = frames.get(run_id)
            if frame is None:
                return None
            mine = frame[frame["run_id"] == run_id] if "run_id" in frame.columns else frame.copy()
            if mine.empty:
                return None
            if columns is not None:
                keep = keep_columns(columns)
                mine = mine[[c for c in mine.columns if c in keep]]
            return mine.reset_index(drop=True)

        return pinned_read(at, lambda: self._seq, lambda: self._index_lock)

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

    def build_history(self, table: str, years: Sequence[int]) -> list[int]:
        """No history copy in memory (ADR 0060): reads are already one lookup per partition."""
        return []

    def history_size(self, table: str) -> int:
        return 0

    def history_current(self, table: str, day: date) -> bool:
        return True  # no copy to be stale

    def free_bytes(self) -> int:
        return 1 << 62  # memory: no volume to fill

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

    def purge_before(self, table: str, cutoff: date, keep: Collection[date] = ()) -> int:
        require_retention(table)
        spared = set(keep)
        with self._index_lock:
            busy = {k for writes in self._pending.values() for k in writes}
            keys = [
                k
                for k in self._partitions
                if k[0] == table and k[1] < cutoff and k not in busy and k[1] not in spared
            ]
            for key in keys:
                del self._partitions[key]
                for frame_key in [f for f in self._frames if f[0] == key]:
                    del self._frames[frame_key]
            if keys:
                self._seq += 1  # committed like a run: a read sees all of the purge or none
            return len(keys)

    def partition_runs(self, table: str, session_date: date) -> list[str]:
        with self._index_lock:
            entries = self._partitions.get((table, session_date), {})
            return sorted(entries, key=lambda r: (entries[r].seq or -1, r))

    def sweep_orphans(self, table: str, session_date: date) -> int:
        with self._index_lock:
            if any((table, session_date) in writes for writes in self._pending.values()):
                raise PartitionBusyError(f"{table} {session_date}")
        return 0  # frames live with their entries: nothing is ever loose

    def purge_runs(self, table: str, session_date: date, runs: Collection[str]) -> int:
        key = (table, session_date)
        with self._index_lock:
            if any(key in writes for writes in self._pending.values()):
                raise PartitionBusyError(f"{table} {session_date}")
            entries = self._partitions.get(key, {})
            gone = {r for r in runs if r in entries}
            for run in gone:
                del entries[run]
            for frame_key in [f for f in self._frames if f[0] == key and f[1] in gone]:
                del self._frames[frame_key]
            if gone:
                self._seq += 1  # committed like a run: a read sees all of the purge or none
            return len(gone)

    def compact_runs(
        self,
        table: str,
        session_date: date,
        dry_run: bool = False,
        verify: bool = False,
        budget_s: float | None = None,
    ) -> CompactionReport:
        """ADR 0078; a spent ``budget_s`` skips the partition, swapping nothing."""
        try:
            return self._compact_runs(table, session_date, dry_run, verify, Budget(budget_s))
        except CompactionOverBudgetError:
            return CompactionReport(skipped=OVER_BUDGET)

    def _compact_runs(
        self, table: str, session_date: date, dry_run: bool, verify: bool, budget: Budget
    ) -> CompactionReport:
        """ADR 0078, as ``LocalTables.compact_runs``; one lock hold makes it atomic, so there is
        no concurrent commit to abort for and no file to leave for a sweep."""
        key = (table, session_date)
        with self._index_lock:
            if any(key in writes for writes in self._pending.values()):
                raise PartitionBusyError(f"{table} {session_date}")
            expected = dict(self._partitions.get(key, {}))
            if not expected:
                return CompactionReport(skipped="no such partition")
            sources: dict[str, pa.Table] = {}

            def load(run: str, entry: RunEntry) -> pa.Table:
                sources[run] = to_arrow(table, self._frames[(key, run, entry.ref)])
                return sources[run]

            plan = plan_compaction(table, expected, load, budget)
            size = {r: len(parquet_bytes(sources[r])) for r in sources}
            before, size_before = len(expected), sum(size.values())
            if plan.skipped or plan.noop:
                return CompactionReport(before, before, size_before, size_before, 0, plan.skipped)
            fresh = {r: f"{expected[r].ref or ''}~{secrets.token_hex(4)}" for r in plan.rewritten}
            kept = kept_entries(expected, plan, fresh)
            size_after = sum(
                len(parquet_bytes(plan.kept[r])) if r in fresh else size[r] for r in kept
            )
            report = CompactionReport(before, len(kept), size_before, size_after, len(plan.dropped))
            if dry_run and not verify:
                return report
            verify_plan(table, expected, sources, kept, {r: plan.kept[r] for r in kept}, budget)
            if dry_run:
                return report
            frames = {
                (key, r, e.ref): self._frames[(key, r, expected[r].ref)] for r, e in kept.items()
            }
            for r in fresh:
                frames[(key, r, kept[r].ref)] = to_frame(plan.kept[r])
            for frame_key in [f for f in self._frames if f[0] == key]:
                del self._frames[frame_key]
            self._frames.update(frames)
            self._partitions[key] = kept
            return report

    def dates(self, table: str, own_run: str | None = None) -> list[date]:
        with self._index_lock:
            keys = set(self._partitions) | set(self._pending.get(own_run or "", {}))
        return sorted(d for (t, d) in keys if t == table)

    def partition_seq(self, table: str, start: date, end: date) -> dict[date, int]:
        with self._index_lock:
            return {
                d: max_seq(entries, self._seq)
                for (t, d), entries in self._partitions.items()
                if t == table and start <= d <= end
            }

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

    def exists(self, run_id: str) -> bool:
        return any(k[0] == run_id for k in self._data)

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
        self._saves = 0

    def generation(self) -> tuple[int, int]:
        return (0, self._saves)

    def save(self, record: RunRecord) -> None:
        self._data[record.run_id] = record.to_json()
        self._saves += 1

    def load(self, run_id: str) -> RunRecord | None:
        text = self._data.get(run_id)
        return RunRecord.from_json(text) if text else None

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        records = [RunRecord.from_json(t) for t in self._data.values()]
        hits = [r for r in records if r.job == job and session_date in (None, r.session_date)]
        return sorted(hits, key=lambda r: r.started_at)

    def find_many(self, jobs: Collection[str], first: date, last: date) -> list[RunRecord]:
        records = [RunRecord.from_json(t) for t in self._data.values()]
        hits = [r for r in records if r.job in jobs and first <= r.session_date <= last]
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
