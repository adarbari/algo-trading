"""The feature table: the universe (or the instruments asked for) x catalogue columns for
exactly the session, filtered and sorted over the whole population, paged, each cell a value or
the UNKNOWN code saying why; never an older partition's value."""

from datetime import timedelta
from typing import Any

import pytest

from algotrade.config.user import UserContext
from algotrade.data import StoreReader
from algotrade.services.read.context import NotFoundError, ReadContext, open_context
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.instruments import table
from algotrade.services.read.instruments.catalogue import UnknownFeatureError
from algotrade.services.read.instruments.table import UniverseFilter, load_table
from algotrade.services.read.values import UnknownCode
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.helpers.stored_frames import T0, stamped
from tests.unit.services.read.instruments.conftest import (
    D0,
    D1,
    FILTERS,
    IBKR,
    IBKR_IV30,
    PRICE,
    USERS,
    context,
    store_with,
)

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
    assert len(calls) == 2  # the filter pass and the sort read; the second page is sliced
    assert [i.symbol for i in (*first.instruments, *second.instruments)] == ["AAA", "ETFX"]
    load_table(ctx, [CLOSE], UniverseFilter(security_type="ETF"), sort=f"-{CLOSE}")
    assert len(calls) > 2  # filters are part of the query
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


def test_a_sort_or_filter_on_a_withheld_field_orders_nothing_by_its_values() -> None:
    """Fix for: sorting a table by a personal-licence column leaked the order of its values."""
    from tests.unit.services.read.instruments.conftest import (  # noqa: PLC0415
        IBKR_IV30,
        context_as,
        with_ibkr,
    )

    reader = store_with(_universe, with_ibkr)
    sorted_by = lambda user: load_table(context_as(reader, user), [IBKR_IV30], sort=f"-{IBKR_IV30}")  # noqa: E731
    holder, trader = sorted_by("owner"), sorted_by("trader")
    assert holder.instruments[0].instrument_id == "EQ:AAA"  # the only value, first
    assert [i.instrument_id for i in trader.instruments] == sorted(
        i.instrument_id for i in trader.instruments
    )  # ties by symbol: no value moved AAA
    assert trader.rows == ((None,),) * len(trader.rows)
    assert {u for row in trader.unknown for u in row} == {UnknownCode.LICENCE}
    assert holder.rows[0] == (0.42,)


# ---------------------------------------------------------------------- filters (ADR 0082)
IV_FILTER = {
    "id": "iv", "label": "IV", "group": "tradeable", "kind": "range", "field": IBKR_IV30,
    "bins": [0, 0.5, 1], "guide": "term:filter_spread",
}  # fmt: skip


def _with_iv(ctx_user: str, value: float) -> ReadContext:
    """``ctx_user`` over a store whose AAA has ``iv30_ibkr`` = ``value``, with an IV filter."""

    def write(w: StoreWriter) -> None:
        write_rows(w, IBKR, D1, [{"instrument_id": "EQ:AAA", "iv30_ibkr": value}])

    reader = store_with(_universe, write)
    shipped = FILTERS[("site", "filters", "universe")]
    docs = {
        ("site", "filters", "universe"): {**shipped, "filter": [*shipped["filter"], IV_FILTER]},
        ("site", "settings", "users"): USERS,
    }
    return open_context(reader, MemoryConfigStore(docs), UserContext(ctx_user))


def _symbols(found: Any) -> list[str]:
    return [i.symbol for i in found.instruments]


def test_filters_narrow_the_whole_universe_before_it_is_paged(ctx: ReadContext) -> None:
    only = [FilterInput("price", min=0)]
    page = load_table(ctx, [CLOSE], page=1, size=1, inputs=only)
    assert (_symbols(page), page.total) == (["AAA"], 1)  # ETFX has no close: UNKNOWN never passes
    assert page.facets is not None and (page.facets.total, page.facets.matched) == (2, 1)
    [price] = [f for f in page.facets.items if f.id == "price"]
    assert (price.unknown, price.removes) == (1, 1)
    assert load_table(ctx, [CLOSE], inputs=only, page=2, size=1).instruments == ()
    plain = load_table(ctx, [CLOSE])
    assert plain.facets is not None and plain.facets.matched == plain.total == 2


