"""The feature table: the universe (or the instruments asked for) x catalogue columns for
exactly the session, filtered and sorted over the whole population, paged, each cell a value or
the UNKNOWN code saying why; never an older partition's value."""

from datetime import timedelta
from typing import Any

import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import NotFoundError, ReadContext
from algotrade.services.read.instruments import table
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.instruments.table import UniverseFilter, load_table
from algotrade.services.read.values import UnknownCode
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.read.instruments.conftest import D0, D1, PRICE, context, store_with

CLOSE = "rollup.price_stats@v2.close"
HV20 = "rollup.price_stats@v2.hv20"
NEXT = "rollup.earnings@v1.next_earnings_date"
SECTOR = "instrument.sector"


def _universe(writer: StoreWriter) -> None:
    rows = [
        {"instrument_id": i, "symbol": s, "security_type": t, "optionable": o,
         "status": "ACTIVE", "universe_version": "v1"}
        for i, s, t, o in (("EQ:AAA", "AAA", "COMMON_STOCK", True),
                           ("EQ:ETFX", "ETFX", "ETF", False))
    ]  # fmt: skip
    write_rows(writer, "universe", D0, rows)


@pytest.fixture
def ctx() -> ReadContext:
    """The latest session (D1) of the instruments store with a universe snapshot on D0."""
    return context(store_with(_universe))


def _cells(ctx: ReadContext, **kwargs: object) -> list[tuple[str, list[object]]]:
    found = load_table(ctx, **kwargs)  # type: ignore[arg-type]
    return [(i.symbol, list(r)) for i, r in zip(found.instruments, found.rows, strict=True)]


def test_the_universe_for_exactly_the_session(ctx: ReadContext) -> None:
    found = load_table(ctx, [CLOSE, NEXT, SECTOR])
    assert (found.session.date, found.universe_snapshot, found.pre_snapshot) == (D1, D0, False)
    assert [c.name for c in found.columns] == [CLOSE, NEXT, SECTOR]
    assert [i.symbol for i in found.instruments] == ["AAA", "ETFX"]  # by symbol
    assert found.rows == ((51.0, None, "Technology"), (None, None, None))
    assert found.unknown == (
        (None, UnknownCode.NO_PARTITION, None),  # earnings@v1 has D0 only: never shown
        (UnknownCode.NO_ROW, UnknownCode.NO_PARTITION, UnknownCode.NULL),
    )
    assert (found.total, found.page, found.size, found.sort) == (2, 1, 100, "symbol")
    assert NEXT.removeprefix("rollup.") not in found.session.present


def test_filters_read_catalogue_fields_over_the_population(ctx: ReadContext) -> None:
    def symbols(f: UniverseFilter) -> list[str]:
        return [i.symbol for i in load_table(ctx, [], f).instruments]

    assert symbols(UniverseFilter(security_type="etf")) == ["ETFX"]
    assert symbols(UniverseFilter(sector="technology")) == ["AAA"]
    assert symbols(UniverseFilter(q="x fund")) == ["ETFX"]  # name contains
    assert symbols(UniverseFilter(q=" aa ")) == ["AAA"]  # symbol contains
    assert symbols(UniverseFilter(leveraged=True)) == []  # not known: never passes
    assert symbols(UniverseFilter(sector="Energy")) == []


def test_sorted_server_side_missing_values_last_then_paged(ctx: ReadContext) -> None:
    assert _cells(ctx, columns=[CLOSE], sort="-symbol") == [("ETFX", [None]), ("AAA", [51.0])]
    # ETFX has no close for D1: last whichever the direction.
    assert [s for s, _ in _cells(ctx, columns=[], sort=CLOSE)] == ["AAA", "ETFX"]
    assert [s for s, _ in _cells(ctx, columns=[], sort=f"-{CLOSE}")] == ["AAA", "ETFX"]
    second = load_table(ctx, [CLOSE], size=1, page=2)
    assert ([i.symbol for i in second.instruments], second.total) == (["ETFX"], 2)
    assert load_table(ctx, [CLOSE], size=1, page=3).instruments == ()


