"""The local backend's version-file reader: ``_read_file`` decodes exactly what
``pq.read_table`` did (same columns, types, metadata and row order), a whole range read too,
and an empty instrument list still raises (the contract suite covers everything else).

Table listing (``names``) walks directories only and equals the recursive glob it replaced,
on nested table paths and with stray directories.

The ``perf`` tests are the budget of Market.history's read (13,500 one-row partitions, two
columns) and of the table listing (50,000 partitions), serial, cold, on an idle machine
(``make perf``): the first ceiling is the time measured when it landed (target under 5 s,
docs/roadmap.md); the listing's is 0.2 s."""

import shutil
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from algotrade.storage.backends import local
from algotrade.storage.backends.local import LocalBackend, _read_file
from tests.helpers.stored_frames import T0, stamped

TABLE = "rollups/market/demo@v1"
START = date(1971, 1, 1)
BUDGET_S = 15.0  # the perf test's ceiling: the measured serial read (see the PR), not the target


def _days(n: int) -> list[date]:
    return [START + timedelta(days=i) for i in range(n)]


def _write(root: Path, n: int) -> LocalBackend:
    backend = LocalBackend(root)
    for i, day in enumerate(_days(n)):
        rows = [
            {"instrument_id": f"EQ:{s}", "a": float(i), "b": i * 2, "c": f"{s}{i}"} for s in "XYZ"
        ]
        backend.tables.write(TABLE, day, "r1", stamped(rows, day, "r1"))
        if i % 7 == 0:  # a later run restating some partitions: two versions to select from
            later = T0 + timedelta(hours=1)
            backend.tables.write(TABLE, day, "r2", stamped(rows[:1], day, "r2", later))
    return backend


def _read_table(path: Path, instruments: Any, columns: Any) -> pa.Table:
    """The reader before this change (``read_table`` with a filter), for comparison."""
    filters = None if instruments is None else [("instrument_id", "in", list(instruments))]
    if columns is None:
        return pq.read_table(path, filters=filters)
    keep = local.keep_columns(columns)
    present = [c for c in pq.read_schema(path).names if c in keep]
    return pq.read_table(path, filters=filters, columns=present)


def _first_file(store: Path) -> Path:
    return next((store / "tables" / TABLE / f"date={START.isoformat()}").glob("run=r1*.parquet"))


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("local") / "data"
    _write(root, 30)
    return root


@pytest.mark.parametrize(
    ("instruments", "columns"),
    [(None, None), (["EQ:Y"], None), (None, ["a"]), (["EQ:Z", "EQ:X"], ["b"]), (["EQ:Q"], None)],
)
def test_read_file_decodes_what_read_table_did(
    store: Path, instruments: list[str] | None, columns: list[str] | None
) -> None:
    path = _first_file(store)
    expected = _read_table(path, instruments, columns)
    assert _read_file(path, instruments, columns).equals(expected, check_metadata=True)


def test_no_instruments_still_raise(store: Path) -> None:
    """``read_table`` failed on an empty "in" list (a null-typed set); so does the reader."""
    with pytest.raises(pa.ArrowTypeError):
        _read_file(_first_file(store), [], None)


@pytest.mark.parametrize(
    ("instruments", "columns", "as_of"),
    [(None, None, None), (["EQ:X", "EQ:Z"], ["a"], None), (None, ["b"], T0)],
)
def test_a_range_read_equals_the_read_table_one(
    store: Path,
    monkeypatch: pytest.MonkeyPatch,
    instruments: list[str] | None,
    columns: list[str] | None,
    as_of: Any,
) -> None:
    args = (TABLE, START, _days(30)[-1], as_of, instruments, None, columns)
    out = LocalBackend(store).tables.read_range(*args)
    monkeypatch.setattr(local, "_read_file", _read_table)
    expected = LocalBackend(store).tables.read_range(*args)
    assert out is not None and expected is not None and len(out) > 30
    pd.testing.assert_frame_equal(out, expected, check_exact=True)


@pytest.mark.perf
def test_a_13500_partition_two_column_read_is_within_budget(tmp_path: Path) -> None:
    n = 13_500
    root = tmp_path / "data"
    _write(root, 1)  # one partition, copied: writing 13,500 through the index takes ~40 s
    base = root / "tables" / TABLE
    first = base / f"date={START.isoformat()}"
    for day in _days(n)[1:]:
        shutil.copytree(first, base / f"date={day.isoformat()}")
    start = time.perf_counter()
    out = LocalBackend(root).tables.read_range(TABLE, START, _days(n)[-1], columns=["a", "b"])
    elapsed = time.perf_counter() - start
    assert out is not None and len(out) == n  # the restating r2 (one row) is the latest
    assert elapsed < BUDGET_S, f"{elapsed:.2f} s for {n} partitions (budget {BUDGET_S} s)"


def _index_files(tables: Path, layout: dict[str, int]) -> None:
    """Indexed partitions (a bare ``_runs.json``: all the listing looks at) per table path."""
    for table, n in layout.items():
        for day in _days(n):
            partition = tables / table / f"date={day.isoformat()}"
            partition.mkdir(parents=True)
            (partition / local.INDEX).write_text("{}")


def test_table_names_equal_the_recursive_glob_on_nested_tables_and_stray_directories(
    tmp_path: Path,
) -> None:
    tables = tmp_path / "data" / "tables"
    _index_files(
        tables,
        {"bars/1d": 3, "rollups/market/regime@v2": 2, "macro/series": 1, "reference": 4},
    )
    (tables / "stray" / "empty").mkdir(parents=True)  # a directory with no partition
    (tables / "stray" / "notes.txt").write_text("x")
    (tables / "unindexed" / "date=2020-01-01").mkdir(parents=True)  # a day with no index
    (tables / "bars" / "1d" / f"date={START.isoformat()}" / "file.parquet").write_text("x")
    (tables / "_txn" / "commits").mkdir(parents=True)
    (tables / "_txn" / "commits" / "r1.json").write_text("{}")
    old = sorted(
        {
            p.parent.parent.relative_to(tables).as_posix()
            for p in tables.glob(f"**/date=*/{local.INDEX}")
        }
    )
    names = LocalBackend(tmp_path / "data").tables.names()
    assert names == old == ["bars/1d", "macro/series", "reference", "rollups/market/regime@v2"]


def test_table_names_of_an_empty_store_are_empty(tmp_path: Path) -> None:
    assert LocalBackend(tmp_path / "data").tables.names() == []


@pytest.mark.perf
def test_listing_tables_of_50000_partitions_is_within_budget(tmp_path: Path) -> None:
    tables = tmp_path / "data" / "tables"
    _index_files(
        tables,
        {"bars/1d": 20_000, "rollups/market/regime@v2": 20_000, "macro/series": 10_000},
    )
    backend = LocalBackend(tmp_path / "data")
    start = time.perf_counter()
    names = backend.tables.names()
    elapsed = time.perf_counter() - start
    assert names == ["bars/1d", "macro/series", "rollups/market/regime@v2"]
    assert elapsed < 0.2, f"{elapsed:.3f} s for 50,000 partitions (budget 0.2 s)"
