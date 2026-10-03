from datetime import date

import pandas as pd
import pytest

from algotrade.core.errors import ConfigurationError
from algotrade.services.market_data import adjust_bars, load_price_data
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.readers import StoreReader
from algotrade.storage.writers import StoreWriter
from tests.storage_helpers import stamped

DAYS = [date(2026, 9, 28), date(2026, 9, 29), date(2026, 9, 30)]


def bars(closes: list[float], iid: str = "EQ:A") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "instrument_id": iid,
            "ts": [pd.Timestamp(d, tz="UTC") for d in DAYS],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [100.0] * len(closes),
        }
    )


SPLIT = pd.DataFrame(
    {"instrument_id": ["EQ:A"], "ts": [pd.Timestamp(DAYS[2], tz="UTC")], "ratio": [2.0]}
)
DIVIDEND = pd.DataFrame(
    {"instrument_id": ["EQ:A"], "ts": [pd.Timestamp(DAYS[1], tz="UTC")], "cash_amount": [1.0]}
)
NONE = pd.DataFrame(columns=["instrument_id", "ts"])


def test_split_adjustment_removes_the_jump() -> None:
    adjusted = adjust_bars(bars([100, 100, 50]), SPLIT, NONE, "splits")
    assert list(adjusted["close"]) == [50, 50, 50]
    assert list(adjusted["volume"]) == [200, 200, 100]
    assert adjust_bars(bars([100, 100, 50]), SPLIT, NONE, "none")["close"].tolist() == [
        100,
        100,
        50,
    ]
    other = adjust_bars(bars([100, 100, 50], "EQ:B"), SPLIT, NONE, "splits")
    assert other["close"].tolist() == [100, 100, 50]  # splits only touch their own instrument


def test_total_return_adds_dividends_on_the_unadjusted_basis() -> None:
    adjusted = adjust_bars(bars([100, 99, 49.5]), SPLIT, DIVIDEND, "total_return")
    # day 1 before the ex-date: x (1 - 1/100) for the dividend, / 2 for the split
    assert adjusted["close"].tolist() == pytest.approx([49.5, 49.5, 49.5])


def test_unknown_mode_is_rejected() -> None:
    with pytest.raises(ConfigurationError, match="price adjustment"):
        adjust_bars(bars([1, 1, 1]), NONE, NONE, "magic")


def test_load_price_data_applies_stored_events_and_records_versions() -> None:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    raw = bars([100, 100, 50])
    for day in DAYS:
        part = raw[raw["ts"].dt.date == day]
        writer.write_table(
            "bars/1d", day, f"b{day.day}", stamped(part.to_dict("records"), day, f"b{day.day}")
        )
    ref = [
        {
            "instrument_id": "EQ:A",
            "symbol": "A",
            "asset_class": "EQ",
            "security_type": "COMMON_STOCK",
            "multiplier": 1.0,
            "status": "ACTIVE",
        }
    ]
    writer.write_table("instruments/reference", DAYS[0], "ref", stamped(ref, DAYS[0], "ref"))
    split = [{"instrument_id": "EQ:A", "ts": pd.Timestamp(DAYS[2], tz="UTC"), "ratio": 2.0}]
    writer.write_table("events/split", DAYS[2], "ca", stamped(split, DAYS[2], "ca"))
    data = load_price_data(StoreReader(backend), ["EQ:A"], DAYS[0], DAYS[2])
    assert data.series["EQ:A"].close.tolist() == [50, 50, 50]
    assert data.versions["events/split"] == ["ca"]
    raw_prices = load_price_data(
        StoreReader(backend), ["EQ:A"], DAYS[0], DAYS[2], adjustment="none"
    )
    assert raw_prices.series["EQ:A"].close.tolist() == [100, 100, 50]
