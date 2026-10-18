"""``data.futures.curves``: the stored snapshots over a range (point in time, by root) and one
root's curve with its annualised roll yield (positive in backwardation)."""

import math
from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.futures.curves import COLUMNS, curve_of, futures_curve
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D = date(2026, 10, 2)


def rows(root: str, prices: list[float | None]) -> list[dict[str, object]]:
    months = [("2026-10", date(2026, 10, 22)), ("2026-11", date(2026, 11, 20))]
    return [
        {"instrument_id": f"FUT:{root}:{m}", "ts": D, "parent_id": f"FUT:{root}", "root": root,
         "contract_month": m, "expiry": e, "price": p}
        for (m, e), p in zip(months, prices, strict=True)
    ]  # fmt: skip


def stored() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    both = [*rows("CL", [70.0, 68.0]), *rows("ZN", [110.0, None])]
    writer.write_table("rates/futures_curve", D, "c", stamped(both, D, "c"))
    return StoreReader(backend)


def test_an_empty_store_has_the_columns_and_no_rows() -> None:
    frame = futures_curve(StoreReader(MemoryBackend()), D, D)
    assert frame.empty and list(frame.columns) == list(COLUMNS)


def test_the_range_read_filters_roots_and_sorts_by_expiry() -> None:
    frame = futures_curve(stored(), D, D)
    assert list(frame["root"]) == ["CL", "CL", "ZN", "ZN"]
    assert list(futures_curve(stored(), D, D, ["ZN"])["root"]) == ["ZN", "ZN"]
    assert futures_curve(stored(), date(2026, 10, 3), date(2026, 10, 5)).empty  # no carry-over


def test_a_read_as_of_before_the_snapshot_was_stored_sees_nothing() -> None:
    before = datetime(2000, 1, 1, tzinfo=UTC)
    assert futures_curve(stored(), D, D, as_of=before).empty


def test_backwardation_has_a_positive_roll_yield_and_unpriced_rows_are_dropped() -> None:
    frame = futures_curve(stored(), D, D)
    cl = curve_of(frame, "CL", D)
    assert list(cl["days"]) == [20.0, 49.0] and cl["roll_yield"].iloc[0] == 0.0
    assert cl["roll_yield"].iloc[1] == pytest.approx(math.log(70.0 / 68.0) / (29 / 365))
    assert len(curve_of(frame, "ZN", D)) == 1  # the unpriced month is not on the curve
    assert curve_of(frame, "XX", D).empty and isinstance(curve_of(frame, "XX", D), pd.DataFrame)
