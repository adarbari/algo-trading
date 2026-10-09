"""``universe_asof`` on synthetic listing frames (ADR 0013 rule at S, ADR 0018 ids)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.universe import COLUMNS, listed_asof, universe_asof
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter

S = date(2012, 6, 1)


def _listings() -> pd.DataFrame:
    rows = [
        # id, ticker, exchange, asset_type, start, end
        ("EQ:TIINGO:A", "AAA", "NYSE", "Stock", "2000-01-03", None),  # member
        ("EQ:TIINGO:B", "BBB", "NYSE", "Stock", "2000-01-03", None),  # NYSE non-member: out
        ("EQ:TIINGO:C", "CCC", "NASDAQ", "Stock", "2005-01-03", "2013-01-02"),  # in, delisted
        ("EQ:TIINGO:D", "DDD", "NYSE", "ETF", "2008-01-02", None),  # ETF: in
        ("EQ:TIINGO:E", "EEE", "NASDAQ", "Stock", "2013-01-02", None),  # not yet listed
        ("EQ:TIINGO:F", "FFF", "NASDAQ", "Stock", "2001-01-02", "2012-05-31"),  # gone
        (None, "GGG", "NASDAQ", "Stock", "2001-01-02", None),  # no trusted id yet
        ("EQ:TIINGO:OLD", "RCY", "NASDAQ", "Stock", "2005-01-03", "2010-12-31"),  # recycled
        ("EQ:TIINGO:NEW", "RCY", "NASDAQ", "Stock", "2011-03-01", None),  # same ticker
    ]
    frame = pd.DataFrame(
        rows,
        columns=["instrument_id", "ticker", "exchange", "asset_type", "start_date", "end_date"],
    )
    for column in ("start_date", "end_date"):
        frame[column] = pd.to_datetime(frame[column])
    return frame


def test_listing_window_membership_and_etf_rules() -> None:
    out = listed_asof(_listings(), S, {"AAA"})
    assert list(out.instruments["ticker"]) == ["AAA", "CCC", "DDD", "RCY"]
    assert list(out.instruments["instrument_id"]) == [
        "EQ:TIINGO:A", "EQ:TIINGO:C", "EQ:TIINGO:D", "EQ:TIINGO:NEW",
    ]  # fmt: skip
    assert out.without_id == 1  # GGG


def test_a_recycled_ticker_is_the_listing_alive_on_the_session() -> None:
    early = listed_asof(_listings(), date(2008, 1, 2), set()).instruments
    late = listed_asof(_listings(), S, set()).instruments
    assert list(early.loc[early["ticker"] == "RCY", "instrument_id"]) == ["EQ:TIINGO:OLD"]
    assert list(late.loc[late["ticker"] == "RCY", "instrument_id"]) == ["EQ:TIINGO:NEW"]


def test_the_boundary_days_are_inside_the_window() -> None:
    last = listed_asof(_listings(), date(2012, 5, 31), set()).instruments
    after = listed_asof(_listings(), date(2012, 6, 1), set()).instruments
    assert "FFF" in set(last["ticker"]) and "FFF" not in set(after["ticker"])


def test_end_date_is_not_exposed_as_a_column() -> None:
    out = listed_asof(_listings(), S, {"AAA"}).instruments
    assert list(out.columns) == COLUMNS and "end_date" not in out.columns


def test_universe_asof_reads_the_latest_snapshot_and_says_which() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    frame = _listings().assign(source="tiingo", run_id="r", perma_ticker="")
    frame["ts"] = pd.Timestamp("2026-10-05", tz="UTC")
    for day in (date(2026, 9, 28), date(2026, 10, 5)):
        stamped = frame.assign(session_date=day, knowledge_ts=pd.Timestamp(day, tz="UTC"))
        writer.write_table("instruments/listing_history", day, "r", stamped)
    members = pd.DataFrame(
        {
            "index_name": ["SP500", "SP500"],
            "ticker": ["AAA", "BBB"],
            "start_date": [date(1999, 1, 4), date(2013, 1, 2)],  # BBB joins after S
            "end_date": [None, None],
            "ts": pd.Timestamp("2026-10-08", tz="UTC"),
            "session_date": date(2026, 10, 8),
            "knowledge_ts": pd.Timestamp("2026-10-08", tz="UTC"),
            "source": "sp500_history",
            "run_id": "m",
        }
    )
    writer.write_table("instruments/index_membership", date(2026, 10, 8), "m", members)
    got = universe_asof(StoreReader(backend), S)
    assert got.snapshot == date(2026, 10, 5) and got.session == S
    assert got.membership_snapshot == date(2026, 10, 8)
    assert list(got.instruments["ticker"]) == ["AAA", "CCC", "DDD", "RCY"]


def test_universe_asof_without_a_snapshot_is_missing_data() -> None:
    with pytest.raises(MissingDataError):
        universe_asof(StoreReader(MemoryBackend()), S)


def test_listings_over_a_window_marks_reused_tickers_and_keeps_the_listing_dates() -> None:
    from algotrade.data.listings.universe import listings_over  # noqa: PLC0415

    backend = MemoryBackend()
    writer = StoreWriter(backend)
    frame = _listings().assign(perma_ticker=["P" + str(i) for i in range(9)])
    frame.loc[6, "perma_ticker"] = ""
    stamped = frame.assign(
        ts=pd.Timestamp("2026-10-05", tz="UTC"),
        session_date=date(2026, 10, 5),
        knowledge_ts=pd.Timestamp("2026-10-05", tz="UTC"),
        source="tiingo",
        run_id="r",
        price_currency="USD",
    )
    stamped["start_date"] = pd.to_datetime(stamped["start_date"]).dt.date
    stamped["end_date"] = pd.to_datetime(stamped["end_date"]).dt.date.where(
        stamped["end_date"].notna(), None
    )
    writer.write_table("instruments/listing_history", date(2026, 10, 5), "r", stamped)
    members = pd.DataFrame(
        {"index_name": ["SP500"], "ticker": ["AAA"], "start_date": [date(2000, 1, 3)],
         "end_date": [None], "ts": [pd.Timestamp("2026-10-05", tz="UTC")]},
    )  # fmt: skip
    known = pd.Timestamp("2026-10-05", tz="UTC")
    members = members.assign(session_date=date(2026, 10, 5), knowledge_ts=known)
    members = members.assign(source="x", run_id="m")
    writer.write_table("instruments/index_membership", date(2026, 10, 5), "m", members)
    out, snapshot = listings_over(StoreReader(backend), date(2010, 1, 4), date(2012, 6, 1))
    assert snapshot == date(2026, 10, 5)
    by_id = out.set_index("instrument_id")
    assert set(by_id.index) == {
        "EQ:TIINGO:A", "EQ:TIINGO:C", "EQ:TIINGO:D",
        "EQ:TIINGO:OLD", "EQ:TIINGO:NEW", "EQ:TIINGO:F",
    }  # fmt: skip
    assert by_id.loc["EQ:TIINGO:OLD", "reused"] and by_id.loc["EQ:TIINGO:NEW", "reused"]
    assert not by_id.loc["EQ:TIINGO:A", "reused"]
    assert by_id.loc["EQ:TIINGO:OLD", "end_date"] == date(2010, 12, 31)
    assert by_id.loc["EQ:TIINGO:A", "end_date"] is None
