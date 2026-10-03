"""Builders for the IBKR enrichment tasks: a store with a universe (every name optionable)
and its reference, and an ``IbkrSource`` over a ``FakeIB``."""

from datetime import date

from algotrade.data import StoreReader
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from algotrade_sources.vendors.ibkr.gateway import GatewayConfig, IbkrMarketData
from algotrade_sources.vendors.ibkr.market_data import IbkrSource
from tests.helpers.fake_ib import FakeIB
from tests.helpers.stored_frames import reference_rows, stamped, universe_rows

SESSION = date(2026, 10, 2)


def write_coverage(writer: StoreWriter, symbols: list[str], session: date = SESSION) -> None:
    """A universe snapshot and its reference: ``EQ:<symbol>`` for each, all optionable."""
    universe = universe_rows(symbols)
    writer.write_table("universe", session, "u", stamped(universe, session, "u"))
    rows = stamped(reference_rows(universe), session, "r")
    writer.write_table("instruments/reference", session, "r", rows)


def coverage_store(symbols: list[str], session: date = SESSION) -> tuple[StoreWriter, StoreReader]:
    backend = MemoryBackend()
    writer, reader = StoreWriter(backend), StoreReader(backend)
    write_coverage(writer, symbols, session)
    return writer, reader


def ibkr_source(fake: FakeIB, stream_wait_s: float = 4.0) -> IbkrSource:
    config = GatewayConfig("127.0.0.1", 4002, 1, stream_wait_s=stream_wait_s)
    return IbkrSource(IbkrMarketData(config, ib_factory=lambda: fake))
