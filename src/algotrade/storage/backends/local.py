"""Local filesystem backend: Parquet tables, gzip raw responses, JSON run records.

Layout under the root directory (an internal detail; nothing else may rely on it)::

    tables/<table>/date=YYYY-MM-DD/run=<run_id>.parquet   (+ _runs.json knowledge index:
                                                           run -> knowledge_ts, or a dict
                                                           with restates / visible_at /
                                                           seq / file / prev; .runs.lock
                                                           guarding it; a resumed run's
                                                           new version: run=<id>~<hex>)
                                                          typed per storage/tables/schemas.py,
                                                          ~64k-row groups + page index
    tables/<table>/_history/                              the derived history copy (history.py,
                                                          ADR 0060): a year per file + manifest
    tables/_txn/pending/<run_id>.jsonl                    a run's writes not yet committed
    tables/_txn/commits/<run_id>.json, seq, commit.lock   commits (local_index.py, ADR 0022)
    raw/source=<s>/dataset=<d>/date=YYYY-MM-DD/run=<run_id>/<key>.json.gz
    staging/<run_id>/<table>/<key>.parquet
    runs/<run_id>.json
    locks/<name>.lock                                      (Backend.lock, e.g. the ingest run)

Every file is written to a unique temp file in its directory and renamed into place, so
concurrent writers never share a temp file and readers never see half a file. The
``_runs.json`` read-modify-write is serialised by a file lock, so two runs writing the same
partition at once (threads or processes) are both indexed. A ``pending`` write is indexed
only when its run commits, in every partition at once (``local_index.py``).
"""

import glob
import gzip
import os
import shutil
import threading
from collections import OrderedDict
from collections.abc import Collection, Sequence
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import (
    concat,
    keep_columns,
    parquet_bytes,
    to_arrow,
    to_frame,
)
from algotrade.storage.backends.history import HistoryCopy
from algotrade.storage.backends.local_index import (
    INDEX,
    TXN,
    Commits,
    atomic_write,
    default_file,
    drop_unreferenced,
    index_lock,
    read_index,
    run_file,
    safe,
    write_index,
)
from algotrade.storage.backends.run_selection import (
    RunEntry,
    StaleSnapshotError,
    merge_rows,
    pinned_read,
    run_mode,
    select_instruments,
    select_runs,
    visible_entries,
)
from algotrade.storage.locks import FileLock, held
from algotrade.storage.runs import RunRecord, run_session
from algotrade.storage.tables.schemas import require_retention


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_parquet(index=False, engine="pyarrow", compression="zstd")


def _stored_tables(root: Path) -> list[str]:
    """Table paths (relative, posix) with an indexed partition, found by walking directories
    only: a directory is a table when one of its ``date=*`` children holds an index, which
    ends its scan (so the cost is the number of table directories, not of partitions or
    files; was ``root.glob("**/date=*/_runs.json")``: 20 s on 54,000 partitions). A directory
    with no indexed partition is searched below, apart from ``_txn`` at the root."""
    found: list[str] = []
    pending = [root]
    while pending:
        directory = pending.pop()
        below: list[str] = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if not entry.is_dir():
                    continue
                if entry.name.startswith("date="):
                    if (Path(entry.path) / INDEX).exists():
                        found.append(directory.relative_to(root).as_posix())
                        below = []
                        break
                elif not (directory == root and entry.name == TXN):
                    below.append(entry.path)
        pending.extend(Path(p) for p in below)
    return found


