"""Local filesystem backend: Parquet tables, gzip raw responses, JSON run records.

Layout under the root directory (an internal detail; nothing else may rely on it)::

    tables/<table>/date=YYYY-MM-DD/run=<run_id>.parquet   (+ _runs.json knowledge index,
                                                           .runs.lock guarding it)
                                                          typed per storage/schemas.py,
                                                          ~64k-row groups + page index
    raw/source=<s>/dataset=<d>/date=YYYY-MM-DD/run=<run_id>/<key>.json.gz
    staging/<run_id>/<table>/<key>.parquet
    runs/<run_id>.json
    locks/<name>.lock                                      (Backend.lock, e.g. the ingest run)

Every file is written to a unique temp file in its directory and renamed into place, so
concurrent writers never share a temp file and readers never see half a file. The
``_runs.json`` read-modify-write is serialised by a file lock, so two runs writing the same
partition at once (threads or processes) are both indexed.
"""

import gzip
import json
import os
import shutil
import tempfile
from collections.abc import Sequence
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from algotrade.storage.backends.arrow import concat, conform, parquet_bytes, to_arrow, to_frame
from algotrade.storage.backends.selection import concat_frames, latest_run, select_instruments
from algotrade.storage.locks import FileLock, held
from algotrade.storage.runs import RunRecord, run_session

_INDEX = "_runs.json"
_INDEX_LOCK = ".runs.lock"


def _atomic_write(path: Path, data: bytes) -> None:
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


def _safe(key: str) -> str:
    if not key or "/" in key or key.startswith("."):
        raise ValueError(f"invalid storage key {key!r}")
    return key


def _parquet_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_parquet(index=False, engine="pyarrow", compression="zstd")


