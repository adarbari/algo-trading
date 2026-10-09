"""``index_members`` on intervals from the recorded fja05680 slice (ADR 0013 over history)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data.listings.membership import SP500, index_members, members_on
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.readers import StoreReader
from algotrade.storage.tables.writers import StoreWriter
from algotrade_sources.vendors.sp500_history.membership import parse_membership
from tests.helpers.payloads import published as payloads


def _intervals() -> pd.DataFrame:
    return parse_membership(payloads.membership_csv())[0]


def test_a_ticker_is_a_member_between_its_dates_and_both_ends_count() -> None:
    rows = _intervals()
    assert "TWTR" in members_on(rows, date(2018, 6, 7))  # first day
    assert "TWTR" in members_on(rows, date(2022, 11, 1))  # last day
    assert "TWTR" not in members_on(rows, date(2018, 6, 6))
    assert "TWTR" not in members_on(rows, date(2022, 11, 2))


def test_a_ticker_that_left_and_came_back_is_a_member_only_during_each_stay() -> None:
    rows = _intervals()  # H: 1996-01-02..2001-06-29 and 2006-08-01..2007-04-10
    assert "H" in members_on(rows, date(1999, 1, 4))
    assert "H" not in members_on(rows, date(2003, 1, 2))
    assert "H" in members_on(rows, date(2006, 9, 1))


def test_a_ticker_renamed_is_two_names_and_a_still_open_stay_has_no_end() -> None:
    rows = _intervals()
    assert "FB" in members_on(rows, date(2020, 1, 2)) and "META" not in members_on(
        rows, date(2020, 1, 2)
    )
    assert "META" in members_on(rows, date(2026, 10, 8))


def test_index_members_reads_the_latest_snapshot_and_names_it() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    rows = _intervals().assign(
        ts=pd.Timestamp("2026-10-08", tz="UTC"),
        source="sp500_history",
        run_id="m",
    )
    for day in (date(2026, 10, 1), date(2026, 10, 8)):
        stamped = rows.assign(session_date=day, knowledge_ts=pd.Timestamp(day, tz="UTC"))
        writer.write_table("instruments/index_membership", day, "m", stamped)
    got = index_members(StoreReader(backend), date(2012, 6, 1))
    assert got.snapshot == date(2026, 10, 8) and got.index_name == SP500
    assert "AAPL" in got.tickers and "TWTR" not in got.tickers


def test_no_membership_snapshot_is_missing_data() -> None:
    with pytest.raises(MissingDataError):
        index_members(StoreReader(MemoryBackend()), date(2012, 6, 1))
