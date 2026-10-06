"""``observations``: the latest vintage per observation as a session knew it, and complete
windows only (a history that does not reach a window's start gives null)."""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from algotrade.features.rollups.market.observations import (
    change_12m,
    known_series,
    last_months,
    latest,
    since,
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


def test_the_latest_vintage_known_by_the_session_wins_and_nulls_are_no_observation() -> None:
    frame = rows(
        ("2008-01-01", "2008-02-01", 4.9),
        ("2008-01-01", "2008-03-07", 5.0),  # the March revision of January
        ("2008-02-01", "2008-03-07", None),  # FRED's "."
    )
    feb = known_series(frame, date(2008, 2, 15))[ID]
    assert list(feb) == [4.9]
    march = known_series(frame, date(2008, 3, 7))[ID]
    assert list(march) == [5.0]  # revised; February is no observation
    assert known_series(frame, date(2008, 1, 31)) == {}
    assert (
        known_series(None, date(2008, 3, 7)) == {} == known_series(frame.iloc[:0], date(2008, 3, 7))
    )


def test_old_observations_are_never_read() -> None:
    frame = rows(("2000-01-01", "2000-02-01", 4.0), ("2008-01-01", "2008-02-01", 5.0))
    assert list(known_series(frame, date(2008, 3, 1), history_days=800)[ID]) == [5.0]
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
    assert list(last_months(s, 12)) == list(s)  # type: ignore[arg-type]
    assert last_months(s, 13) is None
    assert last_months(s.drop(s.index[5]), 11) is None  # a missing month
    day = pd.Timestamp("2008-06-03")
    assert value_near(s, day) == 5.0  # June 1, two days before
    assert np.isnan(value_near(s, pd.Timestamp("2008-06-20")))  # the last is 19 days older
    window = since(s, date(2008, 6, 1))
    assert window is not None and list(window) == [6.0, 7.0, 8.0, 9.0, 10.0, 11.0]
    assert since(s, date(2007, 12, 1)) is None  # the history starts in January 2008
    assert since(None, date(2008, 6, 1)) is None