class LocalTables:
    def __init__(self, root: Path) -> None:
        self.root = root / "tables"
        self.commits = Commits(self.root)
        self.history = HistoryCopy(self.root, self.commits.published, self.commits.no_commits)

    def _dir(self, table: str, session_date: date) -> Path:
        return self.root / table / f"date={session_date.isoformat()}"

    def write(
        self,
        table: str,
        session_date: date,
        run_id: str,
        frame: pd.DataFrame,
        restates: bool = False,
        pending: bool = False,
    ) -> None:
        directory = self._dir(table, session_date)
        data = parquet_bytes(to_arrow(table, frame))
        known = None if frame.empty else pd.Timestamp(frame["knowledge_ts"].max()).isoformat()
        if pending:
            file = self.commits.stage(table, session_date, safe(run_id), known, restates)
            if file is not None:
                atomic_write(directory / file, data)
            return
        if known is not None:
            atomic_write(directory / default_file(safe(run_id)), data)
        with held(index_lock(directory)):
            index = read_index(directory)
            if known is not None:
                index[run_id] = RunEntry(pd.Timestamp(known), restates)
            write_index(directory, index)
        drop_unreferenced(directory, run_id)

    def commit_run(self, run_id: str, at: datetime) -> int:
        return self.commits.commit_run(run_id, at)

    def visible_seq(self) -> int:
        return self.commits.published()

    def abort_run(self, run_id: str) -> int:
        return self.commits.abort_run(run_id)

    def pending_runs(self) -> list[str]:
        return self.commits.pending_runs()

    def recover_runs(self) -> list[str]:
        return self.commits.recover()

    def purge_pending_before(self, cutoff: datetime) -> int:
        return self.commits.purge_pending_before(cutoff)

    def _own(self, table: str, session_date: date, own_run: str | None) -> RunEntry | None:
        """The entry of ``own_run``'s pending write to the partition, if it wrote rows."""
        if own_run is None:
            return None
        item = self.commits.pending_item(own_run, table, session_date)
        if item is None or item["knowledge_ts"] is None:
            return None
        known = pd.Timestamp(item["knowledge_ts"])
        return RunEntry(known, bool(item["restates"]), ref=item["file"])

    def _partition(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None,
        instruments: Sequence[str] | None,
        own_run: str | None,
        upto: int,
        columns: Sequence[str] | None = None,
    ) -> pa.Table | None:
        """The partition as a read at ``as_of`` sees it (``run_selection``), conformed.
        ``upto``: the commit sequence the read captured before opening any index.
        ``columns``: only those (and the key / point-in-time columns) are decoded."""
        directory = self._dir(table, session_date)
        entries = visible_entries(read_index(directory), upto)
        own = self._own(table, session_date, own_run)
        if own_run is not None and own is not None:
            entries[own_run] = own
        runs = select_runs(entries, as_of, run_mode(table))
        if not runs:
            return None
        try:
            parts = [
                _read_file(directory / run_file(run, entries[run]), instruments, columns)
                for run in runs
            ]
        except FileNotFoundError as gone:  # a commit replaced the version and removed its file
            raise StaleSnapshotError(f"{directory}: {gone.filename}") from gone
        data = concat(table, parts)
        return merge_rows(table, data) if len(runs) > 1 else data

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
        own_run: str | None = None,
    ) -> pd.DataFrame | None:
        data = pinned_read(
            lambda upto: self._partition(table, session_date, as_of, instruments, own_run, upto),
            self.commits.published,
            self.commits.no_commits,
        )
        return None if data is None else select_instruments(to_frame(data), instruments)

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
        def at(upto: int) -> list[pa.Table]:  # one commit sequence for the whole range
            by_year: dict[int, pa.Table] = {}
            if as_of is None and own_run is None:  # what the history copy holds (ADR 0060)
                for year, copy in self.history.usable(
                    table, start, end, instruments is not None, upto
                ).items():
                    low, high = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
                    rows = self.history.read_year(
                        table, year, copy, low, high, instruments, columns
                    )
                    if rows is not None:
                        by_year[year] = rows
            parts: dict[int, list[pa.Table]] = {y: [t] for y, t in by_year.items() if t.num_rows}
            if any(y not in by_year for y in range(start.year, end.year + 1)):
                for d in self.dates(table, own_run):
                    if start <= d <= end and d.year not in by_year:
                        data = self._partition(table, d, as_of, instruments, own_run, upto, columns)
                        if data is not None:
                            parts.setdefault(d.year, []).append(data)
            return [t for year in sorted(parts) for t in parts[year]]

        parts = pinned_read(at, self.commits.published, self.commits.no_commits)
        if not parts:
            return None
        frame = to_frame(concat(table, parts))
        return None if frame.empty else frame.reset_index(drop=True)

    def build_history(self, table: str, years: Sequence[int]) -> list[int]:
        """Make the table's history copy hold ``years`` and be current (``history.py``); -> the
        years built. Written only by ingestion (ADR 0005)."""

        def resolved(day: date, upto: int) -> pa.Table | None:
            return self._partition(table, day, None, None, None, upto)

        return self.history.build(table, years, self.dates(table), resolved)

    def history_size(self, table: str) -> int:
        """Bytes of the table's history copy (``history.py``)."""
        return self.history.size(table)

    def free_bytes(self) -> int:
        """Bytes free on the volume the store is on (a build checks it before writing)."""
        return self.history.free_bytes()

    def _own_partitions(self, own_run: str | None) -> set[tuple[str, date]]:
        if own_run is None:
            return set()
        items = self.commits.journal(own_run).values()
        return {(i["table"], date.fromisoformat(i["date"])) for i in items}

    def dates(self, table: str, own_run: str | None = None) -> list[date]:
        base = self.root / table
        found = {d for t, d in self._own_partitions(own_run) if t == table}
        if base.exists():
            found |= {
                date.fromisoformat(p.name.removeprefix("date="))
                for p in base.iterdir()
                if p.name.startswith("date=") and (p / INDEX).exists()
            }
        return sorted(found)

    def names(self, own_run: str | None = None) -> list[str]:
        found = {t for t, _ in self._own_partitions(own_run)}
        if self.root.exists():
            found |= set(_stored_tables(self.root))
        return sorted(found)

    @staticmethod
    def _index(directory: Path) -> dict[str, RunEntry]:
        return read_index(directory)

    def size(self, table: str) -> int:
        base = self.root / table
        return sum(p.stat().st_size for p in base.rglob("*") if p.is_file()) if base.exists() else 0

    def drop(self, table: str) -> int:
        base = self.root / table
        days = sorted(base.glob("date=*")) if base.exists() else []
        self._remove(days)
        shutil.rmtree(base, ignore_errors=True)
        return len(days)

    def purge_before(self, table: str, cutoff: date) -> int:
        """Retention (``require_retention``), committed like a run (``Commits.purge``)."""
        require_retention(table)
        base = self.root / table
        days = [
            d
            for d in (sorted(base.glob("date=*")) if base.exists() else [])
            if date.fromisoformat(d.name.removeprefix("date=")) < cutoff
        ]
        return self.commits.purge(days)

    @staticmethod
    def _remove(days: list[Path]) -> None:
        for day in days:
            with held(index_lock(day)):  # no write or commit is mid-way in the partition
                (day / INDEX).unlink(missing_ok=True)  # unindexed first: readers see nothing
            shutil.rmtree(day)


