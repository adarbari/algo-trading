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
    out = listed_asof(_listings(), S, {"EQ:TIINGO:A"})
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
    out = listed_asof(_listings(), S, {"EQ:TIINGO:A"}).instruments
    assert list(out.columns) == COLUMNS and "end_date" not in out.columns


def test_universe_asof_reads_the_latest_snapshot_and_says_which() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    frame = _listings().assign(source="tiingo", run_id="r", perma_ticker="")
    frame["ts"] = pd.Timestamp("2026-10-05", tz="UTC")
    for day in (date(2026, 9, 28), date(2026, 10, 5)):
        stamped = frame.assign(session_date=day, knowledge_ts=pd.Timestamp(day, tz="UTC"))
        writer.write_table("instruments/listing_history", day, "r", stamped)
    got = universe_asof(StoreReader(backend), S, {"EQ:TIINGO:A"})
    assert got.snapshot == date(2026, 10, 5) and got.session == S
    assert list(got.instruments["ticker"]) == ["AAA", "CCC", "DDD", "RCY"]


def test_universe_asof_without_a_snapshot_is_missing_data() -> None:
    with pytest.raises(MissingDataError):
        universe_asof(StoreReader(MemoryBackend()), S, set())