def test_keys_in_the_order_asked(ctx: ReadContext) -> None:
    found = load_table(ctx, [CLOSE], keys=["ETFX", "EQ:AAA", "AAA"])
    assert [i.symbol for i in found.instruments] == ["ETFX", "AAA"]
    assert (found.sort, found.universe_snapshot) == (None, None)
    assert found.unknown == ((UnknownCode.NO_ROW,), (None,))
    with pytest.raises(NotFoundError, match="NOPE"):
        load_table(ctx, [CLOSE], keys=["NOPE"])


def test_an_unknown_column_or_sort_is_an_error(ctx: ReadContext) -> None:
    with pytest.raises(UnknownFeatureError, match=r"rollup\.nope@v1\.x"):
        load_table(ctx, ["rollup.nope@v1.x"])
    with pytest.raises(UnknownFeatureError, match=r"feature\.nope"):
        load_table(ctx, [], sort="-feature.nope")


def test_no_universe_or_nothing_stored_is_an_empty_table(reader: StoreReader) -> None:
    bare = load_table(context(reader), [CLOSE])  # no universe snapshot stored
    assert (bare.instruments, bare.total, bare.universe_snapshot) == ((), 0, None)
    before = load_table(context(store_with(_universe), D0.replace(day=1)), [HV20])
    assert before.total == 2 and before.pre_snapshot  # the earliest snapshot, disclosed
    assert before.unknown[0] == (UnknownCode.NO_PARTITION,)


def test_company_facts_from_a_later_snapshot_never_filter_or_sort() -> None:
    early = context(store_with(_universe), D0.replace(day=1))  # company snapshot is D0's
    tech = load_table(early, [SECTOR], UniverseFilter(sector="Technology"))
    assert (tech.total, tech.missing) == (0, ("instruments/company",))
    by_sector = load_table(early, [SECTOR], sort=f"-{SECTOR}")
    assert [i.symbol for i in by_sector.instruments] == ["AAA", "ETFX"]  # all null: by symbol
    assert by_sector.unknown == ((UnknownCode.NO_PARTITION,), (UnknownCode.NO_PARTITION,))
    assert load_table(context(store_with(_universe)), [SECTOR]).missing == ()


def test_one_order_per_query_until_the_next_publish(monkeypatch: pytest.MonkeyPatch) -> None:
    reader = store_with(_universe)
    calls: list[int] = []
    real = table.field_view

    def counting(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(table, "field_view", counting)
    ctx = context(reader)
    first = load_table(ctx, [CLOSE], sort=f"-{CLOSE}", size=1, page=1)
    second = load_table(ctx, [CLOSE], sort=f"-{CLOSE}", size=1, page=2)
    assert len(calls) == 1  # the second page is sliced from the cached order
    assert [i.symbol for i in (*first.instruments, *second.instruments)] == ["AAA", "ETFX"]
    load_table(ctx, [CLOSE], UniverseFilter(security_type="ETF"), sort=f"-{CLOSE}")
    assert len(calls) == 2  # filters are part of the query
    rows = [{"instrument_id": i, "close": c, "hv20": 0.1, "high_52w": 1.0, "low_52w": 1.0}
            for i, c in (("EQ:AAA", 51.0), ("EQ:ETFX", 99.0))]  # fmt: skip
    later_ts = T0 + timedelta(minutes=1)
    backend = reader._backend  # type: ignore[attr-defined]
    frame = stamped(rows, D1, "ps-new", later_ts)  # a later revision of D1
    StoreWriter(backend).write_table(PRICE, D1, "ps-new", frame, pending=True)
    assert [i.symbol for i in load_table(ctx, [CLOSE], sort=f"-{CLOSE}").instruments] == [
        "AAA",
        "ETFX",
    ]  # fmt: skip  (pending: not visible, the cached order stands)
    backend.tables.commit_run("ps-new", later_ts)
    later = load_table(ctx, [CLOSE], sort=f"-{CLOSE}")
    assert [i.symbol for i in later.instruments] == ["ETFX", "AAA"]  # a publish: recomputed
    assert later.rows == ((99.0,), (51.0,))