def _read_file(
    path: Path, instruments: Sequence[str] | None, columns: Sequence[str] | None
) -> pa.Table:
    """One version file (``columns``: only those and ``keep_columns``), its rows of
    ``instruments`` in file order. ``ParquetFile`` + an Arrow filter, not ``read_table``: a
    third of the cost on a small file (no dataset discovery), the same columns and types. The
    value set takes the id column's type: an empty ``instruments`` selects no rows (as the
    memory backend does) instead of raising on a null-typed set."""
    with pq.ParquetFile(path) as parquet:
        keep = None if columns is None else keep_columns(columns)
        present = None if keep is None else [c for c in parquet.schema_arrow.names if c in keep]
        data = parquet.read(columns=present)
    if instruments is None:
        return data
    ids = data.column("instrument_id")
    return data.filter(pc.is_in(ids, value_set=pa.array(list(instruments), type=ids.type)))


class LocalRaw:
    def __init__(self, root: Path) -> None:
        self.root = root / "raw"

    def _path(self, source: str, dataset: str, session_date: date, run_id: str, key: str) -> Path:
        return (
            self.root
            / f"source={source}"
            / f"dataset={dataset}"
            / f"date={session_date.isoformat()}"
            / f"run={safe(run_id)}"
            / f"{safe(key)}.json.gz"
        )

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None:
        path = self._path(source, dataset, session_date, run_id, key)
        atomic_write(path, gzip.compress(payload, mtime=0))

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None:
        path = self._path(source, dataset, session_date, run_id, key)
        return gzip.decompress(path.read_bytes()) if path.exists() else None

    def sources(self) -> list[str]:
        found = self.root.glob("source=*") if self.root.exists() else []
        return sorted(d.name.removeprefix("source=") for d in found if d.is_dir())

    def purge_before(self, cutoff: date, source: str | None = None) -> int:
        removed = 0
        pattern = f"source={safe(source)}" if source is not None else "source=*"
        for day in self.root.glob(f"{pattern}/dataset=*/date=*"):
            if date.fromisoformat(day.name.removeprefix("date=")) < cutoff:
                removed += sum(1 for _ in day.rglob("*.json.gz"))
                shutil.rmtree(day)
        return removed


