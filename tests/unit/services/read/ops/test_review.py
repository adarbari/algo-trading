"""The owner's review lists: the FIGI list from the latest universe build's record, else the
session's reference snapshot; the leveraged ETFs to classify."""

from datetime import UTC, date, datetime

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.explore.store import ReadStore
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.ops.review import load_figi_review, load_leverage_review
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import start_run
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped

REFERENCE = "instruments/reference"
D1, D2 = date(2026, 10, 1), date(2026, 10, 2)
NOW = datetime(2026, 10, 3, 2, tzinfo=UTC)


def _golden(explore: tuple[ReadStore, dict[str, str]]) -> ReadContext:
    store = explore[0]
    return open_context(store.reader, store.configs, store.user)


def test_figi_review_from_the_universe_build(explore: tuple[ReadStore, dict[str, str]]) -> None:
    found = load_figi_review(_golden(explore))
    assert found.source.startswith("universe_build-")
    assert [r["symbol"] for r in found.items] == ["BBB"]


def test_leverage_review(explore: tuple[ReadStore, dict[str, str]]) -> None:
    found = load_leverage_review(_golden(explore))
    assert [r["symbol"] for r in found.items] == ["CCC"]
    assert set(found.items[0]) == {"symbol", "instrument_id", "name", "security_type", "exchange"}
    assert found.source == "instruments/reference" and found.session is not None


def test_an_empty_store_has_nothing_to_review() -> None:
    reader = StoreReader(MemoryBackend())
    ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), date(2026, 10, 2))
    for found in (load_figi_review(ctx), load_leverage_review(ctx)):
        assert (found.session, found.items) == (None, ())


def test_figi_review_never_reads_a_later_build() -> None:
    backend = MemoryBackend()
    for day, symbol in ((D1, "OLD"), (D2, "NEW")):
        run = start_run("universe_build", day, NOW)
        run.stats = {"figi_review": [{"symbol": symbol}]}
        backend.runs.save(run.finish(NOW))
    reader = StoreReader(backend)
    for day, symbol in ((D1, "OLD"), (D2, "NEW"), (date(2026, 10, 5), "NEW")):
        ctx = open_context(reader, MemoryConfigStore({}), UserContext("local"), day)
        found = load_figi_review(ctx)
        assert [r["symbol"] for r in found.items] == [symbol]
    early = open_context(reader, MemoryConfigStore({}), UserContext("local"), date(2026, 9, 1))
    assert load_figi_review(early).source == REFERENCE  # no build on or before: the snapshot


def test_figi_review_falls_back_to_the_marked_reference_rows() -> None:
    backend = MemoryBackend()
    rows = [
        {"instrument_id": f"EQ:{s}", "symbol": s, "status": status, "vendor_figi": figi,
         "asset_class": "EQ", "security_type": "COMMON_STOCK", "multiplier": 1.0}
        for s, status, figi in (
            ("ZZZ", "ACTIVE", "BBG1"), ("AAA", "ACTIVE", None), ("OLD", "DELISTED", "BBG2"),
        )
    ]  # fmt: skip
    StoreWriter(backend).write_table(REFERENCE, D1, "ref", stamped(rows, D1, "ref"))
    ctx = open_context(StoreReader(backend), MemoryConfigStore({}), UserContext("local"), D2)
    found = load_figi_review(ctx)
    assert (found.session, found.source) == (D1, REFERENCE)  # the snapshot the session sees
    assert found.items == (
        {"symbol": "ZZZ", "instrument_id": "EQ:ZZZ", "figi": None, "vendor_figi": "BBG1",
         "figi_review_since": None},
    )  # fmt: skip
    assert load_leverage_review(ctx).items == ()  # no leverage classification stored
