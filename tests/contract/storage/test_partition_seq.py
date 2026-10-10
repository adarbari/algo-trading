"""Storage contract, partition stamps (ADR 0063): ``partition_seq`` gives each committed
partition in a range the highest commit sequence of its index, so a reader can tell a partition
it read has not changed without reading it."""

from collections.abc import Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
TABLE = "rollups/instrument/a@v1"
LIVE = "live/option_quotes"
AT = T0 + timedelta(minutes=30)


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    yield MemoryBackend() if request.param == "memory" else LocalBackend(tmp_path / "data")


def frame(day: date, run: str, v: float = 1.0) -> pd.DataFrame:
    return stamped([{"instrument_id": "EQ:A", "value": v}], day, run)


def publish(backend: Backend, run: str, *days: date, restates: bool = False) -> int:
    for day in days:
        backend.tables.write(TABLE, day, run, frame(day, run), restates=restates, pending=True)
    backend.tables.commit_run(run, AT)
    return backend.tables.visible_seq()


def test_a_commit_stamps_its_partitions_with_the_new_sequence(backend: Backend) -> None:
    first = publish(backend, "r1", D1, D2)
    second = publish(backend, "r2", D2, D3)
    stamps = backend.tables.partition_seq(TABLE, D1, D3)
    assert stamps == {D1: first, D2: second, D3: second}
    assert first < second


def test_the_range_is_inclusive_and_other_tables_are_not_included(backend: Backend) -> None:
    publish(backend, "r1", D1, D2, D3)
    backend.tables.write("rollups/instrument/b@v1", D2, "r1", frame(D2, "r1"), pending=True)
    backend.tables.commit_run("r1", AT)
    assert sorted(backend.tables.partition_seq(TABLE, D2, D3)) == [D2, D3]
    assert backend.tables.partition_seq(TABLE, D3 + timedelta(1), D3 + timedelta(5)) == {}
    assert backend.tables.partition_seq("rollups/instrument/none@v1", D1, D3) == {}


def test_a_rerun_of_the_same_run_id_raises_the_stamp(backend: Backend) -> None:
    first = publish(backend, "r1", D1)
    again = publish(backend, "r1", D1)  # the same (table, date, run) replaced
    assert backend.tables.partition_seq(TABLE, D1, D1) == {D1: again} and first < again


def test_a_restating_run_raises_the_stamp(backend: Backend) -> None:
    first = publish(backend, "r1", D1, D2)
    restated = publish(backend, "r2", D1, restates=True)
    assert backend.tables.partition_seq(TABLE, D1, D2) == {D1: restated, D2: first}


def test_pending_writes_are_invisible_to_the_stamp(backend: Backend) -> None:
    backend.tables.write(TABLE, D1, "open", frame(D1, "open"), pending=True)
    assert backend.tables.partition_seq(TABLE, D1, D3) == {}
    first = publish(backend, "r1", D2)
    backend.tables.write(TABLE, D2, "open", frame(D2, "open"), pending=True)
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D2: first}
    assert StoreReader(backend).partition_seq(TABLE, D1, D3) == {D2: first}
    backend.tables.abort_run("open")
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D2: first}


def test_a_purge_removes_the_date_from_the_stamps(backend: Backend) -> None:
    for day in (D1, D2):
        row = {
            "instrument_id": f"OPT:{day}", "underlying_id": "EQ:A", "expiry": day,
            "ts": pd.Timestamp(day, tz="UTC"), "right": "C", "strike": 100.0, "bid": 1.0,
        }  # fmt: skip
        backend.tables.write(LIVE, day, "r1", stamped([row], day, "r1"), pending=True)
    backend.tables.commit_run("r1", AT)
    assert sorted(backend.tables.partition_seq(LIVE, D1, D3)) == [D1, D2]
    assert backend.tables.purge_before(LIVE, D2) == 1
    assert sorted(backend.tables.partition_seq(LIVE, D1, D3)) == [D2]


def test_a_direct_write_without_a_sequence_counts_zero(backend: Backend) -> None:
    backend.tables.write(TABLE, D1, "direct", frame(D1, "direct"))  # not pending: no commit
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D1: 0}
    later = publish(backend, "r1", D1)  # a commit on top of it
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D1: later}


def test_an_indexed_commit_that_is_not_published_is_not_stamped(
    backend: Backend, tmp_path: Path
) -> None:
    """A commit in flight (or crashed before publishing) has indexed its entry but not yet
    raised ``visible_seq``: no read could see it, so the stamp must not name it."""
    first = publish(backend, "r1", D1)
    publish(backend, "r2", D1, D2)
    if isinstance(backend, LocalBackend):
        (backend.tables.commits.base / "seq").write_text(str(first))  # roll the publish back
    else:
        assert isinstance(backend, MemoryBackend)
        backend.tables._seq = first  # type: ignore[attr-defined]
    assert backend.tables.visible_seq() == first
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D1: first, D2: 0}  # r2's entries unseen


def test_an_empty_frame_commit_lists_the_partition_with_stamp_zero_on_any_backend(
    backend: Backend,
) -> None:
    empty = frame(D1, "r1").iloc[0:0]
    backend.tables.write(TABLE, D1, "r1", empty, pending=True)
    backend.tables.commit_run("r1", AT)
    assert backend.tables.partition_seq(TABLE, D1, D3) == {D1: 0}  # listed by dates() too, no entry
