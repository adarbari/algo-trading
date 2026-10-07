"""The chain readings the positioning groups share: the spot rule (close, else price, an id
quoted twice keeps its latest row), expiry days, two-sided mids and relative spreads."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.positioning import chain_inputs as ci


def test_spot_is_the_close_then_the_price_then_nothing() -> None:
    quotes = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:E"],
            "close": [101.0, np.nan, 0.0, -1.0, 50.0],
            "price": [99.0, 98.0, 97.0, 96.0, np.nan],
        }
    )
    spots = ci.closing_spots(quotes)
    assert spots["EQ:A"] == 101.0  # the close, not the after-hours price
    assert spots["EQ:B"] == 98.0  # no close: the price
    assert spots["EQ:C"] == 97.0 and spots["EQ:D"] == 96.0  # a close that is not positive
    assert spots["EQ:E"] == 50.0
    assert ci.closing_spots(quotes.assign(price=np.nan, close=0.0)).isna().all()


def test_missing_columns_and_empty_inputs() -> None:
    assert ci.closing_spots(pd.DataFrame({"instrument_id": ["EQ:A"], "price": [5.0]}))[
        "EQ:A"
    ] == pytest.approx(5.0)
    assert ci.closing_spots(pd.DataFrame({"instrument_id": ["EQ:A"], "close": [6.0]}))[
        "EQ:A"
    ] == pytest.approx(6.0)
    assert ci.closing_spots(None).empty and ci.closing_spots(pd.DataFrame()).empty


def test_an_id_quoted_twice_keeps_its_latest_row() -> None:
    quotes = pd.DataFrame(
        {
            "instrument_id": ["EQ:A", "EQ:A"],
            "ts": pd.to_datetime(["2026-10-02 22:00", "2026-10-02 21:00"], utc=True),
            "close": [101.0, 100.0],
            "price": [101.0, 100.0],
        }
    )
    assert ci.closing_spots(quotes)["EQ:A"] == 101.0  # the later ts, whatever the row order


def test_days_to_expiry_from_dates_or_timestamps() -> None:
    session = date(2026, 10, 2)
    expiries = pd.Series([date(2026, 10, 2), date(2026, 10, 9), date(2026, 11, 1)])
    assert list(ci.days_to(ci.expiry_days(expiries), session)) == [0, 7, 30]
    stamps = pd.Series(pd.to_datetime(["2026-10-03 00:00", "2026-10-02 21:00"]))
    assert list(ci.days_to(ci.expiry_days(stamps), session)) == [1, 0]
    assert list(ci.days_to(np.array(["2026-10-01"], dtype="datetime64[s]"), session)) == [-1]


def test_two_sided_mid_and_relative_spread() -> None:
    bid = pd.Series([1.0, 0.0, 2.0, 1.5, None])
    ask = pd.Series([1.2, 1.0, 2.0, 1.0, 1.0])  # two-sided, no bid, locked, crossed, null bid
    mid = ci.two_sided_mid(bid, ask)
    assert mid[0] == pytest.approx(1.1) and np.isnan(mid[1:]).all()
    spread = ci.relative_spread(bid, ask, mid)
    assert spread[0] == pytest.approx(0.2 / 1.1) and np.isnan(spread[1:]).all()
