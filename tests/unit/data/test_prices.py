from datetime import date

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.prices import bars as read_bars
from algotrade.data.prices import frame_to_series, load_price_data
from algotrade.services.datasets import list_datasets
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

D1, D2 = date(2026, 10, 1), date(2026, 10, 2)


def bars(day: date, rows: dict[str, float]) -> pd.DataFrame:
    ts = pd.Timestamp(day, tz="UTC")
    return stamped(
        [
            {
                "instrument_id": i,
                "ts": ts,
                "open": c,
                "high": c,
                "low": c,
                "close": c,
                "volume": 1.0,
            }
            for i, c in rows.items()
        ],
        day,
        f"r{day.day}",
    )


def test_load_price_data_aligns_and_returns_terms() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    writer.write_table("bars/1d", D1, "r1", bars(D1, {"EQ:A": 1.0}))  # B missing on D1
    writer.write_table("bars/1d", D2, "r2", bars(D2, {"EQ:A": 2.0, "EQ:B": 9.0}))
    ref = stamped(
        [
            {
                "instrument_id": i,
                "symbol": i[3:],
                "asset_class": "EQ",
                "security_type": "ETF",
                "multiplier": 1.0,
                "status": "ACTIVE",
            }
            for i in ("EQ:A", "EQ:B")
        ],
        D1,
        "ref",
    )
    writer.write_table("instruments/reference", D1, "ref", ref)
    data = load_price_data(StoreReader(backend), ["EQ:A", "EQ:B"], D1, D2)
    assert list(data.series["EQ:A"].close) == [2.0]  # aligned to the common session
    assert set(data.terms) == {"EQ:A", "EQ:B"}
    assert data.versions == {"bars/1d": ["r1", "r2"], "instruments/reference": ["ref"]}
    assert (data.reference.snapshot_date, data.reference.pre_snapshot) == (D1, False)


def test_bars_are_sorted_and_missing_bars_are_an_error() -> None:
    backend = MemoryBackend()
    StoreWriter(backend).write_table("bars/1d", D2, "r2", bars(D2, {"EQ:B": 9.0, "EQ:A": 2.0}))
    frame = read_bars(StoreReader(backend), "1d", D1, D2)
    assert list(frame["instrument_id"]) == ["EQ:A", "EQ:B"]
    with pytest.raises(MissingDataError, match="no bars"):
        read_bars(StoreReader(backend), "5m", D1, D2)


def test_frame_to_series_timestamps_are_naive_utc() -> None:
    frame = bars(D1, {"EQ:A": 1.0})
    (series,) = frame_to_series(frame).values()
    assert str(series.timestamps.dtype) == "datetime64[ns]"


def test_missing_catalogue() -> None:
    with pytest.raises(MissingDataError, match="golden"):
        list_datasets(StoreReader(MemoryBackend()))


def test_session_bars_adjust_each_window_as_of_its_session() -> None:
    from algotrade.data.prices import session_bars  # noqa: PLC0415
    from tests.helpers.rollup_store import store, write_bars, write_split  # noqa: PLC0415

    writer, reader = store()
    days = write_bars(writer, {"EQ:A": [100.0, 100.0, 50.0, 50.0], "EQ:B": [10.0] * 4})
    write_split(writer, "EQ:A", days[2], 2.0, stored=days[-1])
    loaded = session_bars(reader, days[0], days[-1])
    before = loaded.window(days[0], days[1])  # the split had not happened yet
    assert list(before.loc[before["instrument_id"] == "EQ:A", "close"]) == [100.0, 100.0]
    after = loaded.window(days[0], days[-1])
    a = after[after["instrument_id"] == "EQ:A"]
    assert list(a["close"]) == [50.0] * 4 and list(a["volume"]) == [2000.0, 2000.0, 1000.0, 1000.0]
    assert list(after.loc[after["instrument_id"] == "EQ:B", "close"]) == [10.0] * 4
    assert loaded.window(days[2], days[2])["session_date"].tolist() == [days[2]] * 2
