"""The history copy (ADR 0060): a read served from it equals the read of the partitions (rows,
order, dtypes), a changed partition makes the year fall back, and the one-instrument read is
within its budget.

The reference is a read at an ``as_of`` after every run, which always takes the partition path
and resolves to what ``as_of`` None does. The ``perf`` test is the budget of an Explore chart's
read (one instrument, one year) from the copy (``make perf``)."""

import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from algotrade.storage.backends import history
from algotrade.storage.backends.history import HISTORY, MANIFEST
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from tests.helpers.stored_frames import T0, stamped

TABLE = "rollups/instrument/demo@v1"
EVENTS = "events/demo"
LATER = T0 + timedelta(hours=1)
FUTURE = datetime(2200, 1, 1, tzinfo=UTC)
FIRST = date(2025, 12, 20)
IDS = ["EQ:A", "EQ:B", "EQ:C", "EQ:D"]


def _days(n: int) -> list[date]:
    return [FIRST + timedelta(days=i) for i in range(n)]


def _rows(i: int, ids: list[str] = IDS, scale: float = 1.0) -> list[dict[str, Any]]:
    return [
        {"instrument_id": s, "a": i * scale + k, "b": i * 2 + k, "c": f"{s}{i}"}
        for k, s in enumerate(ids)
    ]


def _store(root: Path, n: int = 30) -> LocalBackend:
    """``n`` days over a year boundary; some partitions restated by a later run (a superseded
    one), one partition with its rows in another order, one superseded twice."""
    backend = LocalBackend(root)
    for i, day in enumerate(_days(n)):
        ids = IDS[::-1] if i == 3 else IDS
        backend.tables.write(TABLE, day, "r1", stamped(_rows(i, ids), day, "r1"))
        if i % 4 == 0:  # superseded by a later run on the snapshot table
            backend.tables.write(TABLE, day, "r2", stamped(_rows(i, ids, 10.0), day, "r2", LATER))
        if i == 5:
            frame = stamped(_rows(i), day, "r3", LATER + timedelta(hours=1))
            backend.tables.write(TABLE, day, "r3", frame)
        if i % 3 == 0:  # the merge-mode table: a later run revises one row, keeps the rest
            event = stamped(
                [{**r, "ts": pd.Timestamp(day, tz="UTC")} for r in _rows(i)], day, "r1"
            ).assign(known_from=day)
            backend.tables.write(EVENTS, day, "r1", event)
            revised = event.iloc[:1].assign(a=-1.0, run_id="r2", knowledge_ts=pd.Timestamp(LATER))
            backend.tables.write(EVENTS, day, "r2", revised)
    return backend


def _reference(
    backend: LocalBackend, table: str, start: date, end: date, **query: Any
) -> pd.DataFrame | None:
    return backend.tables.read_range(table, start, end, as_of=FUTURE, **query)


@contextmanager
def _copy_reads(backend: LocalBackend) -> Iterator[list[int]]:
    """The years ``read_range`` took from the copy during the block."""
    taken: list[int] = []
    real = backend.tables.history.read_year

    def spy(table: str, year: int, *rest: Any) -> Any:
        taken.append(year)
        return real(table, year, *rest)

    backend.tables.history.read_year = spy  # type: ignore[method-assign, assignment]
    try:
        yield taken
    finally:
        backend.tables.history.read_year = real  # type: ignore[method-assign, assignment]


def _same(left: pd.DataFrame | None, right: pd.DataFrame | None) -> None:
    assert (left is None) == (right is None)
    if left is not None and right is not None:
        assert_frame_equal(left, right)


QUERIES: list[dict[str, Any]] = [
    {},
    {"instruments": ["EQ:B"]},
    {"instruments": ["EQ:D", "EQ:A", "EQ:ZZ"]},
    {"instruments": []},
    {"columns": ["a"]},
    {"instruments": ["EQ:C"], "columns": ["b", "extra"]},
]
RANGES = [
    (date(2025, 1, 1), date(2026, 12, 31)),
    (date(2025, 12, 25), date(2026, 1, 5)),
    (date(2026, 1, 3), date(2026, 1, 3)),
    (date(2025, 12, 20), date(2025, 12, 31)),
    (date(2027, 1, 1), date(2027, 2, 1)),
]


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> LocalBackend:
    backend = _store(tmp_path_factory.mktemp("history") / "data")
    for table in (TABLE, EVENTS):
        assert backend.tables.build_history(table, [2025, 2026]) == [2025, 2026]
    return backend


