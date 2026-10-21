"""Storage contract, the history copy under a pinned read (ADR 0077 decision 2): a copy serves a
read at ``upto`` only when it was built at or below ``upto`` and every requested day still has
the signature it recorded; otherwise the partitions answer, as of ``upto``. The copy is local to
``LocalBackend``; the memory backend has none, so its pinned reads are the partition reads."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from algotrade.storage.backends.local import LocalBackend
from algotrade.storage.tables.readers import StoreReader
from tests.helpers.stored_frames import T0, stamped

D1, D2, D3 = date(2026, 10, 1), date(2026, 10, 2), date(2026, 10, 3)
TABLE = "rollups/instrument/a@v1"
AT = T0 + timedelta(minutes=30)
YEAR = 2026


def commit(backend: LocalBackend, run: str, day: date, value: float) -> int:
    frame = stamped([{"instrument_id": "EQ:A", "value": value}], day, run)
    backend.tables.write(TABLE, day, run, frame, pending=True)
    backend.tables.commit_run(run, AT)
    return backend.tables.visible_seq()


def values(frame: pd.DataFrame | None) -> list[float]:
    assert frame is not None
    return [float(v) for v in frame["value"]]


def test_a_copy_built_after_the_pin_is_refused_and_the_partitions_answer(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    x = commit(backend, "r1", D1, 1.0)
    commit(backend, "r2", D2, 2.0)  # a later session, inside the copy built next
    backend.tables.build_history(TABLE, [YEAR])
    assert backend.tables.history.usable(TABLE, D1, D3, True, x) == {}
    assert YEAR in backend.tables.history.usable(TABLE, D1, D3, True, x + 1)
    found = StoreReader(backend).pinned(x).table_range(TABLE, D1, D3, instruments=["EQ:A"])
    assert values(found) == [1.0]  # never the later session the copy holds


def test_a_restated_older_partition_is_not_read_from_a_copy_built_before_it(
    tmp_path: Path,
) -> None:
    backend = LocalBackend(tmp_path / "data")
    commit(backend, "r1", D1, 1.0)
    x = commit(backend, "r1", D2, 2.0)
    backend.tables.build_history(TABLE, [YEAR])
    backend.tables.pin("release-a", x)
    commit(backend, "r1", D1, 9.0)  # D1 recommitted after the copy and after the pin
    pinned = StoreReader(backend).pinned(x)
    assert backend.tables.history.usable(TABLE, D1, D2, True, x) == {}  # signature moved
    assert values(pinned.table_range(TABLE, D1, D2, instruments=["EQ:A"])) == [1.0, 2.0]
    live = StoreReader(backend).table_range(TABLE, D1, D2, instruments=["EQ:A"])
    assert values(live) == [9.0, 2.0]


def test_an_unchanged_copy_at_or_below_the_pin_serves_the_pinned_read(tmp_path: Path) -> None:
    backend = LocalBackend(tmp_path / "data")
    commit(backend, "r1", D1, 1.0)
    x = commit(backend, "r1", D2, 2.0)
    backend.tables.build_history(TABLE, [YEAR])
    commit(backend, "r2", D3, 3.0)  # a later session, outside the days asked for
    assert YEAR in backend.tables.history.usable(TABLE, D1, D2, True, x)
    pinned = StoreReader(backend).pinned(x)
    assert values(pinned.table_range(TABLE, D1, D2, instruments=["EQ:A"])) == [1.0, 2.0]
