from datetime import datetime

import numpy as np
import pytest

from algotrade.core.model.errors import DataValidationError
from algotrade.core.model.types import Order, Side
from algotrade.core.time.clock import to_utc_datetime
from algotrade.core.views.series import PriceSeries
from tests.helpers.domain_objects import T0, fill, series_from_closes


def test_side_sign() -> None:
    assert Side.BUY.sign == 1
    assert Side.SELL.sign == -1


def test_order_rejects_non_positive_quantity() -> None:
    with pytest.raises(ValueError, match="positive"):
        Order("X", Side.BUY, 0, T0)


def test_order_rejects_naive_datetime() -> None:
    with pytest.raises(ValueError, match="timezone"):
        Order("X", Side.BUY, 1, datetime(2024, 1, 1))  # noqa: DTZ001


def test_fill_signed_quantity_and_notional() -> None:
    f = fill(side=Side.SELL, qty=3, price=10)
    assert f.signed_quantity == -3
    assert f.notional == 30


def test_series_length_mismatch() -> None:
    s = series_from_closes([1, 2, 3])
    with pytest.raises(ValueError, match="rows"):
        PriceSeries("X", s.timestamps, s.open, s.high, s.low, s.close[:2].copy(), s.volume)


def test_series_unknown_field() -> None:
    with pytest.raises(KeyError):
        series_from_closes([1]).field("vwap")


def test_to_utc_datetime() -> None:
    dt = to_utc_datetime(np.datetime64("2024-03-01T12:30:00", "ns"))
    assert (dt.year, dt.month, dt.hour, dt.minute) == (2024, 3, 12, 30)
    assert dt.utcoffset() is not None


def test_data_validation_error_message() -> None:
    err = DataValidationError("file.csv", ["a", "b"])
    assert str(err) == "file.csv: a; b"


def test_instrument_validation_and_multipliers() -> None:
    from algotrade.core.model.instruments import (  # noqa: PLC0415
        AssetClass,
        Instrument,
        multipliers,
    )

    es = Instrument("FUT:ESZ6", "ESZ6", AssetClass.FUTURE, multiplier=50, tick_size=0.25)
    assert multipliers([es]) == {"FUT:ESZ6": 50}
    with pytest.raises(ValueError, match="multiplier"):
        Instrument("X", "X", multiplier=0)
    with pytest.raises(ValueError, match="tick_size"):
        Instrument("X", "X", tick_size=0)
