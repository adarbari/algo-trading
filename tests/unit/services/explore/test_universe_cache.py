"""The universe join is cached per (query, user catalogue, published state): pages come from
one computed frame, equal the uncached rows, and a new publish invalidates (ADR 0022)."""

from datetime import timedelta

import pytest

from algotrade.services.explore import universe
from algotrade.services.explore.store import ReadStore, ResultCache
from algotrade.services.explore.universe import UniverseFilter, ticker_table, universe_page
from algotrade.storage.tables.writers import StoreWriter
from algotrade_sources.framework.base import FixtureSource
from tests.helpers.api_store import END, SYMBOLS, api_store
from tests.helpers.stored_frames import T0, stamped

CLOSE = "rollup.price_stats@v2.close"
TABLE = "rollups/instrument/price_stats@v2"


@pytest.fixture
def store(golden_source: FixtureSource) -> ReadStore:
    return api_store(golden_source)[0]


def compute_counter(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    calls: list[int] = []
    real = universe._universe

    def counting(*args, **kwargs):  # type: ignore[no-untyped-def]
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(universe, "_universe", counting)
    return calls


def rows(table: object) -> list[dict[str, object]]:
    return table.page.items  # type: ignore[attr-defined,no-any-return]


def test_pages_come_from_one_join_and_equal_uncached(
    store: ReadStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = compute_counter(monkeypatch)
    f = UniverseFilter()
    paged = [ticker_table(store, None, f, [CLOSE], f"-{CLOSE}", p, 1) for p in (1, 2, 3, 4)]
    assert len(calls) == 1
    cold = ReadStore(store.reader, store.configs, store.user)  # no shared cache
    whole = ticker_table(cold, None, f, [CLOSE], f"-{CLOSE}", 1, 1000)
    assert [r for t in paged for r in rows(t)] == rows(whole)
    assert paged[0].missing == whole.missing and paged[0].session == whole.session
    assert (
        universe_page(store, None, f, 1, 2).page.items
        == rows(universe_page(cold, None, f, 1, 1000))[:2]
    )
    before = len(calls)
    universe_page(store, None, f, 2, 2)
    assert len(calls) == before  # one join per query shape, not per page


def test_filters_and_columns_are_part_of_the_key(store: ReadStore) -> None:
    every = ticker_table(store, None, UniverseFilter(), [CLOSE], None, 1, 1000)
    levered = ticker_table(store, None, UniverseFilter(leveraged=True), [CLOSE], None, 1, 1000)
    bare = ticker_table(store, None, UniverseFilter(), [], None, 1, 1000)
    assert [r["symbol"] for r in rows(levered)] == ["BULL"]
    assert len(rows(every)) == len(SYMBOLS) and CLOSE not in rows(bare)[0]


def test_a_new_publish_invalidates(store: ReadStore) -> None:
    f = UniverseFilter()
    before = rows(ticker_table(store, None, f, [CLOSE], "symbol", 1, 1000))
    assert rows(ticker_table(store, None, f, [CLOSE], "symbol", 1, 1000)) == before
    seq = store.reader.visible_seq()
    later = T0 + timedelta(minutes=1)
    frame = stamped(
        [{"instrument_id": f"EQ:{s}", "close": 500.0} for s in SYMBOLS], END, "ps-new", later
    ).astype({"close": "float32"})
    backend = store.reader._backend  # type: ignore[attr-defined]
    StoreWriter(backend).write_table(TABLE, END, "ps-new", frame, pending=True)
    assert store.reader.visible_seq() == seq  # pending: nothing changes yet
    assert rows(ticker_table(store, None, f, [CLOSE], "symbol", 1, 1000)) == before
    backend.tables.commit_run("ps-new", later)
    after = rows(ticker_table(store, None, f, [CLOSE], "symbol", 1, 1000))
    assert after != before and {r[CLOSE] for r in after} == {500.0}


def test_the_cache_is_bounded() -> None:
    cache = ResultCache(size=2)
    for key in "abc":
        cache.put(key, key)
    assert cache.get("a") is None and cache.get("c") == "c"
