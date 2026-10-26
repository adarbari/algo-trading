"""The PUT-index replication (ADR 0084 decision 6): which put is sold, the portfolio's value by
hand, settlement at expiry, a missing price never carried, the gap statistics, the monthly rolls
and the refusal to use a later rate for an earlier day."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_ingestion.tasks.verification import put_check
from algotrade_ingestion.tasks.verification import put_replication as pr
from tests.helpers.rollup_store import write_curve

ROLL, EXPIRY = date(2019, 8, 16), date(2019, 9, 20)


def put(strike: float, bid: float, ask: float, *, root: str = "SPX", expiry: date = EXPIRY) -> dict:
    return {
        "instrument_id": f"OPT:{root}{expiry:%y%m%d}P{int(strike * 1000):08d}",
        "root": root, "right": "P", "expiry": expiry, "strike": strike, "bid": bid, "ask": ask,
        "underlying_price": 2850.0,
    }  # fmt: skip


def chain(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_the_put_sold_is_the_standard_series_strike_nearest_the_index() -> None:
    rows = chain(
        put(2845, 49.0, 51.0),
        put(2850, 50.0, 52.0),
        put(2855, 51.0, 53.0),
        put(2850, 80.0, 82.0, root="SPXW"),  # the PM-settled series is another contract
        put(2850, 0.0, 70.0),  # a one-sided quote has no mid
    )
    sold = pr.sell_put(rows, ROLL, EXPIRY, "mid")
    assert sold is not None
    assert (sold.strike, sold.premium) == (2850.0, 51.0)
    assert pr.sell_put(rows, ROLL, EXPIRY, "bid").premium == 50.0  # type: ignore[union-attr]


def test_a_tie_takes_the_lower_strike_and_no_priced_put_is_none() -> None:
    tie = chain(put(2845, 40.0, 42.0), put(2855, 60.0, 62.0)).assign(underlying_price=2850.0)
    assert pr.sell_put(tie, ROLL, EXPIRY, "mid").strike == 2845.0  # type: ignore[union-attr]
    assert pr.sell_put(chain(put(2850, 0.0, 5.0)), ROLL, EXPIRY, "mid") is None


def test_the_portfolio_value_by_hand_and_settlement_at_expiry() -> None:
    mid_day, spot_at_expiry = date(2019, 8, 26), 2800.0
    contract = put(2850, 49.0, 51.0)["instrument_id"]
    quotes = {
        ROLL: chain(put(2850, 49.0, 51.0)),
        mid_day: chain(put(2850, 39.0, 41.0)),
        EXPIRY: chain(put(2850, 0.0, 1.0)).assign(underlying_price=spot_at_expiry),
    }
    sim = pr.replicate(quotes, [ROLL, EXPIRY], {ROLL: 0.02}, "mid")
    accrual = 1 + 0.02 * 10 / 360
    assert sim[ROLL] == 1.0
    assert sim[mid_day] == pytest.approx(((2850 + 50) * accrual - 40) / 2850)
    expiry_accrual = 1 + 0.02 * 35 / 360
    assert sim[EXPIRY] == pytest.approx(((2850 + 50) * expiry_accrual - 50) / 2850)  # 2850 - 2800
    assert contract in quotes[ROLL]["instrument_id"].tolist()


def test_a_second_period_starts_from_the_first_ones_level() -> None:
    nxt = date(2019, 10, 18)
    quotes = {
        ROLL: chain(put(2850, 49.0, 51.0)),
        EXPIRY: chain(put(2850, 0, 1, expiry=EXPIRY), put(2900, 60, 62, expiry=nxt)).assign(
            underlying_price=2900.0
        ),
        nxt: chain(put(2900, 0, 1, expiry=nxt)).assign(underlying_price=2950.0),
    }
    sim = pr.replicate(quotes, [ROLL, EXPIRY, nxt], {ROLL: 0.0, EXPIRY: 0.0}, "mid")
    first = ((2850 + 50) * 1.0 - 0.0) / 2850  # expired out of the money
    assert sim[EXPIRY] == pytest.approx(first)
    assert sim[nxt] == pytest.approx(first * (2900 + 61) / 2900 - first * 0.0 / 2900)


def test_a_session_without_a_price_for_the_held_put_is_nan_never_the_last_price() -> None:
    quotes = {
        ROLL: chain(put(2850, 49.0, 51.0)),
        date(2019, 8, 19): chain(put(2900, 10.0, 12.0)),  # a different strike only
        EXPIRY: chain(put(2850, 0, 1)).assign(underlying_price=2900.0),
    }
    sim = pr.replicate(quotes, [ROLL, EXPIRY], {ROLL: 0.0}, "mid")
    assert np.isnan(sim[date(2019, 8, 19)]) and not np.isnan(sim[EXPIRY])


def test_a_roll_without_quotes_or_without_a_put_is_an_error() -> None:
    with pytest.raises(ValueError, match="no quotes"):
        pr.replicate({}, [ROLL, EXPIRY], {ROLL: 0.0})
    with pytest.raises(ValueError, match="no priced SPX put"):
        pr.replicate({ROLL: chain(put(2850, 0.0, 1.0))}, [ROLL, EXPIRY], {ROLL: 0.0})
    with pytest.raises(ValueError, match="price must be"):
        pr.put_price(chain(put(2850, 1.0, 2.0)), "last")


def test_the_gap_statistics_over_the_common_sessions() -> None:
    days = [date(2019, 8, d) for d in (16, 19, 20, 21)]
    published = pd.Series([100.0, 101.0, 100.5, 102.0], index=days)
    same = pr.compare(published * 3, published)  # rebased, so a scale is no gap
    assert same["gap_bp"] == pytest.approx(0) and same["rms_daily_diff_bp"] == pytest.approx(0)
    assert same["sessions"] == 4 and same["skipped_sessions"] == 0
    off = pr.compare(pd.Series([100.0, 101.0, 100.5, 102.2], index=days), published)
    assert off["gap_bp"] == pytest.approx((102.2 - 102.0) / 100 * 1e4)
    assert off["max_daily_diff_bp"] > 0 and off["correlation"] > 0.99
    partial = pr.compare(pd.Series([100.0, np.nan, 100.5], index=days[:3]), published)
    assert partial["sessions"] == 2 and partial["skipped_sessions"] == 1


def test_the_rolls_are_the_third_friday_or_the_session_before_a_holiday() -> None:
    sessions = [date(2019, 4, 18), date(2019, 5, 17), date(2019, 6, 21), date(2019, 7, 19)]
    # 2019-04-19 was Good Friday: the roll is Thursday the 18th.
    assert put_check.roll_sessions(sessions, date(2019, 4, 1), date(2019, 7, 31)) == sessions
    assert (
        put_check.roll_sessions(sessions[1:], date(2019, 4, 1), date(2019, 7, 31)) == sessions[1:]
    )


def test_a_roll_before_the_first_stored_curve_is_refused_not_given_todays_rate() -> None:
    writer = StoreWriter(MemoryBackend())
    write_curve(writer, date(2024, 1, 2), 0.0546)
    reader = StoreReader(writer._backend)
    assert put_check.three_month_rate(reader, date(2024, 1, 3)) == 0.0546
    with pytest.raises(MissingDataError, match="2002"):
        put_check.three_month_rate(reader, date(2019, 8, 16))


def test_a_saturday_or_good_friday_contract_belongs_to_its_expiry_session() -> None:
    """Before 2015 the monthly put is dated the Saturday after the roll session; a Good Friday
    expiry's contract is dated the Friday after the Thursday session."""
    friday, saturday = date(2014, 3, 21), date(2014, 3, 22)
    rows = chain(
        put(1850, 20.0, 22.0, expiry=saturday), put(1850, 30.0, 32.0, expiry=date(2014, 4, 19))
    )
    sold = pr.sell_put(rows.assign(underlying_price=1850.0), date(2014, 2, 21), friday, "mid")
    assert sold is not None and sold.premium == 21.0  # the Saturday, not the next month
    thursday, good_friday = date(2019, 4, 18), date(2019, 4, 19)
    holiday = chain(put(2900, 9.0, 11.0, expiry=good_friday)).assign(underlying_price=2900.0)
    assert pr.sell_put(holiday, date(2019, 3, 15), thursday, "mid") is not None
    assert pr.sell_put(holiday, date(2019, 3, 15), date(2019, 4, 15), "mid") is None  # 4 days off


def test_a_missing_published_level_is_a_named_error_not_a_traceback() -> None:
    reader = StoreReader(StoreWriter(MemoryBackend())._backend)
    with pytest.raises(MissingDataError, match="PUT"):
        put_check.published_levels(reader)
