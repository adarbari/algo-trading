"""Instrument identity for the session: by id or ticker, from the reference snapshot the
session sees (disclosed), the company name before the listing's, the latest description."""

from datetime import date

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.instruments.identity import load_instrument, resolve_id
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from tests.unit.services.read.instruments.conftest import D0, D1


def test_an_instrument_by_ticker_or_id_from_the_snapshot_the_session_sees(
    ctx: ReadContext,
) -> None:
    assert ctx.session.date == D1
    found = load_instrument(ctx, "aaa")  # tickers resolve case-insensitively
    assert found is not None
    assert found == load_instrument(ctx, "EQ:AAA")
    assert (found.instrument_id, found.symbol, found.name) == ("EQ:AAA", "AAA", "AAA Holdings")
    assert (found.security_type, found.asset_class, found.exchange) == (
        "COMMON_STOCK",
        "EQ",
        "NASDAQ",
    )
    assert (found.is_etf, found.description) == (False, "AAA makes widgets.")
    assert found.reference_snapshot == D0  # the snapshot on or before D1, disclosed


def test_an_etf_without_company_or_description_uses_the_listing(ctx: ReadContext) -> None:
    found = load_instrument(ctx, "ETFX")
    assert found is not None
    assert (found.name, found.is_etf, found.description) == ("X Fund ETF", True, None)


def test_an_unknown_key_is_no_instrument(ctx: ReadContext) -> None:
    assert resolve_id(ctx, "ZZZ") is None
    assert load_instrument(ctx, "EQ:ZZZ") is None


def test_no_reference_stored_is_no_instrument() -> None:
    empty = open_context(StoreReader(MemoryBackend()), MemoryConfigStore({}), UserContext("u"), D1)
    assert load_instrument(empty, "AAA") is None


def test_descriptions_are_read_once_per_publish(ctx: ReadContext, reader: StoreReader) -> None:
    load_instrument(ctx, "AAA")
    key = ("descriptions", reader.visible_seq())
    assert ctx.cache.get(key) is not None


def test_a_company_snapshot_taken_after_the_session_never_names_it(reader: StoreReader) -> None:
    before = open_context(reader, MemoryConfigStore({}), UserContext("u"), date(2026, 9, 29))
    found = load_instrument(before, "AAA")
    assert found is not None and found.name == "AAA COMMON STOCK"  # the listing's name