@pytest.mark.parametrize("table", [TABLE, EVENTS])
@pytest.mark.parametrize("query", QUERIES)
@pytest.mark.parametrize(("start", "end"), RANGES)
def test_the_copy_read_equals_the_partition_read(
    built: LocalBackend, table: str, query: dict[str, Any], start: date, end: date
) -> None:
    backend = built
    expected = _reference(backend, table, start, end, **query)
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(table, start, end, **query)
    _same(got, expected)
    if expected is not None and query.get("instruments") and (table == EVENTS or end.year >= 2026):
        assert taken, "the filtered read was not served from the copy"


def test_an_all_instrument_short_read_stays_on_the_partitions(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2025, 2026])
    with _copy_reads(backend) as taken:
        out = backend.tables.read_range(TABLE, date(2026, 1, 1), date(2026, 1, 9))
    assert taken == [] and out is not None
    _same(out, _reference(backend, TABLE, date(2026, 1, 1), date(2026, 1, 9)))


def test_a_year_built_for_all_instruments_serves_a_long_unfiltered_range(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    for i, day in enumerate(date(2025, 1, 1) + timedelta(days=n) for n in range(300)):
        backend.tables.write(TABLE, day, "r1", stamped(_rows(i), day, "r1"))
    backend.tables.build_history(TABLE, [2025])
    start, end = date(2025, 1, 1), date(2025, 12, 31)
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, start, end)
    assert taken == [2025]
    _same(got, _reference(backend, TABLE, start, end))


def test_a_new_partition_in_a_year_makes_that_year_fall_back(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2025, 2026])
    new = _days(30)[-1] + timedelta(days=1)  # 2026-01-19: one more session in 2026
    backend.tables.write(TABLE, new, "r9", stamped(_rows(99), new, "r9", LATER))
    args = (date(2025, 12, 1), date(2026, 3, 1))
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    assert taken == [2025]  # 2025 is untouched and still served by its copy
    expected = _reference(backend, TABLE, *args, instruments=["EQ:A"])
    _same(got, expected)
    assert got is not None and new in set(got["session_date"])


def test_a_restated_partition_makes_its_year_fall_back(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2025, 2026])
    day = date(2025, 12, 22)
    backend.tables.write(TABLE, day, "r7", stamped(_rows(1, scale=100.0), day, "r7", LATER), True)
    args = (date(2025, 12, 1), date(2026, 3, 1))
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    assert taken == [2026]
    _same(got, _reference(backend, TABLE, *args, instruments=["EQ:A"]))


def test_a_pending_write_changes_nothing_until_it_commits(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2025, 2026])
    day = date(2026, 1, 2)
    frame = stamped(_rows(7, scale=5.0), day, "r8", LATER)
    backend.tables.write(TABLE, day, "r8", frame, pending=True)
    args = (date(2025, 12, 1), date(2026, 3, 1))
    with _copy_reads(backend) as taken:
        before = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    assert taken == [2025, 2026]  # the pending run is invisible: the copy still serves
    _same(before, _reference(backend, TABLE, *args, instruments=["EQ:A"]))
    backend.tables.commit_run("r8", LATER)
    with _copy_reads(backend) as taken:
        after = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    assert taken == [2025]
    _same(after, _reference(backend, TABLE, *args, instruments=["EQ:A"]))
    assert after is not None and 7 * 5.0 in set(after["a"])


def test_a_purged_partition_makes_its_year_fall_back(tmp_path: Path) -> None:
    root = tmp_path / "data"
    backend = _store(root)
    backend.tables.build_history(TABLE, [2025, 2026])
    gone = root / "tables" / TABLE / "date=2025-12-25"  # what retention removes (Commits.purge)
    assert backend.tables.commits.purge([gone]) == 1
    args = (date(2025, 12, 1), date(2026, 3, 1))
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    assert taken == [2026]
    _same(got, _reference(backend, TABLE, *args, instruments=["EQ:A"]))
    assert got is not None and date(2025, 12, 25) not in set(got["session_date"])


