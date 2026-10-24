"""The edge trade ledger through the shared filters (ADR 0082, surface ``edge_trades``): filters
apply to the whole ledger before it is sorted and paged, the older ``period`` is the same read
mapped onto the ``record`` / ``in_sample`` filters, and a value the viewer's licence hides never
passes a filter and is never counted."""

import tomllib
from typing import Any

import pytest

from algotrade.services.read.edge_ledger.trades import (
    EdgeTradePage,
    Period,
    load_edge_trades,
    load_filtered_trades,
    load_trades_page,
)
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.storage.backends.memory import MemoryBackend
from tests.conftest import REPO_ROOT
from tests.unit.services.read.edge_desk.conftest import CUTOFF, KNOWN, store, trade
from tests.unit.services.read.edge_ledger.conftest import LEDGER, context, pick
from tests.unit.services.read.edge_ledger.test_trades import EVIDENCED, edge_of
from tests.unit.services.read.evaluation.conftest import FROZEN, write_run

SHIPPED = tomllib.loads((REPO_ROOT / "config/site/filters/edge_trades.toml").read_text())
DOCS = {("site", "filters", "edge_trades"): SHIPPED, **EVIDENCED}
SELL = FROZEN.replace(month=9, day=30)


@pytest.fixture
def backend() -> MemoryBackend:
    b = MemoryBackend()
    write_run(b, "site1", FROZEN, 0.6, trades=LEDGER)
    return b


def read(
    backend: MemoryBackend, user: str = "owner", period: Period | None = Period.ALL, **kw: Any
):
    ctx = context(backend, user, DOCS, cutoff=CUTOFF)
    kw.setdefault("page", 1)
    kw.setdefault("sort", None)
    kw.setdefault("descending", False)
    kw.setdefault("filters", ())
    return load_filtered_trades(ctx, edge_of(ctx), period, **kw)


def ids(page: EdgeTradePage) -> list[str]:
    return [r.instrument_id for r in page.rows]


@pytest.mark.parametrize("period", list(Period))
@pytest.mark.parametrize("sort", [None, "value", "decision_session", "status", "adv_usd"])
@pytest.mark.parametrize("descending", [False, True])
def test_a_period_alone_is_the_same_read_as_before(
    backend: MemoryBackend, period: Period, sort: str | None, descending: bool
) -> None:
    store(backend, [trade("EQ:L", FROZEN.replace(month=9, day=1), "won", sell=SELL)], KNOWN)
    ctx = context(backend, "owner", DOCS, cutoff=CUTOFF)
    old = load_edge_trades(ctx, edge_of(ctx), period, 1, sort, descending)
    new = read(backend, period=period, sort=sort, descending=descending)
    assert (ids(new), new.total, new.unknown, new.oos_hidden) == (
        ids(old), old.total, old.unknown, old.oos_hidden
    )  # fmt: skip


def test_filters_narrow_the_whole_ledger_before_it_is_paged(backend: MemoryBackend) -> None:
    out = read(backend, filters=[FilterInput("in_sample", ["no"])], limit=1, page=2)
    assert ids(out) == ["EQ:D"] and out.total == 2  # C and D match; the 2nd page of 1
    assert out.facets is not None and out.facets.total == 4 and out.facets.matched == 2


def test_the_result_pick_and_the_return_range(backend: MemoryBackend) -> None:
    assert ids(read(backend, filters=[FilterInput("result", ["lost"])])) == ["EQ:D"]
    gained = read(backend, filters=[FilterInput("return", min=0)])
    assert ids(gained) == ["EQ:A", "EQ:B"]  # C has no return (UNKNOWN), D lost


def test_unknown_never_passes_and_is_counted_apart(backend: MemoryBackend) -> None:
    found = read(backend, filters=[FilterInput("return", min=-1)])
    assert "EQ:C" not in ids(found)  # an excluded pick has no return: not 0, not passing
    facet = next(f for f in found.facets.items if f.id == "return")  # type: ignore[union-attr]
    assert facet.unknown == 1


def test_a_value_the_viewer_may_not_see_never_passes_or_counts() -> None:
    b = MemoryBackend()
    ledger = [*LEDGER[:1], pick(LEDGER[1]["decision_session"], "EQ:A", 1, True,
                                adv_usd_20d=9e9, adv_licence="personal")]  # fmt: skip
    write_run(b, "site1", FROZEN, 0.6, trades=ledger)
    held = read(b, "owner", filters=[FilterInput("adv", min=1e9)])
    assert ids(held) == ["EQ:A"]
    barred = read(b, "me", filters=[FilterInput("adv", min=1e9)])
    assert ids(barred) == []  # the viewer's licence hides the figure: UNKNOWN, never passing
    facet = next(f for f in barred.facets.items if f.id == "adv")  # type: ignore[union-attr]
    assert sum(bin_.count for bin_ in facet.bins) == 1  # only the visible 1e7 row is counted
    assert facet.unknown == 1 and all(bin_.hi < 2e9 for bin_ in facet.bins if bin_.count)