def test_the_old_arguments_equal_the_filters_they_map_onto(ctx: ReadContext) -> None:
    pairs = [
        (UniverseFilter(security_type="etf"), [FilterInput("security_type", ["ETF"])]),
        (UniverseFilter(sector="technology"), [FilterInput("sector", ["Technology"])]),
        (UniverseFilter(optionable=False), [FilterInput("optionable", ["no"])]),
        (UniverseFilter(optionable=True), [FilterInput("optionable", ["yes"])]),
        (UniverseFilter(leveraged=True), [FilterInput("leveraged", ["yes"])]),
        (
            UniverseFilter(security_type="COMMON_STOCK", optionable=True),
            [FilterInput("security_type", ["COMMON_STOCK"]), FilterInput("optionable", ["yes"])],
        ),
    ]
    for old, new in pairs:
        assert load_table(ctx, [CLOSE], old) == load_table(
            ctx, [CLOSE], None, None, 1, 100, None, new
        )
    assert _symbols(load_table(ctx, [], UniverseFilter(optionable=False))) == ["ETFX"]  # no null
    with pytest.raises(FilterRefusedError, match="twice"):
        load_table(ctx, [], UniverseFilter(sector="Energy"), inputs=[FilterInput("sector")])


def test_a_search_comes_after_the_filters_and_the_counts_are_of_the_universe(
    ctx: ReadContext,
) -> None:
    page = load_table(ctx, [], UniverseFilter(q="x"), inputs=[FilterInput("price", min=0)])
    assert page.total == 0 and page.facets is not None
    assert (page.facets.total, page.facets.matched) == (2, 1)  # q is no filter
    assert _symbols(
        load_table(ctx, [], UniverseFilter(q="aa"), inputs=[FilterInput("price", min=0)])
    ) == ["AAA"]


def test_keys_carry_facets_only_when_a_filter_is_set(ctx: ReadContext) -> None:
    assert load_table(ctx, [CLOSE], keys=["AAA", "ETFX"]).facets is None
    off = [FilterInput("price", min=1, active=False), FilterInput("sector")]  # sets nothing
    assert load_table(ctx, [CLOSE], keys=["AAA", "ETFX"], inputs=off).facets is None
    found = load_table(ctx, [CLOSE], keys=["AAA", "ETFX"], inputs=[FilterInput("price", min=0)])
    assert _symbols(found) == ["AAA"] and found.facets is not None and found.facets.total == 2


def test_a_gap_is_disclosed_only_for_the_tables_of_a_set_filter() -> None:
    early = context(store_with(_universe), D0.replace(day=1))  # the company snapshot is D0's
    assert load_table(early, [SECTOR]).missing == ()  # the facets read it: no disclosure
    found = load_table(early, [], inputs=[FilterInput("sector", ["Technology"])])
    assert (found.total, found.missing) == (0, ("instruments/company",))


def test_a_new_sort_or_search_reuses_the_filter_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(store_with(_universe))
    calls: list[int] = []
    real = table.field_view
    monkeypatch.setattr(table, "field_view", lambda *a, **k: calls.append(1) or real(*a, **k))
    load_table(ctx, [CLOSE], inputs=[FilterInput("price", min=0)])
    after_first = len(calls)
    load_table(
        ctx, [CLOSE], UniverseFilter(q="a"), sort="-symbol", inputs=[FilterInput("price", min=0)]
    )
    assert len(calls) == after_first + 1  # only the sort / search read; the pass is cached


def test_a_filter_the_viewer_is_not_offered_is_refused() -> None:
    with pytest.raises(FilterRefusedError):
        load_table(_with_iv("trader", 0.3), [], inputs=[FilterInput("iv", min=0.1)])
    assert _symbols(
        load_table(_with_iv("owner", 0.3), [], inputs=[FilterInput("iv", min=0.1)])
    ) == ["AAA"]


def test_changing_a_hidden_licence_fields_values_changes_no_count() -> None:
    """The leak test: stores differing only in the stored ``iv30_ibkr``; the viewer without the
    personal licence reads the same page and facets from both, with every offered filter set."""
    given = [FilterInput("price", min=0), FilterInput("security_type", ["COMMON_STOCK"])]
    shapes = [load_table(_with_iv("trader", v), [CLOSE], inputs=given) for v in (0.05, 0.95)]
    assert shapes[0] == shapes[1] and shapes[0].facets is not None
    assert all(f.id != "iv" for f in shapes[0].facets.items)
    totals = [
        load_table(_with_iv("owner", v), [], inputs=[FilterInput("iv", min=0.5)]).total
        for v in (0.05, 0.95)
    ]
    assert totals == [0, 1]  # the holder of the licence reads the values
