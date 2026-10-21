"""Local backend: each partition's run index (``_runs.json``) and atomic run commits (ADR 0022).

A run writing ``pending`` puts its Parquet files in place but records them only in its own
journal (``tables/_txn/pending/<run>.jsonl``); no partition index names them, so no read
sees them. ``commit_run`` makes every partition the run wrote visible at once:

1. under the store's commit lock, the journal becomes a commit marker
   (``_txn/commits/<run>.json``, written atomically) with the next commit sequence number.
   This is the decision point: from here the commit is completed, never undone;
2. each partition's index gets the run's entry (``seq``, ``visible_at``; the version it
   replaces is kept as ``prev``, older ones are dropped and flagged, see
   ``run_selection.pinned_read``), under that partition's index lock;
3. ``_txn/seq`` is set to the sequence number: the visibility point. A read captures
   ``seq`` before it opens any index and ignores entries above it, so it sees all of a
   commit or none of it (``run_selection.visible_entries``);
4. the marker, and files of the run no index entry refers to any more, are removed.

A crash after 1 leaves the marker: ``recover`` (and every later commit or abort, first)
re-applies it, which is idempotent. A crash before 1 leaves only the journal and files no
index refers to: ``abort_run`` deletes them (the ingestion startup recovery, or retention).

Pins (ADR 0077): ``pin(name, seq)`` records, under the commit lock, a sequence whose versions
must stay readable (``tables/_txn/pins/<name>.json``). Every commit reads the pins under the
same lock and keeps, per pin, the version it sees (``run_selection.retained``), so a pinned read
survives any number of recommits. Nothing guards against ``purge``, ``remove_runs`` or ``drop``:
each bumps ``destructive_epoch`` (``_txn/epoch``) instead, and a release built at another epoch
is not trusted.

Every file is written to a unique temp file in its directory and renamed into place.
"""

import contextlib
import json
import os
import secrets
import shutil
import tempfile
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.storage.backends.run_selection import RunEntry, chain, committed
from algotrade.storage.locks import FileLock, held
from algotrade.storage.tables.interfaces import PartitionBusyError

INDEX = "_runs.json"
INDEX_LOCK = ".runs.lock"
TXN = "_txn"
PINS = "pins"  # tables/_txn/pins/<name>.json: {"seq": N}, one per retained serving release
EPOCH = "epoch"  # tables/_txn/epoch: the count of destructive operations (see ``Commits``)
ORPHAN_GRACE_S = 60.0  # a loose file younger than this may be a write about to be indexed
SWAP_GRACE_S = 30.0  # a file a compaction swap superseded is swept no sooner than this (ADR 0078)


def atomic_write(path: Path, data: bytes) -> None:
    """Write via a unique temp file in the same directory, then rename into place."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        Path(name).replace(path)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise


def safe(key: str) -> str:
    if not key or "/" in key or key.startswith("."):
        raise ValueError(f"invalid storage key {key!r}")
    return key


def default_file(run_id: str) -> str:
    return f"run={run_id}.parquet"


def run_file(run_id: str, entry: RunEntry) -> str:
    """The file holding the rows of ``entry`` (a version of ``run_id``)."""
    return entry.ref or default_file(run_id)


# ----------------------------------------------------------------------------- the index


def _entry(value: str | dict[str, Any]) -> RunEntry:
    """An index value: ``knowledge_ts`` (a plain run) or a dict with ``knowledge_ts`` and
    optional ``restates``, ``visible_at``, ``seq``, ``file``, ``prev``, ``dropped`` and ``gap``."""
    if isinstance(value, str):
        return RunEntry(pd.Timestamp(value))
    visible = value.get("visible_at")
    return RunEntry(
        pd.Timestamp(str(value["knowledge_ts"])),
        bool(value.get("restates")),
        pd.Timestamp(str(visible)) if visible else None,
        int(value["seq"]) if value.get("seq") is not None else None,
        value.get("file"),
        _entry(value["prev"]) if value.get("prev") else None,
        bool(value.get("dropped")),
        int(value["gap"]) if value.get("gap") is not None else None,
    )


def _value(entry: RunEntry) -> str | dict[str, Any]:
    """The index value for ``entry``; a plain run keeps the original format."""
    out: dict[str, Any] = {"knowledge_ts": entry.knowledge_ts.isoformat()}
    if entry.restates:
        out["restates"] = True
    if entry.visible_at is not None:
        out["visible_at"] = entry.visible_at.isoformat()
    if entry.seq is not None:
        out["seq"] = entry.seq
    if entry.ref is not None:
        out["file"] = entry.ref
    if entry.prev is not None:
        out["prev"] = _value(entry.prev)
    if entry.dropped:
        out["dropped"] = True
    if entry.gap is not None:
        out["gap"] = entry.gap
    return out["knowledge_ts"] if len(out) == 1 else out


def read_index(directory: Path) -> dict[str, RunEntry]:
    path = directory / INDEX
    if not path.exists():
        return {}
    loaded: dict[str, str | dict[str, Any]] = json.loads(path.read_text())
    return {run: _entry(value) for run, value in loaded.items()}


def write_index(directory: Path, entries: dict[str, RunEntry]) -> None:
    data = {run: _value(entry) for run, entry in entries.items()}
    atomic_write(directory / INDEX, json.dumps(data, indent=2, sort_keys=True).encode())


def index_lock(directory: Path) -> FileLock:
    """Serialises read-modify-write of one partition's index (threads and processes)."""
    return FileLock(directory / INDEX_LOCK)


