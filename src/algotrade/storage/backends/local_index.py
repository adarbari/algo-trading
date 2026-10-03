"""Local backend: each partition's run index (``_runs.json``) and atomic run commits (ADR 0022).

A run writing ``pending`` puts its Parquet files in place but records them only in its own
journal (``tables/_txn/pending/<run>.jsonl``); no partition index names them, so no read
sees them. ``commit_run`` makes every partition the run wrote visible at once:

1. under the store's commit lock, the journal becomes a commit marker
   (``_txn/commits/<run>.json``, written atomically) with the next commit sequence number.
   This is the decision point: from here the commit is completed, never undone;
2. each partition's index gets the run's entry (``seq``, ``visible_at``; the version it
   replaces is kept as ``prev``), under that partition's index lock;
3. ``_txn/seq`` is set to the sequence number: the visibility point. A read captures
   ``seq`` before it opens any index and ignores entries above it, so it sees all of a
   commit or none of it (``run_selection.visible_entries``);
4. the marker, and files of the run no index entry refers to any more, are removed.

A crash after 1 leaves the marker: ``recover`` (and every later commit or abort, first)
re-applies it, which is idempotent. A crash before 1 leaves only the journal and files no
index refers to: ``abort_run`` deletes them (the ingestion startup recovery, or retention).

Every file is written to a unique temp file in its directory and renamed into place.
"""

import json
import os
import secrets
import tempfile
import threading
from collections.abc import Iterable
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from algotrade.storage.backends.run_selection import RunEntry, committed
from algotrade.storage.locks import FileLock, held

INDEX = "_runs.json"
INDEX_LOCK = ".runs.lock"
TXN = "_txn"


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
    optional ``restates``, ``visible_at``, ``seq``, ``file`` and ``prev``."""
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
        self._guard = threading.Lock()

    def _dir(self, table: str, day: str) -> Path:
        return self.tables / table / f"date={day}"

    def _journal_path(self, run_id: str) -> Path:
        return self.base / "pending" / f"{safe(run_id)}.jsonl"

    def _marker_path(self, run_id: str) -> Path:
        return self.base / "commits" / f"{safe(run_id)}.json"

    def _commit_lock(self) -> FileLock:
        return FileLock(self.base / "commit.lock")

    def published(self) -> int:
        """The highest commit sequence number whose entries every index already holds."""
        try:
            return int((self.base / "seq").read_text())
        except FileNotFoundError:
            return 0

    # ------------------------------------------------------------------ pending writes

    def journal(self, run_id: str) -> dict[str, dict[str, Any]]:
        """``table|date`` -> the run's latest pending write there (file, knowledge_ts,
        restates). Kept in memory by the writing process; read from disk otherwise."""
        with self._guard:
            if run_id not in self._journals:
                self._journals[run_id] = self._load(run_id)
            return dict(self._journals[run_id])

    def pending_item(self, run_id: str, table: str, session_date: date) -> dict[str, Any] | None:
        """The run's pending write to one partition, without copying the whole journal."""
        with self._guard:
            if run_id not in self._journals:
                self._journals[run_id] = self._load(run_id)
            return self._journals[run_id].get(f"{table}|{session_date.isoformat()}")

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
            journal = self._journals.setdefault(run_id, self._load(run_id))
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
        """A file no committed version of the run uses: the plain name for a run's first
        write to the partition, else a unique one (a resumed run replacing its rows)."""
        plain = default_file(run_id)
        return (
            plain
            if not (directory / plain).exists()
            else f"run={run_id}~{secrets.token_hex(4)}.parquet"
        )

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

    def _forget(self, run_id: str) -> None:
        with self._guard:
            self._journals.pop(run_id, None)
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
                        known, bool(item["restates"]), at, seq, ref, previous
                    )
                write_index(directory, entries)
        if seq > self.published():
            atomic_write(self.base / "seq", str(seq).encode())  # the visibility point
        self._marker_path(run_id).unlink(missing_ok=True)
        for directory in touched:
            drop_unreferenced(directory, run_id)


def _referenced(directory: Path, run_id: str) -> set[str]:
    """Files of ``run_id`` the partition's index refers to (its version and the one before)."""
    entry = read_index(directory).get(run_id)
    versions: Iterable[RunEntry | None] = (entry, entry.prev if entry else None)
    return {run_file(run_id, e) for e in versions if e is not None}


def drop_unreferenced(directory: Path, run_id: str) -> None:
    """Remove files of ``run_id`` in the partition its index no longer refers to."""
    keep = _referenced(directory, run_id)
    candidates = [directory / default_file(run_id), *directory.glob(f"run={run_id}~*.parquet")]
    for path in candidates:
        if path.name not in keep:
            path.unlink(missing_ok=True)
