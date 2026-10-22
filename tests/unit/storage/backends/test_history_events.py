"""The history copy of an events table (ADR 0060 amendment 2026-10-22): a per-instrument read over
all time (``data.events.read_events``) from the copy equals the read of the partitions, point in
time included (a restated day, a second run, a row known later), a rewritten partition makes its
year fall back, and an instrument filter decodes only the row groups that hold the id.

Events are partitioned by day, so an all-time read of one name opens one file per
partition (``events/fund_nav``: 5,737 for 0 rows); the copy turns that into one file per year."""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq
import pytest
from pandas.testing import assert_frame_equal

from algotrade.data.events import ALL_TIME, read_events
from algotrade.storage.backends import history
from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

TABLE = "events/fund_nav"
LATER = T0 + timedelta(hours=1)
FUTURE = datetime(2200, 1, 1, tzinfo=UTC)
FIRST = date(2025, 12, 20)
FUNDS = [f"EQ:F{i}" for i in range(6)]


def _rows(day: date, nav: float, ids: list[str] = FUNDS) -> pd.DataFrame:
    ts = pd.Timestamp(day, tz="UTC")
    rows = [
        {"instrument_id": s, "series": "X", "ts": ts, "nav": nav + k} for k, s in enumerate(ids)
    ]
    return pd.DataFrame(rows).assign(known_from=day + timedelta(days=1))


def _store(root: Path) -> LocalBackend:
    """40 ingest days over a year boundary; every third day restated by a second run (one fund's
    NAV corrected), one day holding a row known only later (a later ``known_from``)."""
    backend = LocalBackend(root)
    for i in range(40):
        day = FIRST + timedelta(days=i)
        frame = stamped(_rows(day, float(i)).to_dict("records"), day, "r1").assign(
            known_from=day + timedelta(days=1)
        )
        backend.tables.write(TABLE, day, "r1", frame)
        if i % 3 == 0:
            fixed = frame.iloc[:1].assign(nav=-1.0, run_id="r2", knowledge_ts=pd.Timestamp(LATER))
            backend.tables.write(TABLE, day, "r2", fixed)
        if i == 7:
            late = frame.iloc[1:2].assign(
                run_id="r3", nav=-7.0, knowledge_ts=pd.Timestamp(LATER), known_from=date(2026, 2, 1)
            )
            backend.tables.write(TABLE, day, "r3", late)
    return backend


def _build(backend: LocalBackend) -> None:
    assert backend.tables.build_history(TABLE, [2025, 2026]) == [2025, 2026]


@contextmanager
def _reads(backend: LocalBackend) -> Iterator[dict[str, list[Any]]]:
    """The years ``read_range`` took from the copy, and the row groups decoded from it."""
    seen: dict[str, list[Any]] = {"years": [], "groups": []}
    real_year = backend.tables.history.read_year
    real_groups = pq.ParquetFile.read_row_groups

    def year(table: str, y: int, *rest: Any) -> Any:
        seen["years"].append(y)
        return real_year(table, y, *rest)

    def groups(self: pq.ParquetFile, row_groups: list[int], *a: Any, **k: Any) -> Any:
        seen["groups"].append(list(row_groups))
        return real_groups(self, row_groups, *a, **k)

    backend.tables.history.read_year = year  # type: ignore[method-assign, assignment]
    pq.ParquetFile.read_row_groups = groups  # type: ignore[method-assign, assignment]
    try:
        yield seen
    finally:
        backend.tables.history.read_year = real_year  # type: ignore[method-assign, assignment]
        pq.ParquetFile.read_row_groups = real_groups  # type: ignore[method-assign]


def _events(backend: LocalBackend, ids: list[str] | None, through: date | None, **q: Any) -> Any:
    return read_events(StoreReader(backend), TABLE, *ALL_TIME, ids, through=through, **q).frame


@pytest.mark.parametrize("ids", [None, ["EQ:F1"], ["EQ:F4", "EQ:F0"], ["EQ:NOPE"]])
@pytest.mark.parametrize("through", [None, date(2026, 1, 3), date(2026, 1, 20), date(2026, 3, 1)])
def test_an_events_read_through_the_copy_equals_the_partitions(
    tmp_path: Path, ids: list[str] | None, through: date | None
) -> None:
    backend = _store(tmp_path / "data")
    _build(backend)
    with _reads(backend) as seen:
        got = _events(backend, ids, through)
    expected = _events(backend, ids, through, as_of=FUTURE)  # the partition path
    assert_frame_equal(got, expected)
    if ids is not None:
        assert sorted(seen["years"]) == [2025, 2026]


def test_a_restated_day_and_a_second_run_are_what_the_copy_serves(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    _build(backend)
    frame = _events(backend, ["EQ:F0"], None)
    corrected = frame[frame["ts"] == pd.Timestamp(FIRST, tz="UTC")]
    assert list(corrected["nav"]) == [-1.0] and list(corrected["run_id"]) == ["r2"]
    day7 = pd.Timestamp(FIRST + timedelta(days=7), tz="UTC")

    def nav_on_day7(through: date | None) -> list[float]:
        got = _events(backend, ["EQ:F1"], through)
        return list(got[got["ts"] == day7]["nav"])

    assert (
        nav_on_day7(date(2026, 1, 20)) == []
    )  # the table keeps the latest run of a day (snapshot): its row is not known yet
    assert nav_on_day7(date(2026, 2, 1)) == [-7.0]
    assert nav_on_day7(None) == [-7.0]


def test_a_rewritten_partition_makes_only_its_year_fall_back(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    _build(backend)
    day = date(2026, 1, 5)
    fix = stamped(_rows(day, 99.0).to_dict("records"), day, "r9", LATER).assign(known_from=day)
    backend.tables.write(TABLE, day, "r9", fix)
    with _reads(backend) as seen:
        got = _events(backend, ["EQ:F2"], None)
    assert seen["years"] == [2025]  # 2026 reads its partitions
    assert_frame_equal(got, _events(backend, ["EQ:F2"], None, as_of=FUTURE))


def test_a_new_ingest_day_makes_the_current_year_fall_back(tmp_path: Path) -> None:
    backend = _store(tmp_path / "data")
    _build(backend)
    day = date(2026, 3, 1)
    backend.tables.write(TABLE, day, "r1", stamped(_rows(day, 1.0).to_dict("records"), day, "r1"))
    with _reads(backend) as seen:
        got = _events(backend, ["EQ:F2"], None)
    assert seen["years"] == [2025]
    assert_frame_equal(got, _events(backend, ["EQ:F2"], None, as_of=FUTURE))


def test_an_instrument_filter_decodes_only_the_row_groups_holding_the_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(history, "ROW_GROUP_ROWS", 12)  # a fund's rows span one or two groups
    backend = _store(tmp_path / "data")
    _build(backend)
    folder = tmp_path / "data" / "tables" / TABLE / history.HISTORY
    files = sorted(folder.glob("year=*.parquet"))
    assert len(files) == 2  # 40 partitions: two files, not 40+
    total = {f.name[:9]: pq.ParquetFile(f).metadata.num_row_groups for f in files}
    assert all(n > 3 for n in total.values())
    with _reads(backend) as seen:
        _events(backend, ["EQ:F5"], None)
    assert len(seen["groups"]) == 2  # one read per year file
    assert all(0 < len(g) <= 3 for g in seen["groups"]), seen["groups"]
    assert sum(len(g) for g in seen["groups"]) < sum(total.values()) / 2
