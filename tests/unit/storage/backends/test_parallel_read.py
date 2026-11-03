"""A long ``read_range`` reads its partitions on a bounded pool (``_map_days``) and returns what
the serial loop returns, in day order; a failed read propagates; ``conform`` skips a table that
is already conformed and rebuilds one that is not."""

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pytest

from algotrade.storage.backends import local
from algotrade.storage.backends.arrow import conform
from algotrade.storage.backends.local import LocalBackend, _map_days
from algotrade.storage.backends.runs.run_selection import StaleSnapshotError
from tests.helpers.stored_frames import stamped

TABLE = "rollups/market/demo@v1"
START = date(2026, 1, 1)


def _days(n: int) -> list[date]:
    return [START + timedelta(days=k) for k in range(n)]


def test_map_days_keeps_day_order_when_pooled() -> None:
    days = _days(local.PARALLEL_FROM * 3)
    assert _map_days(lambda d: d.toordinal(), days) == [d.toordinal() for d in days]


def test_map_days_propagates_the_first_failure() -> None:
    def read(day: date) -> int:
        if day == START + timedelta(days=70):
            raise StaleSnapshotError("gone")
        return 1

    with pytest.raises(StaleSnapshotError):
        _map_days(read, _days(local.PARALLEL_FROM * 2))


def test_pooled_range_equals_the_serial_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalBackend(tmp_path).tables
    days = _days(local.PARALLEL_FROM + 6)
    for k, day in enumerate(days):
        rows = [{"instrument_id": "MKT:US", "value": float(k)}]
        store.write(TABLE, day, "r1", stamped(rows, day, "r1"))
    pooled = store.read_range(TABLE, days[0], days[-1])
    monkeypatch.setattr(local, "READ_WORKERS", 1)
    serial = store.read_range(TABLE, days[0], days[-1])
    assert pooled is not None and serial is not None
    pd.testing.assert_frame_equal(pooled, serial)
    assert list(pooled["value"]) == [float(k) for k in range(len(days))]


def test_conform_returns_a_conformed_table_as_it_is_and_rebuilds_a_pandas_one() -> None:
    frame = pd.DataFrame({"instrument_id": ["EQ:A"]})
    once = conform("bars/1d", pa.Table.from_pandas(frame, preserve_index=False))
    assert conform("bars/1d", once) is once
    assert b"pandas" not in (once.schema.metadata or {})
