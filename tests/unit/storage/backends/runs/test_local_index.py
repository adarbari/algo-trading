"""``Commits`` of the local backend as a compaction worker meets it (ADR 0078 amendment
2026-10-20): another process's journal is never trusted from an earlier read, a swap never
publishes an index naming a file that is not there, and a killed writer's temp file is swept."""

import dataclasses
import json
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.runs import local_index
from algotrade.storage.backends.runs.local_index import SWAP_GRACE_S, read_index
from algotrade.storage.tables.interfaces import PartitionBusyError
from tests.helpers.stored_frames import T0, stamped

TABLE = "events/dividend"
DAY, OTHER = date(2026, 10, 2), date(2026, 10, 5)


def put(backend: LocalBackend, run: str, day: date, commit: bool) -> None:
    ts = pd.Timestamp(day, tz="UTC")
    rows = [{"instrument_id": "EQ:A", "ts": ts, "cash_amount": 1.0}]
    frame = stamped(rows, day, run, T0 + timedelta(hours=1))
    backend.tables.write(TABLE, day, run, frame, pending=True)
    if commit:
        backend.tables.commit_run(run, T0 + timedelta(days=1))


def age(directory: Path) -> None:
    for path in directory.iterdir():
        os.utime(path, (0, 0))


def test_a_run_staged_after_a_foreign_journal_was_first_read_is_not_swept(tmp_path: Path) -> None:
    """The first test of the PR: a long-lived worker read a backfill's journal early (one
    partition); the backfill then staged a file into another. The worker's sweep must see it."""
    worker, backfill = LocalBackend(tmp_path), LocalBackend(tmp_path)
    put(backfill, "r1", DAY, commit=True)
    put(backfill, "bf", OTHER, commit=False)
    assert worker.tables.commits.journal("bf")  # the worker's first read: only OTHER is in it
    put(backfill, "bf", DAY, commit=False)  # staged later, into the partition being swept
    directory = tmp_path / "tables" / TABLE / f"date={DAY.isoformat()}"
    age(directory)
    staged = next(directory.glob("run=bf*.parquet"))
    with pytest.raises(PartitionBusyError):
        worker.tables.sweep_orphans(TABLE, DAY)
    assert staged.exists()
    assert worker.tables.commits.pending_item("bf", TABLE, DAY) is not None


def test_a_journal_that_did_not_change_is_not_read_again(tmp_path: Path) -> None:
    worker, backfill = LocalBackend(tmp_path), LocalBackend(tmp_path)
    put(backfill, "bf", DAY, commit=False)
    commits = worker.tables.commits
    first = commits.journal("bf")
    cached = commits._foreign["bf"][1]
    assert commits.journal("bf") == first and commits._foreign["bf"][1] is cached


def test_a_committed_run_leaves_no_cached_journal(tmp_path: Path) -> None:
    worker, backfill = LocalBackend(tmp_path), LocalBackend(tmp_path)
    put(backfill, "bf", DAY, commit=False)
    assert worker.tables.commits.journal("bf")
    backfill.tables.commit_run("bf", T0 + timedelta(days=1))
    assert worker.tables.commits.journal("bf") == {}
    assert "bf" not in worker.tables.commits._foreign


def test_a_swap_naming_a_missing_file_is_refused(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    put(backend, "r1", DAY, commit=True)
    directory = tmp_path / "tables" / TABLE / f"date={DAY.isoformat()}"
    expected = read_index(directory)
    ghost = {"r1": dataclasses.replace(expected["r1"], ref="run=r1~dead.parquet")}
    before = (directory / "_runs.json").read_text()
    assert backend.tables.commits.swap_runs(directory, expected, ghost) is False
    assert (directory / "_runs.json").read_text() == before
    (directory / "run=r1~dead.parquet").write_bytes(b"x")  # present: the swap goes through
    assert backend.tables.commits.swap_runs(directory, expected, ghost) is True


def test_the_temp_file_of_a_killed_write_is_swept_once_old(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path)
    put(backend, "r1", DAY, commit=True)
    directory = tmp_path / "tables" / TABLE / f"date={DAY.isoformat()}"
    old, young = directory / ".run=x.parquet.ab12.tmp", directory / ".run=y.parquet.cd34.tmp"
    old.write_bytes(b"x")
    young.write_bytes(b"y")
    os.utime(old, (0, 0))
    assert backend.tables.sweep_orphans(TABLE, DAY) == 1
    assert not old.exists() and young.exists() and (directory / "run=r1.parquet").exists()


def test_the_swap_grace_is_thirty_seconds() -> None:
    assert SWAP_GRACE_S == 30.0


def files(backend: LocalBackend, day: date = DAY) -> set[str]:
    return {p.name for p in (backend.tables.root / TABLE / f"date={day.isoformat()}").glob("run=*")}


def test_a_pinned_chain_keeps_its_files_through_sweeps_and_recommits_and_gap_round_trips(
    tmp_path: Path,
) -> None:
    backend = LocalBackend(tmp_path / "data")
    directory = backend.tables.root / TABLE / f"date={DAY.isoformat()}"
    put(backend, "r1", DAY, True)
    backend.tables.pin("release-a", backend.tables.visible_seq())
    for _ in range(4):
        put(backend, "r1", DAY, True)  # five versions of r1, the first pinned
    entry = read_index(directory)["r1"]
    chain_files = {entry.ref, entry.prev.ref, entry.prev.prev.ref}  # type: ignore[union-attr]
    assert entry.prev is not None and entry.prev.gap is not None  # a hole, recorded
    assert files(backend) >= {f for f in chain_files if f}
    age(directory)
    assert backend.tables.sweep_orphans(TABLE, DAY) == 0  # every file of the chain is named
    assert read_index(directory) == {"r1": entry}  # the index round-trips with its gaps
    backend.tables.unpin("release-a")
    put(backend, "r1", DAY, True)
    assert len(files(backend)) == 2  # head and the one before: the pinned ones are deleted


def test_an_unchanged_index_is_parsed_once_and_a_replaced_one_again(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The memo of ``read_index`` is keyed by the file's identity: reads of an unchanged index
    parse nothing, a write (a rename onto a new inode) is seen by the next read, and a caller's
    edit of the returned dict never reaches the memo."""
    backend = LocalBackend(tmp_path)
    put(backend, "r1", DAY, commit=True)
    directory = tmp_path / "tables" / TABLE / f"date={DAY.isoformat()}"
    local_index._PARSED.clear()
    parsed: list[int] = []
    real = json.loads

    def counting(text: str) -> Any:
        parsed.append(1)
        return real(text)

    monkeypatch.setattr(json, "loads", counting)
    first = read_index(directory)
    first.clear()  # a caller editing its copy before write_index
    assert set(read_index(directory)) == {"r1"} and set(read_index(directory)) == {"r1"}
    assert len(parsed) == 1
    put(backend, "r2", DAY, commit=True)
    assert set(read_index(directory)) == {"r1", "r2"}
    assert len(parsed) == 2