class LocalTables:
    def __init__(self, root: Path) -> None:
        self.root = root / "tables"

    def _dir(self, table: str, session_date: date) -> Path:
        return self.root / table / f"date={session_date.isoformat()}"

    def write(self, table: str, session_date: date, run_id: str, frame: pd.DataFrame) -> None:
        directory = self._dir(table, session_date)
        data = parquet_bytes(to_arrow(table, frame))
        _atomic_write(directory / f"run={_safe(run_id)}.parquet", data)
        with held(FileLock(directory / _INDEX_LOCK)):
            index = self._index(directory)
            if not frame.empty:
                index[run_id] = pd.Timestamp(frame["knowledge_ts"].max()).isoformat()
            _atomic_write(directory / _INDEX, json.dumps(index, indent=2, sort_keys=True).encode())

    def _chosen_file(self, table: str, session_date: date, as_of: datetime | None) -> Path | None:
        directory = self._dir(table, session_date)
        known = {run: pd.Timestamp(ts) for run, ts in self._index(directory).items()}
        chosen = latest_run(known, as_of)
        return None if chosen is None else directory / f"run={chosen}.parquet"

    def read(
        self,
        table: str,
        session_date: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        path = self._chosen_file(table, session_date, as_of)
        if path is None:
            return None
        filters = [("instrument_id", "in", list(instruments))] if instruments is not None else None
        frame = to_frame(conform(table, pq.read_table(path, filters=filters)))
        return select_instruments(frame, instruments)

    def read_range(
        self,
        table: str,
        start: date,
        end: date,
        as_of: datetime | None = None,
        instruments: Sequence[str] | None = None,
    ) -> pd.DataFrame | None:
        paths = [
            path
            for d in self.dates(table)
            if start <= d <= end and (path := self._chosen_file(table, d, as_of)) is not None
        ]
        if not paths:
            return None
        filters = [("instrument_id", "in", list(instruments))] if instruments is not None else None
        combined = concat(table, [pq.read_table(path, filters=filters) for path in paths])
        return concat_frames([to_frame(combined)])

    def dates(self, table: str) -> list[date]:
        base = self.root / table
        if not base.exists():
            return []
        return sorted(
            date.fromisoformat(p.name.removeprefix("date="))
            for p in base.iterdir()
            if p.name.startswith("date=") and (p / _INDEX).exists()
        )

    def names(self) -> list[str]:
        if not self.root.exists():
            return []
        found = {p.parent.parent.relative_to(self.root).as_posix()
                 for p in self.root.glob(f"**/date=*/{_INDEX}")}  # fmt: skip
        return sorted(found)

    @staticmethod
    def _index(directory: Path) -> dict[str, str]:
        path = directory / _INDEX
        loaded: dict[str, str] = json.loads(path.read_text()) if path.exists() else {}
        return loaded


class LocalRaw:
    def __init__(self, root: Path) -> None:
        self.root = root / "raw"

    def _path(self, source: str, dataset: str, session_date: date, run_id: str, key: str) -> Path:
        return (
            self.root
            / f"source={source}"
            / f"dataset={dataset}"
            / f"date={session_date.isoformat()}"
            / f"run={_safe(run_id)}"
            / f"{_safe(key)}.json.gz"
        )

    def put(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str, payload: bytes
    ) -> None:
        path = self._path(source, dataset, session_date, run_id, key)
        _atomic_write(path, gzip.compress(payload, mtime=0))

    def get(
        self, source: str, dataset: str, session_date: date, run_id: str, key: str
    ) -> bytes | None:
        path = self._path(source, dataset, session_date, run_id, key)
        return gzip.decompress(path.read_bytes()) if path.exists() else None

    def purge_before(self, cutoff: date) -> int:
        removed = 0
        for day in self.root.glob("source=*/dataset=*/date=*"):
            if date.fromisoformat(day.name.removeprefix("date=")) < cutoff:
                removed += sum(1 for _ in day.rglob("*.json.gz"))
                shutil.rmtree(day)
        return removed


class LocalStaging:
    def __init__(self, root: Path) -> None:
        self.root = root / "staging"

    def put(self, run_id: str, table: str, key: str, frame: pd.DataFrame) -> None:
        _atomic_write(
            self.root / _safe(run_id) / table / f"{_safe(key)}.parquet", _parquet_bytes(frame)
        )

    def keys(self, run_id: str, table: str) -> list[str]:
        directory = self.root / run_id / table
        return sorted(p.stem for p in directory.glob("*.parquet")) if directory.exists() else []

    def collect(self, run_id: str, table: str) -> pd.DataFrame | None:
        directory = self.root / run_id / table
        parts = [pd.read_parquet(directory / f"{k}.parquet") for k in self.keys(run_id, table)]
        parts = [p for p in parts if not p.empty]
        return pd.concat(parts, ignore_index=True) if parts else None

    def clear(self, run_id: str) -> None:
        shutil.rmtree(self.root / _safe(run_id), ignore_errors=True)

    def purge_before(self, cutoff: date) -> int:
        old = [
            d
            for d in (self.root.iterdir() if self.root.exists() else [])
            if d.is_dir() and (s := run_session(d.name)) is not None and s < cutoff
        ]
        for directory in old:
            shutil.rmtree(directory, ignore_errors=True)
        return len(old)


class LocalRuns:
    def __init__(self, root: Path) -> None:
        self.root = root / "runs"

    def save(self, record: RunRecord) -> None:
        _atomic_write(self.root / f"{_safe(record.run_id)}.json", record.to_json().encode())

    def load(self, run_id: str) -> RunRecord | None:
        path = self.root / f"{_safe(run_id)}.json"
        return RunRecord.from_json(path.read_text()) if path.exists() else None

    def find(self, job: str, session_date: date | None = None) -> list[RunRecord]:
        if not self.root.exists():
            return []
        records = [RunRecord.from_json(p.read_text()) for p in self.root.glob("*.json")]
        hits = [r for r in records if r.job == job and session_date in (None, r.session_date)]
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
        return FileLock(self.root / "locks" / f"{_safe(name)}.lock")
