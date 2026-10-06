"""Stored rollup rows: one instrument's latest row, a range for some instruments, the read
path of expression features (only the columns asked for, a column a partition lacks as null,
nothing when nothing is stored) and a market's row's group fields for one session or a range."""

from datetime import date

import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data.prices import adjusted_bars
from algotrade.data.rollups import (
    feature_rows,
    group_rows,
    group_view,
    latest_rollup,
    rollup_row,
    rollup_rows,
)
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


def test_latest_rollup_is_the_newest_partition_on_or_before_with_its_rows() -> None:
    writer, reader = store()
    for day, close in ((D1, 1.0), (D2, 2.0)):
        rows = [{"instrument_id": "EQ:A", "close": close}, {"instrument_id": "EQ:B", "close": 9.0}]
        writer.write_table(TABLE, day, f"r-{day}", stamped(rows, day, f"r-{day}"))
    day, frame = latest_rollup(reader, TABLE, date(2026, 10, 5)) or (None, None)
    assert day == D2 and list(frame["close"]) == [2.0, 9.0]  # type: ignore[index]
    assert "run_id" not in frame.columns  # type: ignore[union-attr]  # stamps dropped
    day, frame = latest_rollup(reader, TABLE, D1, ["EQ:B"]) or (None, None)
    assert day == D1 and list(frame["instrument_id"]) == ["EQ:B"]  # type: ignore[index]
    assert latest_rollup(reader, TABLE, date(2026, 9, 1)) is None  # a later partition is not used
    assert latest_rollup(reader, "rollups/instrument/none@v1", D2) is None
    assert latest_rollup(reader, TABLE, D2, ["EQ:ZZ"]) is None  # none of the ids has a row


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


def test_group_rows_reads_every_stored_session_of_the_range() -> None:
    writer, reader = store()
    breadth, trend = "rollups/market/breadth@v1", "rollups/market/trend@v1"
    write_rows(writer, breadth, D1, [{"instrument_id": "MKT:US", "share": 0.4}])
    write_rows(writer, breadth, D2, [{"instrument_id": "MKT:US", "share": None}])
    write_rows(writer, trend, D2, [{"instrument_id": "MKT:US", "slope": 1.5}])
    fields = ["market.breadth@v1.share", "market.trend@v1.slope", "market.other@v1.x"]
    frame, missing = group_rows(reader, D1, D2, fields, ["MKT:US"])
    assert list(frame["session_date"]) == [D1, D2]  # no row for a session: absent, not null
    assert frame["market.breadth@v1.share"].iloc[0] == 0.4
    assert frame["market.breadth@v1.share"].isna().iloc[1]  # a stored null stays null
    assert (
        frame["market.trend@v1.slope"].isna().iloc[0]
        and frame["market.trend@v1.slope"].iloc[1] == 1.5
    )
    assert missing == ("rollups/market/other@v1",)
    empty, gone = group_rows(reader, D1, D2, fields[2:], ["MKT:US"])
    assert empty.empty and list(empty.columns) == ["session_date", "instrument_id"]
    assert gone == ("rollups/market/other@v1",)
    with pytest.raises(ValueError, match="not a feature group field"):
        group_rows(reader, D1, D2, ["instrument.symbol"], ["MKT:US"])