class LocalStaging:
    def __init__(self, root: Path) -> None:
        self.root = root / "staging"

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None:
        atomic_write(
            self.root / safe(run_id) / table / f"{safe(key)}.parquet", _parquet_bytes(frame)
        )

    def keys(self, run_id: str, table: str) -> list[str]:
        directory = self.root / run_id / table
        return sorted(p.stem for p in directory.glob("*.parquet")) if directory.exists() else []

    def collect(self, run_id: str, table: str) -> pd.DataFrame | None:
        directory = self.root / run_id / table
        parts = [pd.read_parquet(directory / f"{k}.parquet") for k in self.keys(run_id, table)]
        parts = [p for p in parts if not p.empty]
        return pd.concat(parts, ignore_index=True) if parts else None

    def exists(self, run_id: str) -> bool:
        return (self.root / safe(run_id)).is_dir()

    def clear(self, run_id: str) -> None:
        shutil.rmtree(self.root / safe(run_id), ignore_errors=True)

    def purge_before(self, cutoff: date) -> int:
        old = [
            d
            for d in (self.root.iterdir() if self.root.exists() else [])
            if d.is_dir() and (s := run_session(d.name)) is not None and s < cutoff
        ]
        for directory in old:
            shutil.rmtree(directory, ignore_errors=True)
        return len(old)


MAX_PARSED_BYTES = 64 * 1024 * 1024  # the run files ``LocalRuns`` keeps parsed, by file size


