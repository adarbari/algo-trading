"""Stored rollup rows: one instrument's latest row, a range for some instruments, the read
path of expression features (only the columns asked for, a column a partition lacks as null,
nothing when nothing is stored) and one session's group fields of a market's row."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.prices import adjusted_bars
from algotrade.data.rollups import feature_rows, group_view, rollup_row, rollup_rows
from tests.helpers.rollup_store import store, write_rows
from tests.helpers.stored_frames import stamped

TABLE = "rollups/instrument/price_stats@v2"
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


def test_feature_rows_read_only_the_columns_asked_for() -> None:
    writer, reader = store()
    demo = "rollups/instrument/demo@v1"
    write_rows(writer, demo, D1, [{"instrument_id": "EQ:B", "a": 1.0, "b": 2.0}])
    write_rows(writer, demo, D2, [{"instrument_id": "EQ:A", "b": 3.0}])
    rows = feature_rows(reader, demo, {"a"}, D1, D2)
    assert rows is not None
    assert list(rows.columns) == ["session_date", "instrument_id", "a"]
    assert rows["session_date"].tolist() == [D1, D2] and rows["a"].isna().tolist() == [False, True]
    assert feature_rows(reader, demo, set(), D1, D1).columns.tolist() == [  # type: ignore[union-attr]
        "session_date", "instrument_id",
    ]  # fmt: skip
    assert feature_rows(reader, "rollups/instrument/none@v1", {"a"}, D1, D2) is None


def test_group_view_reads_exactly_the_sessions_partition_for_the_ids() -> None:
    writer, reader = store()
    market = "rollups/market/breadth@v1"
    write_rows(writer, market, D1, [{"instrument_id": "MKT:US", "share": 0.4, "n": 10}])
    fields = ["market.breadth@v1.share", "market.other@v1.x"]
    frame, missing = group_view(reader, D1, fields, ["MKT:US"])
    assert frame.to_dict("list") == {"instrument_id": ["MKT:US"], "market.breadth@v1.share": [0.4]}
    assert missing == ("rollups/market/other@v1",)
    later, gone = group_view(reader, D2, fields[:1], ["MKT:US"])  # never the older partition
    assert list(later.columns) == ["instrument_id"] and gone == (market,)
    with pytest.raises(ValueError, match="not a feature group field"):
        group_view(reader, D1, ["instrument.symbol"], ["MKT:US"])