# ----------------------------------------------------------------------------- commits


class Commits:
    """Pending journals, commit markers and the published commit sequence of one store."""

    def __init__(self, tables_root: Path) -> None:
        self.tables = tables_root
        self.base = tables_root / TXN
        self._journals: dict[str, dict[str, dict[str, Any]]] = {}  # this process's runs
        # other processes' journals: (size, mtime_ns) of the file read -> its parsed lines
        self._foreign: dict[str, tuple[tuple[int, int], dict[str, dict[str, Any]]]] = {}
        self._guard = threading.Lock()

    def _dir(self, table: str, day: str) -> Path:
        return self.tables / table / f"date={day}"

    def _journal_path(self, run_id: str) -> Path:
        return self.base / "pending" / f"{safe(run_id)}.jsonl"

    def _marker_path(self, run_id: str) -> Path:
        return self.base / "commits" / f"{safe(run_id)}.json"

    def _commit_lock(self) -> FileLock:
        return FileLock(self.base / "commit.lock")

    @contextmanager
    def no_commits(self) -> Iterator[None]:
        """Hold the commit lock: no commit, abort or recovery runs (and so nothing a read
        pinned is replaced) until the block ends."""
        with held(self._commit_lock()):
            yield

    def published(self) -> int:
        """The highest commit sequence number whose entries every index already holds."""
        try:
            return int((self.base / "seq").read_text())
        except FileNotFoundError:
            return 0

    # ------------------------------------------------------------------ pins and the epoch

    def _pin_path(self, name: str) -> Path:
        return self.base / PINS / f"{safe(name)}.json"

    def _read_pins(self) -> dict[str, int]:
        """The pins on disk (caller holds the commit lock, or accepts a moment-old answer)."""
        directory = self.base / PINS
        found = sorted(directory.glob("*.json")) if directory.exists() else []
        out: dict[str, int] = {}
        for path in found:
            try:
                out[path.stem] = int(json.loads(path.read_text())["seq"])
            except FileNotFoundError:  # unpinned meanwhile
                continue
        return out

    def pins(self) -> dict[str, int]:
        """Every pin, name -> sequence, read under the commit lock."""
        with held(self._commit_lock()):
            return self._read_pins()

    def pin(self, name: str, seq: int) -> None:
        """Keep the versions a read at ``seq`` sees (from now on: ``ValueError`` above the
        published sequence). Replaces the pin of the same name."""
        with held(self._commit_lock()):
            self._recover()
            if seq > self.published():
                raise ValueError(f"pin {name!r}: sequence {seq} is above the published one")
            atomic_write(self._pin_path(name), json.dumps({"seq": seq}).encode())

    def unpin(self, name: str) -> None:
        with held(self._commit_lock()):
            self._pin_path(name).unlink(missing_ok=True)

    def epoch(self) -> int:
        """The number of destructive operations so far (0 before any)."""
        try:
            return int((self.base / EPOCH).read_text())
        except FileNotFoundError:
            return 0

    def _bump_epoch(self) -> None:
        atomic_write(self.base / EPOCH, str(self.epoch() + 1).encode())

    def bump_epoch(self) -> None:
        """Record a destructive operation made outside the commit lock (``drop``)."""
        with held(self._commit_lock()):
            self._bump_epoch()

    # ------------------------------------------------------------------ pending writes

    def journal(self, run_id: str) -> dict[str, dict[str, Any]]:
        """``table|date`` -> the run's latest pending write there (file, knowledge_ts,
        restates). The writing process keeps its own journal in memory; any other run's is
        re-read when its file changed (journals are append-only, so ``(size, mtime_ns)`` says)."""
        with self._guard:
            return dict(self._current(run_id))

    def pending_item(self, run_id: str, table: str, session_date: date) -> dict[str, Any] | None:
        """The run's pending write to one partition, without copying the whole journal."""
        with self._guard:
            return self._current(run_id).get(f"{table}|{session_date.isoformat()}")

    def _current(self, run_id: str) -> dict[str, dict[str, Any]]:
        """The journal of ``run_id`` (caller holds the guard). A run this process staged is kept
        in memory; a foreign one is never trusted from an earlier read: a long-lived process
        (a compaction worker) must see a backfill that staged after its first look."""
        if run_id in self._journals:
            return self._journals[run_id]
        try:
            stat = self._journal_path(run_id).stat()
        except FileNotFoundError:
            self._foreign.pop(run_id, None)
            return {}
        signature = (stat.st_size, stat.st_mtime_ns)
        cached = self._foreign.get(run_id)
        if cached is None or cached[0] != signature:
            cached = (signature, self._load(run_id))
            self._foreign[run_id] = cached
        return cached[1]

    def _load(self, run_id: str) -> dict[str, dict[str, Any]]:
        path = self._journal_path(run_id)
        out: dict[str, dict[str, Any]] = {}
        if not path.exists():
            return out
        for line in path.read_text().splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:  # a line cut short by a crash: that write never returned
                continue
            out[f"{item['table']}|{item['date']}"] = item
        return out

    def stage(
        self, table: str, session_date: date, run_id: str, known: str | None, restates: bool
    ) -> str | None:
        """Record a pending write of ``run_id``; -> the file to write its rows to (``None``
        for no rows). Recorded before the file is written, so an abort finds every file."""
        day = session_date.isoformat()
        key = f"{table}|{day}"
        directory = self._dir(table, day)
        with self._guard:
            if run_id not in self._journals:  # this process now owns the run's journal
                self._journals[run_id] = self._load(run_id)
            journal = self._journals[run_id]
            prior = journal.get(key, {}).get("file")
            file = None if known is None else prior or self._fresh(directory, run_id)
            if prior and prior != file:
                (directory / prior).unlink(missing_ok=True)
            item = {"table": table, "date": day, "file": file, "knowledge_ts": known,
                    "restates": restates}  # fmt: skip
            journal[key] = item
            path = self._journal_path(run_id)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as fh:
                fh.write(json.dumps(item, sort_keys=True) + "\n")
        return file

    @staticmethod
    def _fresh(directory: Path, run_id: str) -> str:
        """A name no committed version of the run ever used: the plain one for a run's first
        write to the partition, else a unique one (a resumed run replacing its rows).

        Names are never reused, even after the version holding one is dropped: a read that
        resolved its pinned version to that name before the drop opens it afterwards, and
        would read a pending write there instead of failing over (``StaleSnapshotError``)."""
        plain = default_file(run_id)
        first = run_id not in read_index(directory) and not (directory / plain).exists()
        return plain if first else f"run={run_id}~{secrets.token_hex(4)}.parquet"

    def pending_runs(self) -> list[str]:
        directory = self.base / "pending"
        return sorted(p.stem for p in directory.glob("*.jsonl")) if directory.exists() else []

    # ------------------------------------------------------------------ commit / abort

    def commit_run(self, run_id: str, at: datetime) -> int:
        with held(self._commit_lock()):
            self._recover()
            journal = self.journal(run_id)
            if not journal:
                self._forget(run_id)
                return 0
            marker = {
                "run_id": run_id,
                "seq": self.published() + 1,
                "at": pd.Timestamp(at).isoformat(),
                "entries": [journal[k] for k in sorted(journal)],
            }
            payload = json.dumps(marker, indent=2, sort_keys=True).encode()
            atomic_write(self._marker_path(run_id), payload)  # the decision point
            self._forget(run_id)
            self._apply(marker)
            return len(journal)

    def abort_run(self, run_id: str) -> int:
        with held(self._commit_lock()):
            self._recover()  # a run that reached its commit marker is completed, not undone
            journal = self.journal(run_id)
            for item in journal.values():
                if item.get("file"):
                    directory = self._dir(item["table"], item["date"])
                    if item["file"] not in _referenced(directory, run_id):
                        (directory / item["file"]).unlink(missing_ok=True)
            self._forget(run_id)
            return len(journal)

    def recover(self) -> list[str]:
        with held(self._commit_lock()):
            return self._recover()

    def purge_pending_before(self, cutoff: datetime) -> int:
        """Abort runs whose journal was last written before ``cutoff``."""
        limit = pd.Timestamp(cutoff).timestamp()
        old = [r for r in self.pending_runs() if self._journal_path(r).stat().st_mtime < limit]
        for run_id in old:
            self.abort_run(run_id)
        return len(old)

    def purge(self, directories: list[Path]) -> int:
        """Delete committed partitions (retention), committed like a run: under the commit
        lock (no commit, abort or recovery in between; a read pinned to an older sequence
        retries), each index removed under its lock before its files, then the published
        sequence moves on so readers and caches keyed on it see the purge. A partition a
        pending run has written to is kept (purged on a later pass). -> partitions deleted."""
        with held(self._commit_lock()):
            self._recover()
            busy = {
                self._dir(item["table"], item["date"])
                for run_id in self.pending_runs()
                for item in self.journal(run_id).values()
            }
            gone = [d for d in directories if d not in busy]
            if gone:
                self._bump_epoch()  # before the files go: a release is never trusted over a hole
            for directory in gone:
                with held(index_lock(directory)):  # no write is mid-way in the partition
                    (directory / INDEX).unlink(missing_ok=True)  # unindexed first
                shutil.rmtree(directory, ignore_errors=True)
            if gone:
                atomic_write(self.base / "seq", str(self.published() + 1).encode())
            return len(gone)

    def runs_of(self, directory: Path) -> list[str]:
        """The committed runs of one partition, oldest commit first."""
        entries = read_index(directory)
        return sorted(entries, key=lambda r: (entries[r].seq or -1, r))

    def sweep(self, directory: Path) -> int:
        """Delete the ``run=*.parquet`` files of one partition its index does not name (see
        ``TableStore.sweep_orphans``), under the commit lock. -> files deleted."""
        with held(self._commit_lock()):
            self._recover()
            busy = {
                self._dir(item["table"], item["date"])
                for run_id in self.pending_runs()
                for item in self.journal(run_id).values()
            }
            if directory in busy:
                raise PartitionBusyError(str(directory))
            with held(index_lock(directory)):
                entries = read_index(directory)
                named = _named(entries)
                found = [p for p in directory.glob("run=*.parquet") if p.name not in named]
                staged = {  # read after the glob: a run staged since the busy check is spared
                    item["file"]
                    for run_id in self.pending_runs()
                    for item in self.journal(run_id).values()
                    if self._dir(item["table"], item["date"]) == directory
                }
                cutoff = time.time() - ORPHAN_GRACE_S  # a direct write puts its file first
                orphans = [p for p in found if p.name not in staged and _older(p, cutoff)]
                # the temp file of an ``atomic_write`` a killed process left (a run file's)
                orphans += [p for p in directory.glob(".run=*.tmp") if _older(p, cutoff)]
                for path in orphans:
                    path.unlink(missing_ok=True)
            return len(orphans)

    def remove_runs(self, directory: Path, runs: Iterable[str]) -> int:
        """Delete committed runs of one partition (see ``TableStore.purge_runs``), committed like
        ``purge``: under the commit lock, the index rewritten under its lock before the files go,
        then the sequence moves on. ``PartitionBusyError`` when a pending run wrote to the
        partition. -> runs deleted."""
        with held(self._commit_lock()):
            self._recover()
            busy = {
                self._dir(item["table"], item["date"])
                for run_id in self.pending_runs()
                for item in self.journal(run_id).values()
            }
            if directory in busy:
                raise PartitionBusyError(str(directory))
            with held(index_lock(directory)):
                entries = read_index(directory)
                gone = [r for r in dict.fromkeys(runs) if r in entries]
                if not gone:
                    return 0
                self._bump_epoch()
                write_index(directory, {r: e for r, e in entries.items() if r not in gone})
            for run in gone:
                drop_unreferenced(directory, run)  # no longer indexed: every version's file
            atomic_write(self.base / "seq", str(self.published() + 1).encode())
            return len(gone)

    def swap_runs(
        self,
        directory: Path,
        expected: dict[str, RunEntry],
        replacement: dict[str, RunEntry],
        grace_s: float = SWAP_GRACE_S,
        clock: Callable[[], float] = time.time,
        refuse: Path | None = None,
    ) -> bool:
        """Compare-and-swap one partition's index (ADR 0078): ``replacement`` becomes the index
        only if it still equals ``expected``; -> whether it was swapped. Not a commit: the
        sequence file is never written, so ``visible_seq`` and every ``partition_seq`` stay. The
        caller wrote the files ``replacement`` names beforehand, under fresh names. Takes the
        commit lock and recovers first; ``PartitionBusyError`` when a pending run wrote to the
        partition. The files only ``expected`` named get a modification time that ``sweep`` spares
        for ``grace_s`` from now (a read that resolved them finishes on them): the caller deletes
        nothing. ``refuse``: a path that must not exist (a history copy made since the plan): the
        swap is not done. The index write is the last step and nothing after it can raise."""
        with held(self._commit_lock()):
            self._recover()
            busy = {
                self._dir(item["table"], item["date"])
                for run_id in self.pending_runs()
                for item in self.journal(run_id).values()
            }
            if directory in busy:
                raise PartitionBusyError(str(directory))
            chained = any(e.prev is not None for e in expected.values())
            with held(index_lock(directory)):
                if read_index(directory) != expected or (refuse is not None and refuse.exists()):
                    return False
                if chained and self._read_pins():  # a collapsed chain would unpin a release
                    return False
                if any(  # a file the new index names was swept or never landed: never publish it
                    not (directory / name).exists()
                    for name in _named(replacement) - _named(expected)
                ):
                    return False
                stamp = (
                    clock() + grace_s - ORPHAN_GRACE_S
                )  # sweep deletes below now - ORPHAN_GRACE_S
                for name in _named(expected) - _named(replacement):  # before the swap, best effort
                    with contextlib.suppress(OSError):
                        os.utime(directory / name, (stamp, stamp))
                write_index(directory, replacement)
            return True

    def _forget(self, run_id: str) -> None:
        with self._guard:
            self._journals.pop(run_id, None)
            self._foreign.pop(run_id, None)
            self._journal_path(run_id).unlink(missing_ok=True)

    def _recover(self) -> list[str]:
        """Complete every commit that reached its marker (caller holds the commit lock)."""
        directory = self.base / "commits"
        markers = sorted(directory.glob("*.json")) if directory.exists() else []
        loaded = sorted((json.loads(p.read_text()) for p in markers), key=lambda m: m["seq"])
        for marker in loaded:
            self._apply(marker)
            self._forget(marker["run_id"])
        return [m["run_id"] for m in loaded]

    def _apply(self, marker: dict[str, Any]) -> None:
        """Steps 2-4 of the module docstring; safe to repeat after a crash."""
        run_id, seq, at = marker["run_id"], int(marker["seq"]), pd.Timestamp(marker["at"])
        pins = set(self._read_pins().values())  # under the commit lock: no pin appears mid-apply
        touched = []
        for item in marker["entries"]:
            directory = self._dir(item["table"], item["date"])
            touched.append(directory)
            with held(index_lock(directory)):
                entries = read_index(directory)
                if item["knowledge_ts"] is not None:
                    file = item["file"]
                    ref = None if file == default_file(run_id) else file
                    known = pd.Timestamp(item["knowledge_ts"])
                    previous = entries.get(run_id)
                    entries[run_id] = committed(
                        known, bool(item["restates"]), at, seq, ref, previous, pins
                    )
                write_index(directory, entries)
        if seq > self.published():
            atomic_write(self.base / "seq", str(seq).encode())  # the visibility point
        self._marker_path(run_id).unlink(missing_ok=True)
        for directory in touched:
            drop_unreferenced(directory, run_id)


def _older(path: Path, cutoff: float) -> bool:
    """Whether ``path`` exists and was modified before ``cutoff`` (it may vanish meanwhile)."""
    try:
        return path.stat().st_mtime < cutoff
    except FileNotFoundError:
        return False


def _named(entries: dict[str, RunEntry]) -> set[str]:
    """Every file name an index names: each run's version and every older one it keeps."""
    return {run_file(run, version) for run, entry in entries.items() for version in chain(entry)}


def _referenced(directory: Path, run_id: str) -> set[str]:
    """Files of ``run_id`` the partition's index refers to (its version and every older kept)."""
    return {run_file(run_id, e) for e in chain(read_index(directory).get(run_id))}


def drop_unreferenced(directory: Path, run_id: str) -> None:
    """Remove files of ``run_id`` in the partition its index no longer refers to."""
    keep = _referenced(directory, run_id)
    candidates = [directory / default_file(run_id), *directory.glob(f"run={run_id}~*.parquet")]
    for path in candidates:
        if path.name not in keep:
            path.unlink(missing_ok=True)
