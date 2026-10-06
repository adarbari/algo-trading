"""``observations``: the input's known rows as one series per id, complete day windows only (a
history that does not reach a window's start gives null), and monthly windows that tolerate gaps
down to a minimum of months present."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.market.observations import (
    as_series,
    by_month,
    change_12m,
    latest,
    since,
    trailing_mean,
    value_near,
)

ID = "MACRO:UNRATE"


def rows(*items: tuple[str, str, float | None]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "instrument_id": ID,
                "obs_date": date.fromisoformat(obs),
                "vintage_date": date.fromisoformat(vintage),
                "value": value,
            }
            for obs, vintage, value in items
        ]
    ).sort_values("vintage_date", kind="stable")


def test_known_rows_become_one_series_per_id_and_nulls_are_no_observation() -> None:
    frame = rows(
        ("2008-02-01", "2008-03-07", None),  # FRED's "."
        ("2008-01-01", "2008-03-07", 5.0),
    )
    frame = pd.concat([frame, frame.assign(instrument_id="MACRO:B", value=[1.0, 2.0])])
    got = as_series(frame)
    assert sorted(got) == ["MACRO:B", ID]
    assert list(got[ID]) == [5.0]  # February is no observation
    assert list(got["MACRO:B"].index) == [pd.Timestamp("2008-01-01"), pd.Timestamp("2008-02-01")]
    assert as_series(None) == {} == as_series(frame.iloc[:0])
    assert np.isnan(latest({}, ID))


def months(values: list[float], last: str = "2008-12-01") -> pd.Series:
    index = pd.date_range(end=last, periods=len(values), freq="MS")
    return pd.Series(values, index=index, dtype=float)


def test_year_changes_need_the_observation_a_year_earlier() -> None:
    s = months([100.0] + [0.0] * 11 + [110.0])
    assert change_12m({ID: s}, ID, ratio=True) == pytest.approx(0.10)
    assert change_12m({ID: s}, ID, ratio=False) == pytest.approx(10.0)
    assert np.isnan(change_12m({ID: s.iloc[1:]}, ID, ratio=True))  # no value a year back
    assert np.isnan(change_12m({}, ID, ratio=True))


def test_windows_are_complete_or_null() -> None:
    s = months([float(i) for i in range(12)])
    day = pd.Timestamp("2008-06-03")
    assert value_near(s, day) == 5.0  # June 1, two days before
    assert np.isnan(value_near(s, pd.Timestamp("2008-06-20")))  # the last is 19 days older
    window = since(s, date(2008, 6, 1))
    assert window is not None and list(window) == [6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
    assert since(s, date(2007, 12, 1)) is None  # the history starts in January 2008
    assert since(None, date(2008, 6, 1)) is None


def test_monthly_windows_tolerate_gaps_down_to_their_minimum() -> None:
    s = months([float(i) for i in range(12)])
    by = by_month(s)
    last = max(by)
    assert len(by) == 12 and by[last] == 11.0
    assert trailing_mean(by, last, 12, 12) == pytest.approx(5.5)
    one_gap = by_month(s.drop(s.index[5]))  # a month never published
    assert trailing_mean(one_gap, last, 12, 10) == pytest.approx((66 - 5) / 11)
    assert np.isnan(trailing_mean(one_gap, last, 12, 12))
    three_gaps = by_month(s.drop(s.index[[2, 5, 8]]))
    assert np.isnan(trailing_mean(three_gaps, last, 12, 10))  # 9 of 12: below the minimum
    assert trailing_mean(three_gaps, last - 2, 3, 2) == pytest.approx((7 + 9) / 2)
    assert by_month(None) == {}
