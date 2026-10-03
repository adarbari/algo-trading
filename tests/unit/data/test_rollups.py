from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.prices import adjusted_bars
from algotrade.data.rollups import rollup_row, rollup_rows
from tests.helpers.rollup_store import store
from tests.helpers.stored_frames import stamped

TABLE = "rollups/instrument/price_stats@v1"
D1, D2 = date(2026, 9, 30), date(2026, 10, 1)


def test_rollup_row_is_the_latest_partition_on_or_before() -> None:
    writer, reader = store()
    for day, close in ((D1, 1.0), (D2, 2.0)):
        rows = [{"instrument_id": "EQ:A", "close": close}, {"instrument_id": "EQ:B", "close": 9.0}]
        writer.write_table(TABLE, day, f"r-{day}", stamped(rows, day, f"r-{day}"))
    assert rollup_row(reader, TABLE, "EQ:A") == (D2, {"instrument_id": "EQ:A", "close": 2.0})
    assert rollup_row(reader, TABLE, "EQ:A", D1) == (D1, {"instrument_id": "EQ:A", "close": 1.0})
    assert rollup_row(reader, TABLE, "EQ:A", date(2026, 9, 1)) is None  # before the first
    assert rollup_row(reader, TABLE, "EQ:C") is None
    only_a = rollup_rows(reader, TABLE, D1, D2, instruments=["EQ:A"])
    assert only_a is not None and list(only_a["close"]) == [1.0, 2.0]


def test_adjusted_bars_rejects_an_unknown_adjustment() -> None:
    _, reader = store()
    with pytest.raises(ConfigurationError, match="price adjustment"):
        adjusted_bars(reader, "1d", D1, D2, adjustment="dividends_only")
