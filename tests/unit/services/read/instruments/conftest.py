"""A small store for the instrument read objects: two sessions with bars (D0, D1), the
reference and company snapshots taken on D0 only (so a read for D1 sees D0's), a description,
``price_stats@v2`` for both sessions (D1: AAA only, ``hv20`` null) and ``earnings@v1`` only on
D0 (an older partition a D1 read must never show)."""

from datetime import date

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows

D0, D1 = date(2026, 9, 30), date(2026, 10, 1)
PRICE = "rollups/instrument/price_stats@v2"
EARNINGS = "rollups/instrument/earnings@v1"


def _reference(writer: StoreWriter) -> None:
    rows = [
        {"instrument_id": "EQ:AAA", "symbol": "AAA", "name": "AAA COMMON STOCK",
         "asset_class": "EQ", "security_type": "COMMON_STOCK", "exchange": "NASDAQ",
         "multiplier": 1.0, "status": "ACTIVE", "is_etf": False},
        {"instrument_id": "EQ:ETFX", "symbol": "ETFX", "name": "X Fund ETF", "asset_class": "EQ",
         "security_type": "ETF", "exchange": "NYSE_ARCA", "multiplier": 1.0, "status": "ACTIVE",
         "is_etf": True},
    ]  # fmt: skip
    write_rows(writer, "instruments/reference", D0, rows)
    company = {"instrument_id": "EQ:AAA", "symbol": "AAA", "cik": "1", "name": "AAA Holdings",
               "sic": "3571", "sector": "Technology", "fetched_on": D0}  # fmt: skip
    write_rows(writer, "instruments/company", D0, [company])
    text = {"instrument_id": "EQ:AAA", "symbol": "AAA", "description": " AAA makes widgets. ",
            "description_source": "massive_overview", "fetched_on": D0}  # fmt: skip
    write_rows(writer, "instruments/description", D0, [text])


def _market(writer: StoreWriter) -> None:
    for day in (D0, D1):
        bar = {"open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}
        row = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), **bar}
        write_rows(writer, "bars/1d", day, [row])
    old = [{"instrument_id": i, "close": 50.0, "hv20": 0.3, "high_52w": 60.0, "low_52w": 40.0}
           for i in ("EQ:AAA", "EQ:ETFX")]  # fmt: skip
    write_rows(writer, PRICE, D0, old)
    now = {"instrument_id": "EQ:AAA", "close": 51.0, "hv20": None, "high_52w": 60.0,
           "low_52w": 40.0}  # fmt: skip
    write_rows(writer, PRICE, D1, [now])
    earnings = {"instrument_id": "EQ:AAA", "next_earnings_date": D1, "days_to_earnings": 1}
    write_rows(writer, EARNINGS, D0, [earnings])


@pytest.fixture
def reader() -> StoreReader:
    backend = MemoryBackend()
    writer = StoreWriter(backend)
    _reference(writer)
    _market(writer)
    return StoreReader(backend)


@pytest.fixture
def ctx(reader: StoreReader) -> ReadContext:
    """The read context for the latest session, D1."""
    return open_context(reader, MemoryConfigStore({}), UserContext("local"))