def test_as_of_and_own_run_reads_never_use_the_copy(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2025, 2026])
    args = (date(2025, 1, 1), date(2026, 12, 31))
    with _copy_reads(backend) as taken:
        pinned = backend.tables.read_range(TABLE, *args, as_of=T0 + timedelta(minutes=1))
        own = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"], own_run="r1")
    assert taken == []
    assert pinned is not None and own is not None
    assert set(pinned["run_id"]) <= {"r1"}  # the superseding runs are not yet known at that time


def test_a_copy_whose_file_is_gone_or_damaged_falls_back(tmp_path: Path) -> None:
    root = tmp_path / "data"
    backend = _store(root)
    backend.tables.build_history(TABLE, [2025, 2026])
    folder = root / "tables" / TABLE / HISTORY
    files = sorted(folder.glob("year=*.parquet"))
    files[0].unlink()
    files[1].write_bytes(b"not parquet")
    args = (date(2025, 1, 1), date(2026, 12, 31))
    got = backend.tables.read_range(TABLE, *args, instruments=["EQ:A"])
    _same(got, _reference(backend, TABLE, *args, instruments=["EQ:A"]))
    (folder / MANIFEST).write_text("{ damaged")
    _same(
        LocalBackend(root).tables.read_range(TABLE, *args, instruments=["EQ:A"]),
        _reference(backend, TABLE, *args, instruments=["EQ:A"]),
    )


def test_build_keeps_a_fresh_year_rebuilds_a_changed_one_and_drops_the_rest(
    tmp_path: Path,
) -> None:
    root = tmp_path / "data"
    backend = _store(root)
    folder = root / "tables" / TABLE / HISTORY
    assert backend.tables.build_history(TABLE, [2025, 2026]) == [2025, 2026]
    assert backend.tables.build_history(TABLE, [2025, 2026]) == []  # nothing changed
    day = date(2026, 1, 4)
    backend.tables.write(TABLE, day, "r6", stamped(_rows(3, scale=7.0), day, "r6", LATER))
    assert backend.tables.build_history(TABLE, [2025, 2026]) == [2026]
    assert len(list(folder.glob("year=*.parquet"))) == 2  # the replaced file is removed
    assert backend.tables.build_history(TABLE, [2026, 2024]) == []  # 2024 has no partitions
    assert set(backend.tables.history.years(TABLE)) == {2026}
    assert len(list(folder.glob("year=*.parquet"))) == 1
    assert backend.tables.history.years("rollups/instrument/none@v1") == {}


def test_the_manifest_records_what_a_year_was_built_from(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2026])
    copy = backend.tables.history.years(TABLE)[2026]
    assert copy.seq == backend.tables.visible_seq()
    assert sorted(copy.days) == [d.isoformat() for d in _days(30) if d.year == 2026]
    assert copy.rows == 4 * len(copy.days)


def test_the_copy_is_sorted_by_instrument_with_small_row_groups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(history, "ROW_GROUP_ROWS", 10)
    backend = _store(tmp_path / "data")
    backend.tables.build_history(TABLE, [2026])
    folder = tmp_path / "data" / "tables" / TABLE / HISTORY
    parquet = pq.ParquetFile(next(folder.glob("year=2026*.parquet")))
    assert parquet.metadata.num_row_groups > 1
    data = parquet.read().to_pandas()
    assert list(data.columns[-2:]) == [history.DAY, history.POS]
    assert data["instrument_id"].is_monotonic_increasing
    assert not data.duplicated(["instrument_id", history.DAY]).any()
    got = backend.tables.read_range(
        TABLE, date(2026, 1, 1), date(2026, 1, 31), instruments=["EQ:C"]
    )
    _same(
        got, _reference(backend, TABLE, date(2026, 1, 1), date(2026, 1, 31), instruments=["EQ:C"])
    )


