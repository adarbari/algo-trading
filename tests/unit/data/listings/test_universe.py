"""``universe_asof`` on synthetic listing frames (ADR 0013 rule at S, ADR 0018 ids)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.universe import (
    COLUMNS,
    delisted_by,
    listed_asof,
    listing_frame,
    universe_asof,
)
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


def test_delisted_by_counts_only_an_end_date_on_or_before_the_session() -> None:
    backend = MemoryBackend()
    day = date(2026, 10, 5)
    frame = _listings().assign(source="tiingo", run_id="r", perma_ticker="", session_date=day)
    frame["ts"] = pd.Timestamp(day, tz="UTC")
    frame["knowledge_ts"] = pd.Timestamp(day, tz="UTC")
    StoreWriter(backend).write_table("instruments/listing_history", day, "r", frame)
    reader = StoreReader(backend)
    assert delisted_by(reader, date(2012, 5, 31)) == {
        "EQ:TIINGO:OLD": date(2010, 12, 31),
        "EQ:TIINGO:F": date(2012, 5, 31),
    }
    assert "EQ:TIINGO:C" not in delisted_by(reader, date(2013, 1, 1))  # ends 2013-01-02: unknown
    got = delisted_by(reader, date(2013, 1, 2))
    assert got["EQ:TIINGO:C"] == date(2013, 1, 2) and "EQ:TIINGO:A" not in got  # open, no id: out


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


def test_listings_over_catches_a_listing_and_a_membership_between_month_starts() -> None:
    from algotrade.data.listings.universe import listings_over  # noqa: PLC0415

    now, day = pd.Timestamp("2026-10-05", tz="UTC"), date(2026, 10, 5)
    rows = [  # id, ticker, exchange, start, end
        ("EQ:TIINGO:SHORT", "SHT", "NASDAQ", date(2012, 3, 8), date(2012, 3, 20)),  # inside a month
        ("EQ:TIINGO:MID", "MID", "NYSE", date(2000, 1, 3), None),  # a member 03-08..03-20 only
        ("EQ:TIINGO:OUT", "OUT", "NYSE", date(2000, 1, 3), None),  # never a member
    ]
    frame = pd.DataFrame(
        rows, columns=["instrument_id", "ticker", "exchange", "start_date", "end_date"]
    )
    frame = frame.assign(asset_type="Stock", price_currency="USD", perma_ticker="", ts=now,
                         session_date=day, knowledge_ts=now, source="tiingo",
                         run_id="l")  # fmt: skip
    frame["end_date"] = frame["end_date"].astype(object).where(frame["end_date"].notna(), None)
    members = pd.DataFrame({"index_name": ["SP500"], "ticker": ["MID"],
                            "start_date": [date(2012, 3, 8)], "end_date": [date(2012, 3, 20)],
                            "ts": [now], "session_date": [day], "knowledge_ts": [now],
                            "source": ["x"], "run_id": ["m"]})  # fmt: skip
    writer = StoreWriter(MemoryBackend())
    writer.write_table("instruments/listing_history", day, "l", frame)
    writer.write_table("instruments/index_membership", day, "m", members)
    out, _ = listings_over(StoreReader(writer._backend), date(2012, 1, 4), date(2012, 6, 1))
    assert set(out["instrument_id"]) == {"EQ:TIINGO:SHORT", "EQ:TIINGO:MID"}


def test_listings_over_excludes_a_recycled_ticker_whose_membership_ended_before_the_listing() -> (
    None
):
    from algotrade.data.listings.universe import listings_over  # noqa: PLC0415

    now, day = pd.Timestamp("2026-10-05", tz="UTC"), date(2026, 10, 5)
    frame = pd.DataFrame(
        [("EQ:TIINGO:X2", "X", "NYSE", "Stock", date(2015, 1, 5), None)],
        columns=["instrument_id", "ticker", "exchange", "asset_type", "start_date", "end_date"],
    ).assign(price_currency="USD", perma_ticker="", ts=now, session_date=day,
             knowledge_ts=now, source="tiingo", run_id="l")  # fmt: skip
    members = pd.DataFrame(
        {"index_name": ["SP500"], "ticker": ["X"], "start_date": [date(2000, 1, 3)],
         "end_date": [date(2005, 12, 30)], "ts": [now], "session_date": [day],
         "knowledge_ts": [now], "source": ["x"], "run_id": ["m"]}
    )  # fmt: skip
    writer = StoreWriter(MemoryBackend())
    writer.write_table("instruments/listing_history", day, "l", frame)
    writer.write_table("instruments/index_membership", day, "m", members)
    out, _ = listings_over(StoreReader(writer._backend), date(2010, 1, 4), date(2020, 12, 31))
    assert out.empty  # the old company's membership is not the new listing's


# ---------------------------------------------------- the merged table (ADR 0087): every read


def _merged_store() -> StoreReader:
    """A merged snapshot: a Tiingo row, a Massive-only row, a Tiingo row out of scope that
    carries an id and is alive (an OTC listing), and a Massive row with no start date."""
    now, day = pd.Timestamp("2026-10-05", tz="UTC"), date(2026, 10, 5)
    rows = [  # id, ticker, exchange, source, start, end, scope_reason, security_type
        ("EQ:A", "AAA", "NASDAQ", "tiingo", date(2000, 1, 3), None, None, None),
        ("EQ:M", "MMM", "NASDAQ", "massive", date(2000, 1, 3), date(2013, 1, 2), None, "WARRANT"),
        ("EQ:O", "OTC", "NASDAQ", "tiingo", date(2000, 1, 3), None, "other_exchange", None),
        ("EQ:U", "UND", "NASDAQ", "massive", None, date(2014, 1, 2), None, "COMMON_STOCK"),
        (None, "NOEND", "NASDAQ", "massive", None, None, None, None),
    ]
    frame = pd.DataFrame(
        rows,
        columns=["instrument_id", "ticker", "exchange", "source", "start_date", "end_date",
                 "scope_reason", "security_type"],
    ).assign(asset_type="Stock", price_currency="USD", perma_ticker="", ts=now,
             session_date=day, knowledge_ts=now, run_id="r")  # fmt: skip
    frame["start_date"] = (
        frame["start_date"].astype(object).where(frame["start_date"].notna(), None)
    )
    frame["end_date"] = frame["end_date"].astype(object).where(frame["end_date"].notna(), None)
    members = pd.DataFrame(
        {"index_name": ["SP500"], "ticker": ["AAA"], "start_date": [date(2000, 1, 3)],
         "end_date": [None], "ts": [now], "session_date": [day], "knowledge_ts": [now],
         "source": ["x"], "run_id": ["m"]}
    )  # fmt: skip
    writer = StoreWriter(MemoryBackend())
    writer.write_table("instruments/listing_history", day, "r", frame)
    writer.write_table("instruments/index_membership", day, "m", members)
    return StoreReader(writer._backend)


def test_rows_out_of_scope_are_stored_but_never_read() -> None:
    from algotrade.data.listings.resolvers import listing_resolver  # noqa: PLC0415
    from algotrade.data.listings.tickers import listing_tickers  # noqa: PLC0415
    from algotrade.data.listings.universe import (  # noqa: PLC0415
        listing_frame,
        listings_over,
        read_listings,
    )

    reader = _merged_store()
    raw = reader.table("instruments/listing_history", date(2026, 10, 5))
    assert raw is not None and "OTC" in set(raw["ticker"])  # stored
    frame, snap = listing_frame(reader)
    assert snap.snapshot_date == date(2026, 10, 5) and "OTC" not in set(frame["ticker"])
    assert "OTC" not in set(universe_asof(reader, date(2012, 6, 1)).instruments["ticker"])
    over, _ = listings_over(reader, date(2010, 1, 4), date(2012, 6, 1))
    assert "OTC" not in set(over["ticker"])
    assert "EQ:O" not in delisted_by(reader, date(2030, 1, 1))
    assert "OTC" not in set(read_listings(reader)[0]["ticker"])
    assert listing_resolver(reader)(date(2012, 6, 1)).knows("OTC") is False
    assert "EQ:O" not in listing_tickers(reader).by_id


def test_an_old_snapshot_reads_null_types_and_the_added_columns_without_a_key_error() -> None:
    backend, day = MemoryBackend(), date(2026, 10, 5)
    old = _listings().assign(source="tiingo", run_id="r", perma_ticker="", price_currency="USD")
    old["ts"] = pd.Timestamp(day, tz="UTC")
    old = old.assign(session_date=day, knowledge_ts=pd.Timestamp(day, tz="UTC"))
    old["start_date"] = pd.to_datetime(old["start_date"]).dt.date
    old["end_date"] = pd.to_datetime(old["end_date"]).dt.date.where(old["end_date"].notna(), None)
    StoreWriter(backend).write_table("instruments/listing_history", day, "r", old)
    members = pd.DataFrame(
        {"index_name": ["SP500"], "ticker": ["AAA"], "start_date": [date(1999, 1, 4)],
         "end_date": [None], "ts": [pd.Timestamp(day, tz="UTC")], "session_date": [day],
         "knowledge_ts": [pd.Timestamp(day, tz="UTC")], "source": ["x"], "run_id": ["m"]}
    )  # fmt: skip
    StoreWriter(backend).write_table("instruments/index_membership", day, "m", members)
    got = universe_asof(StoreReader(backend), S)  # no scope_reason, no security_type stored
    assert list(got.instruments["ticker"]) == ["AAA", "CCC", "DDD", "RCY"]
    assert got.instruments["security_type"].isna().all()
    assert got.null_type == 3 and got.undated == 0  # the three Stocks; DDD is an ETF
    frame, _ = listing_frame(StoreReader(backend))
    assert {"scope_reason", "id_source", "vendor_end_date", "is_adr"} <= set(frame.columns)
    assert frame["scope_reason"].isna().all() and len(frame) == len(old)


def test_a_listing_with_no_start_is_counted_undated_and_never_returned() -> None:
    from algotrade.data.listings.universe import listings_over  # noqa: PLC0415

    reader = _merged_store()
    got = universe_asof(reader, date(2012, 6, 1))
    # UND (end 2014) and NOEND (open) may be alive on S: counted, never returned; MMM is dated.
    assert got.undated == 2
    assert list(got.instruments["ticker"]) == ["AAA", "MMM"]
    assert list(got.instruments["security_type"].fillna("none")) == ["none", "WARRANT"]
    assert got.null_type == 1  # AAA is a Stock with no type
    assert universe_asof(reader, date(2013, 6, 3)).undated == 2  # UND until 2014-01-02, NOEND open
    assert universe_asof(reader, date(2015, 1, 5)).undated == 1  # UND has ended: only NOEND
    over, _ = listings_over(reader, date(2010, 1, 4), date(2020, 12, 31))
    assert "UND" not in set(over["ticker"])  # the guard: a null start is never in a window


def test_the_winners_sample_reads_only_tiingo_rows() -> None:
    from algotrade.data.listings.universe import read_listings  # noqa: PLC0415

    frame, _ = read_listings(_merged_store())
    assert set(frame["source"]) == {"tiingo"} and list(frame["ticker"]) == ["AAA"]
