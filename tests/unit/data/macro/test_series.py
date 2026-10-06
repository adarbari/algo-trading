"""``data.macro.series``: every partition unioned, the latest stored row per key, and each
observation as a session knew it (its latest vintage on or before the session)."""

from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.data.macro.series import (
    COLUMNS,
    TABLE,
    latest_vintages,
    series_as_of,
    stored_vintages,
)
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

UNRATE, VIX = "MACRO:UNRATE", "IDX:VIX"
BACKFILL, NIGHTLY = date(2026, 10, 5), date(2026, 10, 6)


def row(iid: str, obs: str, vintage: str, value: float | None) -> dict[str, object]:
    return {
        "instrument_id": iid,
        "series": iid.partition(":")[2],
        "obs_date": date.fromisoformat(obs),
        "vintage_date": date.fromisoformat(vintage),
        "value": value,
        "vintage_kind": "alfred" if iid == UNRATE else "lagged",
    }


def at(day: date) -> datetime:
    return datetime(day.year, day.month, day.day, 22, tzinfo=UTC)


def store(*parts: tuple[date, str, list[dict[str, object]]]) -> StoreReader:
    writer = StoreWriter(MemoryBackend())
    for session, run, rows in parts:
        writer.write_table(TABLE, session, run, stamped(rows, session, run, at(session), "fred"))
    return StoreReader(writer._backend)


HISTORY = [
    row(UNRATE, "2008-01-01", "2008-02-01", 4.9),
    row(UNRATE, "2008-01-01", "2008-03-07", 5.0),  # the March revision of January
    row(UNRATE, "2008-02-01", "2008-03-07", 4.8),
    row(VIX, "2008-03-03", "2008-03-03", 26.5),
]


def test_stored_vintages_union_partitions_and_keep_the_latest_stored_row() -> None:
    fix = [row(UNRATE, "2008-02-01", "2008-03-07", 4.9)]  # restated by a later run
    reader = store((BACKFILL, "backfill", HISTORY), (NIGHTLY, "nightly", fix))
    frame = stored_vintages(reader)
    assert len(frame) == 4 and "session_date" not in frame.columns
    assert list(frame["vintage_date"]) == sorted(frame["vintage_date"])
    feb = frame[frame["obs_date"] == date(2008, 2, 1)]
    assert list(feb["value"]) == [4.9]
    assert list(stored_vintages(reader, [VIX])["instrument_id"]) == [VIX]
    before = stored_vintages(reader, as_of=at(BACKFILL))
    assert list(before[before["obs_date"] == date(2008, 2, 1)]["value"]) == [4.8]


def test_nothing_stored_is_an_empty_frame() -> None:
    reader = store()
    assert list(stored_vintages(reader).columns) == COLUMNS
    assert series_as_of(reader, [UNRATE], date(2008, 3, 10), 60).empty


@pytest.mark.parametrize(
    ("session", "expected"),
    [
        (date(2008, 1, 31), {}),  # nothing published yet
        (date(2008, 2, 1), {date(2008, 1, 1): 4.9}),  # the first release
        (date(2008, 3, 6), {date(2008, 1, 1): 4.9}),  # the revision is not out yet
        (date(2008, 3, 7), {date(2008, 1, 1): 5.0, date(2008, 2, 1): 4.8}),
    ],
)
def test_series_as_of_gives_the_latest_vintage_a_session_knew(
    session: date, expected: dict[date, float]
) -> None:
    frame = series_as_of(store((BACKFILL, "backfill", HISTORY)), [UNRATE], session, 60)
    assert dict(zip(frame["obs_date"], frame["value"], strict=True)) == expected
    assert list(frame.columns) == COLUMNS


def test_lookback_bounds_the_observation_dates_and_frames_pivot() -> None:
    reader = store((BACKFILL, "backfill", HISTORY))
    session = date(2008, 3, 7)
    assert list(series_as_of(reader, [UNRATE], session, 30)["obs_date"]) == [date(2008, 2, 1)]
    both = series_as_of(reader, None, date(2008, 3, 10), 60)
    wide = both.pivot(index="obs_date", columns="instrument_id", values="value")
    assert list(wide.columns) == [VIX, UNRATE] and len(wide) == 3
    assert series_as_of(reader, [], session, 0).empty  # lookback 0: the session's own dates
    with pytest.raises(ValueError, match="lookback"):
        series_as_of(reader, [UNRATE], session, -1)


def test_latest_vintages_is_pure() -> None:
    frame = pd.DataFrame(HISTORY)
    known = latest_vintages(frame, date(2008, 3, 7))
    assert list(known["instrument_id"]) == [VIX, UNRATE, UNRATE]
    assert list(known["value"]) == [26.5, 5.0, 4.8]
    assert list(latest_vintages(frame, date(2008, 2, 29))["value"]) == [4.9]
