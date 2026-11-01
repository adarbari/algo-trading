"""``data.rates.curve``: the latest stored Treasury curve on or before a date."""

from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data import feature_inputs as inputs
from algotrade.data.rates import TABLE, curve, tenor_history
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

FIRST, SECOND = date(2026, 10, 1), date(2026, 10, 2)


def _rows(day: date, short: float) -> list[dict[str, object]]:
    ts = pd.Timestamp(day, tz="UTC")
    tenors = [
        ("10Y", 3650, short + 0.01), ("1Y", 365, short - 0.002), ("1M", 30, short),
        ("3M", 91, short - 0.001),
    ]  # fmt: skip
    return [
        {
            "instrument_id": f"RATE:UST-{t}",
            "ts": ts,
            "tenor": t,
            "tenor_days": d,
            "rate_par": r,
            "rate_cont": r,
        }
        for t, d, r in tenors
    ]


@pytest.fixture
def reader() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for day, short in ((FIRST, 0.04), (SECOND, 0.05)):
        writer.write_table(TABLE, day, "r", stamped(_rows(day, short), day, "r"))
    return StoreReader(backend)


def test_latest_curve_on_or_before(reader: StoreReader) -> None:
    holiday = curve(reader, date(2026, 10, 12))  # a bond-market holiday uses the last curve
    assert holiday.curve_date == SECOND and not holiday.pre_snapshot
    assert holiday.frame["tenor"].tolist() == ["1M", "3M", "1Y", "10Y"]  # sorted by days
    assert float(holiday.rate(30 / 365)) == pytest.approx(0.05)
    assert float(curve(reader, FIRST).rate(0.0)) == pytest.approx(0.04)


def test_before_the_first_curve_falls_back_flagged(reader: StoreReader) -> None:
    early = curve(reader, date(2020, 1, 2))
    assert early.curve_date == FIRST and early.pre_snapshot


def test_no_curve_stored_is_missing_data() -> None:
    with pytest.raises(MissingDataError, match="rates"):
        curve(StoreReader(MemoryBackend()), FIRST)


def test_tenor_history_is_one_row_per_curve_date(reader: StoreReader) -> None:
    got = tenor_history(reader, "10Y", FIRST, SECOND)
    assert got["session_date"].tolist() == [FIRST, SECOND]
    assert got["rate_par"].tolist() == pytest.approx([0.05, 0.06])
    assert tenor_history(reader, "10Y", SECOND, SECOND)["rate_par"].tolist() == pytest.approx(
        [0.06]
    )
    assert tenor_history(reader, "30Y", FIRST, SECOND).empty
    assert tenor_history(StoreReader(MemoryBackend()), "10Y", FIRST, SECOND).empty


def test_the_10y_input_serves_the_window_up_to_the_session(reader: StoreReader) -> None:
    loaded = inputs.load_input(reader, "rates/treasury_10y", [SECOND], 1)
    assert loaded.at(SECOND, 1)["rate_par"].tolist() == pytest.approx([0.05, 0.06])
    assert inputs.has_input("events/macro_release")
