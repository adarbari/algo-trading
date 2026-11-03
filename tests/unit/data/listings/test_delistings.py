"""``read_delistings`` / ``known_by`` / ``convention`` and ``delisted_listings`` on synthetic
frames (ADR 0087): the snapshot written on or before a session, the replacement returns, the final
venue of an id with several listings."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.delistings import TABLE, convention, known_by, read_delistings
from algotrade.data.listings.universe import delisted_by, delisted_listings
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped


def _rows(day: date, known: date) -> list[dict[str, object]]:
    return [
        {"instrument_id": "EQ:A", "ts": pd.Timestamp(day, tz="UTC"), "known_from": known,
         "last_session": day, "last_close": 1.0, "reason": "UNKNOWN",
         "terminal_basis": "ZERO_UNKNOWN", "delisting_return": 0.0}
    ]  # fmt: skip


def test_convention_by_reason_and_final_exchange() -> None:
    assert convention("ACQUIRED", "NASDAQ") == ("ZERO_ACQUIRED", 0.0)
    assert convention("BANKRUPTCY", "NASDAQ") == ("REPLACEMENT", -0.55)
    assert convention("STANDARDS", "NASDAQ") == ("REPLACEMENT", -0.55)
    assert convention("BANKRUPTCY", "NYSE") == ("REPLACEMENT", -0.30)
    assert convention("STANDARDS", "AMEX") == ("REPLACEMENT", -0.30)
    assert convention("BANKRUPTCY", None) == ("REPLACEMENT", -0.30)
    assert convention("VOLUNTARY", "NASDAQ") == ("ZERO_UNKNOWN", 0.0)
    assert convention("UNKNOWN", "NYSE") == ("ZERO_UNKNOWN", 0.0)


def test_the_read_takes_the_latest_snapshot_on_or_before_the_write_session() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day in (date(2026, 10, 10), date(2026, 10, 24)):
        frame = stamped(_rows(date(2020, 1, 2), date(2020, 1, 3)), day, f"r-{day}")
        writer.write_table(TABLE, day, f"r-{day}", frame)
    reader = StoreReader(backend)
    assert read_delistings(reader)[1] == date(2026, 10, 24)
    assert read_delistings(reader, date(2026, 10, 23))[1] == date(2026, 10, 10)
    with pytest.raises(MissingDataError, match="delistings"):
        read_delistings(reader, date(2026, 10, 9))  # a later snapshot never stands in
    with pytest.raises(MissingDataError, match="delistings"):
        read_delistings(StoreReader(MemoryBackend()))


def test_known_by_keeps_the_rows_known_on_or_before_the_session() -> None:
    frame = pd.DataFrame({"known_from": [date(2020, 1, 3), date(2020, 1, 6)], "x": [1, 2]})
    assert list(known_by(frame, date(2020, 1, 2))["x"]) == []
    assert list(known_by(frame, date(2020, 1, 3))["x"]) == [1]
    assert list(known_by(frame, date(2020, 1, 6))["x"]) == [1, 2]


def _listing_store(rows: list[tuple]) -> StoreReader:  # type: ignore[type-arg]
    frame = pd.DataFrame(
        rows,
        columns=[
            "instrument_id",
            "ticker",
            "exchange",
            "security_type",
            "cik",
            "start_date",
            "end_date",
        ],
    )
    frame = frame.assign(
        source="tiingo", asset_type="Stock", ts=pd.Timestamp("2026-10-05", tz="UTC")
    )
    for column in ("start_date", "end_date"):
        frame[column] = pd.to_datetime(frame[column]).dt.date
    backend = MemoryBackend()
    day = date(2026, 10, 5)
    StoreWriter(backend).write_table(
        "instruments/listing_history", day, "r", stamped(frame.to_dict("records"), day, "r")
    )
    return StoreReader(backend)


def test_delisted_listings_gives_the_final_venue_and_the_latest_cik() -> None:
    reader = _listing_store(
        [
            ("EQ:A", "AAA", "NASDAQ", "COMMON_STOCK", "0001", "2000-01-03", "2010-01-04"),
            ("EQ:A", "AAB", "NYSE", "COMMON_STOCK", None, "2010-01-11", "2015-01-05"),
            ("EQ:B", "BBB", "NYSE", "ETF", "0002", "2000-01-03", "2020-01-02"),  # after the session
            ("EQ:C", "CCC", "NASDAQ", "COMMON_STOCK", "0003", "2000-01-03", None),  # open
        ]
    )
    gone, snapshot = delisted_listings(reader, date(2016, 1, 4))
    assert snapshot == date(2026, 10, 5) and list(gone["instrument_id"]) == ["EQ:A"]
    row = gone.iloc[0]  # a ticker change 4 sessions later is no delisting of its own
    assert (row["last_day"], row["exchange"], row["cik"]) == (date(2015, 1, 5), "NYSE", "0001")
    assert bool(row["final"])


def test_a_delisted_and_relisted_id_has_a_row_per_gap() -> None:
    reader = _listing_store(
        [
            ("EQ:R", "RRR", "NASDAQ", "COMMON_STOCK", "0007", "2000-01-03", "2010-01-04"),
            ("EQ:R", "RRR", "NYSE", "COMMON_STOCK", None, "2010-01-20", "2014-01-06"),  # gap
            ("EQ:R", "RRRN", "NYSE", "COMMON_STOCK", None, "2014-01-08", "2018-01-02"),  # 1 session
            ("EQ:S", "SSS", "NYSE", "COMMON_STOCK", "0008", "2000-01-03", "2012-01-03"),
            ("EQ:S", "SSS", "NYSE", "COMMON_STOCK", "0008", "2013-01-02", None),  # relisted, open
        ]
    )
    gone, _ = delisted_listings(reader, date(2030, 1, 1))
    got = [(r.instrument_id, r.last_day, r.exchange, r.final) for r in gone.itertuples()]
    assert got == [
        (
            "EQ:R",
            date(2010, 1, 4),
            "NASDAQ",
            False,
        ),  # next starts the 11th session after: a real gap
        ("EQ:R", date(2018, 1, 2), "NYSE", True),  # 2014-01-06 -> 01-08 is a ticker change
        ("EQ:S", date(2012, 1, 3), "NYSE", False),  # open again: not final
    ]
    assert gone.loc[gone["last_day"] == date(2010, 1, 4), "cik"].item() == "0007"
    assert gone.loc[gone["last_day"] == date(2018, 1, 2), "cik"].item() == "0007"
    by = delisted_by(reader, date(2030, 1, 1))
    assert by == {"EQ:R": date(2018, 1, 2)}  # the outcomes' rule: only the last stretch
    assert delisted_by(reader, date(2016, 1, 4)) == {}  # R was open in 2016, S relisted


def test_a_listing_nested_in_an_earlier_one_never_ends_the_stretch() -> None:
    reader = _listing_store(
        [
            ("EQ:N", "AAA", "NASDAQ", "COMMON_STOCK", "0001", "2000-01-03", "2010-01-04"),
            ("EQ:N", "AAB", "NYSE", "COMMON_STOCK", None, "2001-01-02", "2005-01-04"),  # nested
        ]
    )
    gone, _ = delisted_listings(reader, date(2030, 1, 1))
    assert [(r.last_day, r.exchange, r.final) for r in gone.itertuples()] == [
        (date(2010, 1, 4), "NASDAQ", True)  # the one that ended last, not the nested one
    ]
    assert delisted_by(reader, date(2030, 1, 1)) == {"EQ:N": date(2010, 1, 4)}