def test_a_column_added_mid_year_is_not_served_as_nulls_for_earlier_days(tmp_path: Path) -> None:
    root = tmp_path / "data"
    backend = LocalBackend(root)
    for i, day in enumerate(date(2026, 1, 1) + timedelta(days=n) for n in range(20)):
        frame = stamped(_rows(i), day, "r1")
        backend.tables.write(TABLE, day, "r1", frame.assign(x=1.5) if i >= 10 else frame)
    backend.tables.build_history(TABLE, [2026])
    early = (date(2026, 1, 1), date(2026, 1, 8))
    late = (date(2026, 1, 12), date(2026, 1, 20))
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, *early, instruments=["EQ:A"])
    assert taken == [] and got is not None and "x" not in got.columns
    _same(got, _reference(backend, TABLE, *early, instruments=["EQ:A"]))
    with _copy_reads(backend) as taken:
        got = backend.tables.read_range(TABLE, *late, instruments=["EQ:A"])
    assert taken == [2026]
    _same(got, _reference(backend, TABLE, *late, instruments=["EQ:A"]))


def test_a_build_removes_the_temp_file_a_crashed_build_left(tmp_path: Path) -> None:
    root = tmp_path / "data"
    backend = _store(root)
    folder = root / "tables" / TABLE / HISTORY
    backend.tables.build_history(TABLE, [2026])
    stray = folder / ".year=2026~dead.parquet.abc.tmp"
    stray.write_bytes(b"half")
    backend.tables.build_history(TABLE, [2026])
    assert not stray.exists()


def test_a_table_without_instrument_ids_has_no_copy(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    day = date(2026, 1, 2)
    frame = stamped([{"key": "k", "value": 1.0}], day, "r1")
    backend.tables.write("catalog/demo", day, "r1", frame)
    with pytest.raises(ValueError, match="instrument_id"):
        backend.tables.build_history("catalog/demo", [2026])


def test_history_size_and_free_bytes_report_the_copy_and_the_volume(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    assert backend.tables.history_size(TABLE) == 0
    backend.tables.build_history(TABLE, [2026])
    assert backend.tables.history_size(TABLE) > 0
    assert backend.tables.free_bytes() > 0
    assert LocalBackend(tmp_path / "absent").tables.free_bytes() > 0  # a store not yet written
    assert MemoryBackend().tables.history_size(TABLE) == 0


def test_the_memory_backend_keeps_no_copy() -> None:
    backend = MemoryBackend()
    day = date(2026, 1, 2)
    backend.tables.write(TABLE, day, "r1", stamped(_rows(1), day, "r1"))
    assert backend.tables.build_history(TABLE, [2026]) == []
    assert backend.tables.read_range(TABLE, day, day) is not None


@pytest.mark.perf
def test_a_one_instrument_year_read_from_the_copy_is_within_budget(tmp_path: Path) -> None:
    n_days, n_ids = 365, 1500
    ids = [f"EQ:{i:05d}" for i in range(n_ids)]
    backend = LocalBackend(tmp_path / "data")
    for i, day in enumerate(date(2025, 1, 1) + timedelta(days=d) for d in range(n_days)):
        rows = [{"instrument_id": s, "a": float(i), "b": i, "c": 0.5, "d": 1.5} for s in ids]
        backend.tables.write(TABLE, day, "r1", stamped(rows, day, "r1"))
    start, end = date(2025, 1, 1), date(2025, 12, 31)
    t0 = time.perf_counter()
    expected = _reference(backend, TABLE, start, end, instruments=["EQ:00777"])
    from_partitions = time.perf_counter() - t0
    backend.tables.build_history(TABLE, [2025])
    reader = LocalBackend(tmp_path / "data")  # cold: nothing parsed or cached
    t0 = time.perf_counter()
    got = reader.tables.read_range(TABLE, start, end, instruments=["EQ:00777"])
    from_copy = time.perf_counter() - t0
    _same(got, expected)
    assert from_copy < 0.05, (
        f"{from_copy * 1000:.0f} ms from the copy, {from_partitions:.2f} s from partitions"
    )
