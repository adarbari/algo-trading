"""``data.macro.vintages``: the ``pit = "lag"`` rule dates each value ``release_lag_days``
after its observation and flags it ``lagged``."""

from datetime import date

import pandas as pd
import pytest

from algotrade.data.macro.vintages import lagged_vintages


def test_vintage_date_is_the_observation_plus_the_lag() -> None:
    obs = pd.DataFrame(
        {
            "instrument_id": ["IDX:SPX"] * 2,
            "obs_date": ["2008-03-03", "2008-03-04"],
            "value": [1.0, 2.0],
        }
    )
    out = lagged_vintages(obs, 1)
    assert list(out["obs_date"]) == [date(2008, 3, 3), date(2008, 3, 4)]
    assert list(out["vintage_date"]) == [date(2008, 3, 4), date(2008, 3, 5)]
    assert set(out["vintage_kind"]) == {"lagged"} and list(out["value"]) == [1.0, 2.0]
    assert list(lagged_vintages(obs, 0)["vintage_date"]) == list(out["obs_date"])
    assert "vintage_date" not in obs.columns  # the input is not changed


def test_a_negative_lag_is_refused() -> None:
    with pytest.raises(ValueError, match="release_lag_days"):
        lagged_vintages(pd.DataFrame({"obs_date": []}), -1)
