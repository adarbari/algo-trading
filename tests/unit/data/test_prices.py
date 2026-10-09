from datetime import UTC, date, datetime

import pandas as pd
import pytest

from algotrade.core.model.errors import MissingDataError
from algotrade.data import StoreReader
from algotrade.data.prices import adjusted_bars, frame_to_series, load_price_data, session_bars
from algotrade.data.prices import bars as read_bars
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


# ------------------------------------------------------------------ flagged bars (ADR 0061)
FDAYS = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]
FLAGGED_DAY = FDAYS[1]
FLAG = ("f1", "FLAGGED", datetime(2026, 10, 5, 22, tzinfo=UTC))  # run, status, knowledge


def _flag_rows(status: str) -> list[dict[str, object]]:
    return [
        {
            "instrument_id": "EQ:A",
            "ts": pd.Timestamp(FLAGGED_DAY, tz="UTC"),
            "reason": "UNEXPLAINED_JUMP",
            "detail": "outside the trusted segment",
            "status": status,
        }
    ]


def _flagged_store(*flag_runs: tuple[str, str, datetime]) -> MemoryBackend:
    """Three stored daily bars of two instruments; ``flag_runs``: (run id, status, knowledge)."""
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    for i, day in enumerate(FDAYS):
        rows = [
            {"instrument_id": iid, "ts": pd.Timestamp(day, tz="UTC"), "open": c, "high": c,
             "low": c, "close": c, "volume": 100.0}
            for iid, c in (("EQ:A", 10.0 + i), ("EQ:B", 20.0))
        ]  # fmt: skip
        writer.write_table("bars/1d", day, f"b{i}", stamped(rows, day, f"b{i}"))
    for run_id, status, knowledge in flag_runs:
        flags = stamped(_flag_rows(status), FDAYS[-1], run_id, knowledge)
        writer.write_table("events/bar_flag", FDAYS[-1], run_id, flags)
    return backend


def test_session_bars_drops_flagged() -> None:
    reader = StoreReader(_flagged_store(FLAG))
    frame = read_bars(reader, "1d", FDAYS[0], FDAYS[2])
    assert sorted(zip(frame["instrument_id"], frame["session_date"], strict=True)) == sorted(
        [("EQ:A", FDAYS[0]), ("EQ:A", FDAYS[2]), *(("EQ:B", d) for d in FDAYS)]
    )
    adjusted, _ = adjusted_bars(reader, "1d", FDAYS[0], FDAYS[2])
    assert len(adjusted) == 5
    window = session_bars(reader, FDAYS[0], FDAYS[2])
    assert window.flagged == {("EQ:A", FLAGGED_DAY)}
    day = window.window(FDAYS[0], FDAYS[2])
    assert len(day[day["instrument_id"] == "EQ:A"]) == 2  # a missing bar, never a zero return
    assert (day["close"] > 0).all()


def test_flag_is_read_with_the_bars_as_of_and_a_later_clear_retracts_it() -> None:
    before = datetime(2026, 10, 4, tzinfo=UTC)  # the bars exist, the flag (10-05) not yet
    cleared = ("f2", "CLEARED", datetime(2026, 10, 6, 22, tzinfo=UTC))
    both = StoreReader(_flagged_store(FLAG, cleared))
    assert len(read_bars(both, "1d", FDAYS[0], FDAYS[2])) == 6  # the latest row: CLEARED
    only_flag = StoreReader(_flagged_store(FLAG))
    assert len(read_bars(only_flag, "1d", FDAYS[0], FDAYS[2], as_of=before)) == 6
    assert len(read_bars(only_flag, "1d", FDAYS[0], FDAYS[2])) == 5


def test_a_backtest_that_needs_a_flagged_bar_names_the_flag() -> None:
    reader = StoreReader(_flagged_store(FLAG))
    with pytest.raises(MissingDataError, match="UNEXPLAINED_JUMP") as raised:
        load_price_data(reader, ["EQ:A"], FDAYS[0], FDAYS[2])
    assert "EQ:A" in str(raised.value) and str(FLAGGED_DAY) in str(raised.value)