def test_a_filter_sets_the_sort_after_it(backend: MemoryBackend) -> None:
    page = read(backend, filters=[FilterInput("in_sample", ["yes"])], sort="value", descending=True)
    assert ids(page) == ["EQ:B", "EQ:A"]


def test_a_viewers_record_filter_wins_over_the_default_period(backend: MemoryBackend) -> None:
    store(backend, [trade("EQ:L", FROZEN.replace(month=9, day=1), "won", sell=SELL)], KNOWN)
    live = read(backend, period=Period.ALL, filters=[FilterInput("record", ["live"])])
    assert ids(live) == ["EQ:L"]
    both = read(backend, period=None)
    assert ids(both) == ["EQ:A", "EQ:B", "EQ:C", "EQ:D", "EQ:L"] and both.total == 5


def test_a_filter_that_is_not_offered_is_refused_before_any_read(backend: MemoryBackend) -> None:
    with pytest.raises(FilterRefusedError):
        read(backend, filters=[FilterInput("nope", ["x"])])


def test_a_period_with_no_filters_and_no_counts_keeps_the_fast_read(backend: MemoryBackend) -> None:
    ctx = context(backend, "owner", DOCS, cutoff=CUTOFF)
    fast = load_trades_page(ctx, "drift", Period.ALL, 1, None, False)
    assert fast is not None and fast.facets is None and fast.total == 4
    counted = load_trades_page(ctx, "drift", Period.ALL, 1, None, False, (), True)
    assert counted is not None and counted.facets is not None and counted.total == 4
    assert load_trades_page(ctx, "nope", Period.ALL, 1, None, False) is None


def hidden_copy() -> tuple[Any, Any]:
    """A viewer's copy whose out-of-sample result is withheld: one in-sample and one
    out-of-sample row stored, only the first is ever served."""
    from algotrade.services.read.evaluation.edges import load_edge  # noqa: PLC0415
    from algotrade.storage.tables.result_writer import ResultWriter  # noqa: PLC0415
    from tests.helpers.stored_frames import stamped  # noqa: PLC0415
    from tests.unit.services.read.evaluation.conftest import END  # noqa: PLC0415
    from tests.unit.services.read.evaluation.test_versions import (  # noqa: PLC0415
        MOVED,
        write_own_run,
    )

    backend = MemoryBackend()
    write_own_run(backend)
    record = backend_run(backend)
    rows = [
        {**pick(FROZEN, "EQ:A", 1, True, edge_id="mine", split_from=MOVED), "user_id": "me"},
        {**pick(END, "EQ:Z", 1, False, edge_id="mine", split_from=MOVED), "user_id": "me"},
    ]
    frame = stamped(rows, END, "mine1", record.started_at, "edge-eval")
    writer = ResultWriter(backend)
    with writer.publishing("mine1", record.started_at):
        writer.write_result("edge_trades", END, "mine1", frame, pending=True)
        record.stats["ledger_rows"] = 2
        writer.save_run(record)
    docs = {**DOCS, ("me", "edges", "mine"): {"extends": "drift", "screeners": ["momo"]}}
    ctx = context(backend, "me", docs, cutoff=CUTOFF)
    edge = load_edge(ctx, "mine")
    assert edge is not None and edge.oos_hidden
    return ctx, edge


def backend_run(backend: MemoryBackend) -> Any:
    from tests.unit.services.read.edge_ledger.test_trades import run_record  # noqa: PLC0415

    return run_record(backend, "mine1")


def test_a_hidden_copys_withheld_trades_are_disclosed_whichever_filter_chose_the_rows() -> None:
    ctx, edge = hidden_copy()
    out = load_filtered_trades(ctx, edge, Period.OUT_OF_SAMPLE, 1, None, False, ())
    assert (out.rows, out.total, out.oos_hidden) == ((), 0, True)  # the old early return
    for period, filters in [
        (Period.ALL, ()),
        (None, ()),
        (Period.LIVE, [FilterInput("record", ["backtest"])]),  # a viewer's record beats `live`
        (Period.IN_SAMPLE, [FilterInput("in_sample", ["no"])]),  # and so does in_sample
    ]:
        page = load_filtered_trades(ctx, edge, period, 1, None, False, filters)
        assert page.oos_hidden, (period, filters)
    inside = load_filtered_trades(ctx, edge, Period.IN_SAMPLE, 1, None, False, ())
    assert ids(inside) == ["EQ:A"] and not inside.oos_hidden  # nothing was withheld from it
    out_but_filtered = load_filtered_trades(
        ctx, edge, Period.OUT_OF_SAMPLE, 1, None, False, [FilterInput("in_sample", ["no"])]
    )
    assert out_but_filtered.oos_hidden and out_but_filtered.facets is not None  # counts asked for