class LocalRuns:
    def __init__(self, root: Path) -> None:
        self.root = root / "runs"
        # file name -> (its stat when parsed, the record): a record is parsed again only once
        # its file changed (``save`` replaces the file); never handed out, only copies of it
        # (an LRU bounded by the files' sizes: ``MAX_PARSED_BYTES``)
        self._parsed: OrderedDict[str, tuple[tuple[int, int, int], RunRecord]] = OrderedDict()
        self._parsed_bytes = 0
        self._parsed_lock = threading.Lock()
        # the directory's file stems with their session (``run_session``), listed again only once
        # ``generation`` changes: ``find`` ran once per edge and owner, each over ~10 000 files
        self._listing: tuple[tuple[int, int], list[tuple[str, date | None]]] | None = None

    def _stems(self) -> list[tuple[str, date | None]]:
        """``(stem, run_session(stem))`` of every ``.json`` file; the stamp is read before the
        listing, so a save during it leaves a stale stamp and the next call lists again."""
        stamp = self.generation()
        with self._parsed_lock:
            held = self._listing
        if held is not None and held[0] == stamp:
            return held[1]
        stems = [
            (stem, run_session(stem))
            for path in self.root.iterdir()
            if path.suffix == ".json" and (stem := path.stem)
        ]
        with self._parsed_lock:
            self._listing = (stamp, stems)
        return stems

    def _record(self, name: str) -> RunRecord | None:
        """The record in file ``name``, parsed once per version of the file; a copy (its
        ``items`` and ``stats`` too), so a caller that changes it changes no other's. ``None``
        when the file is gone (a concurrent cleanup)."""
        path = self.root / name
        try:
            st = path.stat()
            stamp = (st.st_ino, st.st_mtime_ns, st.st_size)
            with self._parsed_lock:
                held = self._parsed.get(name)
                if held is not None and held[0] == stamp:
                    self._parsed.move_to_end(name)
            if held is None or held[0] != stamp:
                held = (stamp, RunRecord.from_json(path.read_text()))
                self._remember(name, held, st.st_size)
        except FileNotFoundError:
            return None
        record = held[1]
        return replace(record, items=dict(record.items), stats=dict(record.stats))

    def _remember(self, name: str, held: tuple[tuple[int, int, int], RunRecord], size: int) -> None:
        """Keep ``held`` as the most recent entry; evict the least recent past the byte bound."""
        with self._parsed_lock:
            old = self._parsed.pop(name, None)
            if old is not None:
                self._parsed_bytes -= old[0][2]
            self._parsed[name] = held
            self._parsed_bytes += size
            while self._parsed_bytes > MAX_PARSED_BYTES and len(self._parsed) > 1:
                _, (evicted, _record) = self._parsed.popitem(last=False)
                self._parsed_bytes -= evicted[2]

    def generation(self) -> tuple[int, int]:
        """``(inode, mtime_ns)`` of the runs directory: ``save`` is an atomic rename into it,
        which changes the directory's mtime (checked on APFS: 2000 of 2000 saves); a read, a
        stat of a file or a parse does not. ``(0, 0)`` while the directory does not exist."""
        try:
            st = self.root.stat()
        except FileNotFoundError:
            return (0, 0)
        return (st.st_ino, st.st_mtime_ns)

    def save(self, record: RunRecord) -> None:
        atomic_write(self.root / f"{safe(record.run_id)}.json", record.to_json().encode())

    def load(self, run_id: str) -> RunRecord | None:
        path = self.root / f"{safe(run_id)}.json"
        return RunRecord.from_json(path.read_text()) if path.exists() else None

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        if not self.root.exists():
            return []
        # a ``new_run_id`` file names its job and session: only the job's own (of the session
        # asked for) are opened; a file in any other form (a services/jobs id) is opened too
        # (parsing every record took 0.9 s a call over 6 400 files: the edges page made 26)
        prefix = f"{safe(job)}-"
        names = [
            f"{stem}.json"
            for stem, day in self._stems()
            if day is None or (stem.startswith(prefix) and session_date in (None, day))
        ]
        records = [r for name in names if (r := self._record(name)) is not None]
        hits = [r for r in records if r.job == job and session_date in (None, r.session_date)]
        return sorted(hits, key=lambda r: r.started_at)

    def find_many(self, jobs: Collection[str], first: date, last: date) -> list[RunRecord]:
        if not self.root.exists():
            return []
        # run ids are ``{job}-{session}-{time}`` (new_run_id): only a job's own files are
        # opened, and of those only the sessions asked for (a record of another job, an edge
        # evaluation's runs are large, is never read)
        # a job whose name is a prefix of another's matches the other's files too: each file
        # is read once, and a record counts only for the job it names
        paths = {
            path
            for job in jobs
            for path in self.root.glob(f"{glob.escape(safe(job))}-*.json")
            if (day := run_session(path.stem)) is not None and first <= day <= last
        }
        records = [r for path in sorted(paths) if (r := self._record(path.name)) is not None]
        hits = [r for r in records if r.job in jobs]
        return sorted(hits, key=lambda r: r.started_at)


class LocalBackend:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.tables = LocalTables(root)
        self.raw = LocalRaw(root)
        self.staging = LocalStaging(root)
        self.runs = LocalRuns(root)

    def lock(self, name: str) -> FileLock:
        """A lock shared by every process using this data root (``locks/<name>.lock``)."""
        return FileLock(self.root / "locks" / f"{safe(name)}.lock")
