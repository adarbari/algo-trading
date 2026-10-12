"""``purge_superseded``: the runs a restating run supersedes are deleted, files included, on
every backend; nothing a read can still see is touched (ADR 0066: an erase must remove the
data, not only hide it behind a newer run)."""

from collections.abc import Callable, Iterator
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.interfaces import Backend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import T0, stamped

DAY = date(2026, 10, 2)
TABLE = "events/dividend"


@pytest.fixture(params=["memory", "local"])
def backend(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Backend]:
    factories: dict[str, Callable[[], Backend]] = {
        "memory": MemoryBackend,
        "local": lambda: LocalBackend(tmp_path / "data"),
    }
    yield factories[request.param]()


def put(backend: Backend, run: str, iid: str, hours: int, restates: bool = False) -> None:
    rows: list[dict[str, object]] = [
        {"instrument_id": iid, "ts": pd.Timestamp(DAY, tz="UTC"), "cash_amount": 1.0}
    ]
    frame = stamped(rows, DAY, run, T0 + timedelta(hours=hours))
    StoreWriter(backend).write_table(TABLE, DAY, run, frame, restates=restates)


def ids(backend: Backend) -> list[str]:
    frame = backend.tables.read(TABLE, DAY)
    assert frame is not None
    return sorted(frame["instrument_id"])


def files(tmp_path: Path) -> list[str]:
    return sorted(p.name for p in (tmp_path / "data").rglob("*.parquet"))


def test_runs_before_the_latest_restating_run_are_deleted(backend: Backend, tmp_path: Path) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "r2", "EQ:B", 1)
    put(backend, "rewrite", "EQ:A", 2, restates=True)
    put(backend, "later", "EQ:C", 3)
    assert backend.tables.purge_superseded(TABLE, DAY) == 2
    assert ids(backend) == ["EQ:A", "EQ:C"]  # the view is unchanged
    if isinstance(backend, LocalBackend):
        assert files(tmp_path) == ["run=later.parquet", "run=rewrite.parquet"]  # r1, r2 gone


def test_it_is_idempotent_and_leaves_a_partition_without_a_restating_run(
    backend: Backend,
) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "r2", "EQ:B", 1)
    assert backend.tables.purge_superseded(TABLE, DAY) == 0  # nothing restates: all are read
    put(backend, "rewrite", "EQ:A", 2, restates=True)
    assert backend.tables.purge_superseded(TABLE, DAY) == 2
    assert backend.tables.purge_superseded(TABLE, DAY) == 0
    assert backend.tables.purge_superseded(TABLE, date(2020, 1, 1)) == 0  # no such partition


def test_it_moves_the_published_sequence_so_caches_see_it(backend: Backend) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "rewrite", "EQ:A", 1, restates=True)
    before = backend.tables.visible_seq()
    assert backend.tables.purge_superseded(TABLE, DAY) == 1
    assert backend.tables.visible_seq() > before
    assert backend.tables.purge_superseded(TABLE, DAY) == 0
    assert backend.tables.visible_seq() == before + 1


def test_a_partition_a_pending_run_wrote_to_is_left_for_a_later_pass(backend: Backend) -> None:
    put(backend, "r1", "EQ:A", 0)
    put(backend, "rewrite", "EQ:A", 1, restates=True)
    rows: list[dict[str, object]] = [
        {"instrument_id": "EQ:Z", "ts": pd.Timestamp(DAY, tz="UTC"), "cash_amount": 1.0}
    ]
    backend.tables.write(
        TABLE, DAY, "busy", stamped(rows, DAY, "busy", T0 + timedelta(hours=5)), pending=True
    )
    assert backend.tables.purge_superseded(TABLE, DAY) == 0
    backend.tables.abort_run("busy")
    assert backend.tables.purge_superseded(TABLE, DAY) == 1
