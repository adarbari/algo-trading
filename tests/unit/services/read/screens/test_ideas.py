"""``load_ideas``: the viewer's screener pool ranked by the rule (services/ideas/rule.py), each
idea served from its best pick only; the licence rule, NOT_RUN, the PAUSED section, paging and the
filters (ADR 0082, PR 4: they narrow the whole list before it is paged, no count leaks a
hidden-licence field, UNKNOWN never passes, a cursor is only good for its filters). The filter
tests use a store with a later ``alpha`` run ``big`` of twelve picks ``S000``.. (dollar volume
stored for the first eight, days to earnings for the first six, a personal IV for all twelve:
the field of the leak tests)."""

import copy
from collections.abc import Callable
from datetime import timedelta

import pandas as pd
import pytest
from hypothesis import given as hypothesis_given
from hypothesis import settings
from hypothesis import strategies as st

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.filtering.definitions import FilterRefusedError
from algotrade.services.read.filtering.facets import Facets, FilterFacet
from algotrade.services.read.filtering.masks import FilterInput, WindowUnit, Within
from algotrade.services.read.filtering.served import load_served_filters
from algotrade.services.read.screens import results as results_module
from algotrade.services.read.screens import runs as runs_module
from algotrade.services.read.screens.ideas import (
    FIRST_PAGE,
    Ideas,
    display_metrics,
    load_ideas,
)
from algotrade.services.read.screens.runs import ScreenerRun
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.rollup_store import write_rows
from tests.unit.services.read.screens.conftest import (
    CONFIGS,
    D1,
    IDEAS_FILTERS,
    T,
    context,
    screens_store,
    write_big_run,
    write_gated,
)

OLD_PRIORITY = {("me", "preferences", "preferences"): {"ideas": {"priority": ["gamma", "nope"]}}}
WIDE = {("site", "ranking", "ideas"): {"site_top": 500, "user_top": 500}}  # no cap: paging tests


def _ids(found: Ideas) -> list[str]:
    return [i.instrument_id for i in found.items]


def test_ideas_are_ranked_by_their_best_pick_with_every_pick_listed(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert (ideas.session, ideas.total) == (D1, 3)
    # me's beta (weight 3): BBB 3, DDD 3 / 2; site alpha (weight 1): AAA 1, BBB 1 / 2
    assert _ids(ideas) == ["EQ:BBB", "EQ:DDD", "EQ:AAA"]
    first = ideas.items[0]
    assert first.rank == 1 and first.instrument is not None and first.instrument.symbol == "BBB"
    assert (first.score, first.best.config_id, first.best.decision) == (3.0, "beta", "QUALIFIED")
    assert [(p.config_id, p.own, p.position, p.score) for p in first.picked_by] == [
        ("beta", True, 1, 3.0), ("alpha", False, 2, 0.5)
    ]  # fmt: skip
    assert [i.score for i in ideas.items] == [3.0, 1.5, 1.0]


def test_a_stale_priority_preference_is_read_without_error_and_changes_nothing(
    reader: StoreReader, ctx: ReadContext
) -> None:
    assert _ids(load_ideas(context(reader, OLD_PRIORITY), 10)) == _ids(load_ideas(ctx, 10))


def test_the_users_screen_wins_over_the_preset_with_its_id(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert "EQ:CCC" not in _ids(ideas)  # the site's beta run (CCC 99) is not me's beta
    assert [(s.screener.id, s.screener.owner) for s in ideas.screeners] == [
        ("beta", "me"), ("gamma", "me"), ("alpha", "site")
    ]  # fmt: skip


def test_screeners_count_the_whole_run_and_say_not_run(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 1)  # one item shown; counts are over the run
    assert _ids(ideas) == ["EQ:BBB"] and ideas.total == 3
    by_id = {s.screener.id: s for s in ideas.screeners}
    alpha = by_id["alpha"]
    assert alpha.run is not None and alpha.run.run_id == "r1"
    assert (alpha.picked, alpha.not_run, alpha.withheld) == (2, None, False)
    assert [r.instrument_id for r in alpha.top] == ["EQ:AAA", "EQ:BBB"]  # its first pool picks
    gamma = by_id["gamma"]  # ran on D0 only: no lookback
    assert (gamma.run, gamma.picked, gamma.top) == (None, 0, ())
    assert gamma.not_run is not None and gamma.not_run.code is UnknownCode.NOT_RUN


def test_a_session_nothing_ran_for(reader: StoreReader) -> None:
    later = open_context(
        reader, MemoryConfigStore(CONFIGS), UserContext("me"), D1 + timedelta(days=1)
    )
    ideas = load_ideas(later, 10)
    assert (ideas.items, ideas.total) == ((), 0)
    assert all(s.not_run is not None for s in ideas.screeners)


def test_a_run_withheld_by_a_licence_contributes_nothing_and_is_listed(reader: StoreReader) -> None:
    # ``trader`` holds no personal licence: alpha's run read personal fields, so its rank would
    # leak the hidden values; the site's beta stored no values to tell its fields (withheld
    # whole). Neither is part of the pool; each is listed, with a count and no ranking.
    ideas = load_ideas(context(reader, user="trader"), 10)
    assert (ideas.items, ideas.total) == ((), 0)
    by_id = {s.screener.id: s for s in ideas.screeners}
    assert by_id["alpha"].withheld and by_id["alpha"].top == () and by_id["alpha"].picked == 2
    assert by_id["beta"].withheld and by_id["beta"].top == ()


def test_a_viewer_who_holds_the_licences_has_nothing_withheld(ctx: ReadContext) -> None:
    assert not any(s.withheld for s in load_ideas(ctx, 10).screeners)


def test_the_paused_section_follows_the_rule_and_is_no_idea(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ideas = load_ideas(context(reader), 10)
    assert _ids(ideas) == ["EQ:BBB", "EQ:DDD", "EQ:AAA"]  # a paused row picks nothing
    assert ideas.paused_total == 2
    assert [(p.instrument_id, p.result.config_id) for p in ideas.paused] == [
        ("EQ:BBB", "alpha"), ("EQ:DDD", "alpha")
    ]  # fmt: skip
    first = ideas.paused[0]
    assert first.result.decision == "PAUSED" and first.result.reasons == "regime=STRESS: alpha"
    assert first.instrument is not None and first.instrument.symbol == "BBB"
    alpha = next(s for s in ideas.screeners if s.screener.id == "alpha")
    assert alpha.picked == 1 and alpha.run is not None and alpha.run.paused == 2
    assert [r.instrument_id for r in alpha.top] == ["EQ:AAA"]  # a paused row is no top pick


def test_the_paused_section_is_capped_by_the_limit_but_counts_every_row(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ideas = load_ideas(context(reader), 1)
    assert ideas.paused_total == 2 and len(ideas.paused) == 1


def test_an_idea_carries_its_best_picks_regime_and_size(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    by_id = {i.instrument_id: i for i in load_ideas(context(reader), 10).items}
    assert (by_id["EQ:AAA"].regime, by_id["EQ:AAA"].size_multiplier) == ("STRESS", 0.5)
    assert (by_id["EQ:BBB"].regime, by_id["EQ:BBB"].size_multiplier) == (None, None)  # beta's


def test_no_paused_rows_is_an_empty_section(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert (ideas.paused_total, ideas.paused) == (0, ())


def test_metrics_and_watch_outs_come_from_the_best_pick_alone(ctx: ReadContext) -> None:
    by_id = {i.instrument_id: i for i in load_ideas(ctx, 10).items}
    # AAA's best is alpha's pick: its stored column and criterion value
    assert {m.name: m.value for m in by_id["EQ:AAA"].metrics} == {"spread": 0.05, "iv30": "high"}
    # BBB's best is me's beta (no stored values); alpha's iv_rank 40 is not merged in
    assert by_id["EQ:BBB"].metrics == ()
    assert by_id["EQ:BBB"].watch_out == ("large_move",)
    assert by_id["EQ:AAA"].watch_out == ()


def test_display_values_are_numbers_and_strings_a_column_over_a_criterion(
    ctx: ReadContext,
) -> None:
    aaa = next(i for i in load_ideas(ctx, 10).items if i.instrument_id == "EQ:AAA")
    assert display_metrics(aaa.best) == aaa.metrics


# ----------------------------------------------------------------------------- caps


def test_only_the_first_picks_of_a_screener_count() -> None:
    backend = screens_store()
    write_big_run(backend, 30, frozen=True)  # alpha: 30 picks, a site preset: its first 5 count
    ideas = load_ideas(context(StoreReader(backend)), 100)
    assert _ids(ideas) == ["EQ:BBB", "EQ:DDD", *[f"EQ:S00{n}" for n in range(5)]]
    assert [i.score for i in ideas.items][2:] == [1.0, 0.5, 1 / 3, 0.25, 0.2]


# ----------------------------------------------------------------------------- top


def test_a_screeners_top_is_read_from_its_picks_without_reading_its_run_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = screens_store()
    write_big_run(backend, 30, frozen=True, criteria=2)
    ctx = context(StoreReader(backend))
    shown = load_ideas(ctx, 100)  # every pick shown: the stored result is the reference
    real = results_module.run_row_details
    asked: list[str] = []

    def spy(c: ReadContext, run: ScreenerRun, instruments: object) -> pd.DataFrame:
        asked.append(run.run_id)
        return real(c, run, instruments)  # type: ignore[arg-type]

    monkeypatch.setattr(results_module, "run_row_details", spy)
    light = load_ideas(context(StoreReader(backend)), 1)  # one idea (beta's): big read for top only
    assert "big" not in asked  # the top of alpha came from screen_picks, no run file read
    ours = {s.screener.id: s for s in light.screeners}["alpha"]
    full = {s.screener.id: s for s in shown.screeners}["alpha"]
    assert [(t.instrument_id, t.position, t.score) for t in ours.top] == [
        ("EQ:S000", 1, 500.0), ("EQ:S001", 2, 500.0), ("EQ:S002", 3, 500.0)
    ]  # fmt: skip
    assert ours.top == full.top  # the same whatever else the page shows
    by_id = {i.instrument_id: i for i in shown.items}
    assert [t.score for t in ours.top] == [by_id[t.instrument_id].best.score for t in ours.top]


def test_top_picks_name_their_instrument_or_none_when_not_in_the_snapshot(ctx: ReadContext) -> None:
    alpha = {s.screener.id: s for s in load_ideas(ctx, 10).screeners}["alpha"]
    assert [(t.instrument_id, t.position) for t in alpha.top] == [("EQ:AAA", 1), ("EQ:BBB", 2)]
    assert [t.instrument.symbol if t.instrument else None for t in alpha.top] == ["AAA", "BBB"]


# ----------------------------------------------------------------------------- pages

PICKS = 120


def _pages(ctx: ReadContext, size: int) -> list[Ideas]:
    out, after = [], None
    while True:
        page = load_ideas(ctx, size, after)
        out.append(page)
        after = page.next_cursor
        if after is None:
            return out


def _ctx(frozen: bool, picks: int = PICKS) -> ReadContext:
    backend = screens_store()
    write_big_run(backend, picks, frozen)
    return context(StoreReader(backend), WIDE)


def test_page_two_continues_page_one_with_no_repeat_and_no_gap() -> None:
    ctx = _ctx(frozen=True)
    whole = load_ideas(ctx, 500)
    assert whole.total == PICKS + 2 and whole.next_cursor is None  # + BBB, DDD of beta
    pages = _pages(ctx, FIRST_PAGE)
    assert [len(p.items) for p in pages] == [50, 50, 22]
    assert [p.next_cursor is not None for p in pages] == [True, True, False]
    joined = [i for p in pages for i in p.items]
    assert [i.instrument_id for i in joined] == _ids(whole)  # the same order as one page
    assert len({i.instrument_id for i in joined}) == len(joined)  # no repeat
    assert [i.rank for i in joined] == list(range(1, PICKS + 3))  # no gap, ranks continue
    assert {p.total for p in pages} == {PICKS + 2}  # totals unaffected by the page


def test_the_first_page_carries_the_paused_section_and_later_pages_do_not() -> None:
    backend = screens_store()
    write_gated(backend)
    ctx = context(StoreReader(backend))
    first = load_ideas(ctx, 2)
    second = load_ideas(ctx, 2, first.next_cursor)
    assert (first.paused_total, len(first.paused)) == (2, 2)
    assert (second.paused_total, second.paused) == (2, ())


def test_ranks_are_the_same_with_and_without_the_picks_table() -> None:
    old, new = _ctx(frozen=False), _ctx(frozen=True)
    for size in (7, 50, 500):
        before, after = _pages(old, size), _pages(new, size)
        assert [_ids(p) for p in before] == [_ids(p) for p in after]
        assert [p.total for p in before] == [p.total for p in after]


def test_a_run_with_a_picks_file_is_ranked_without_reading_its_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real = runs_module.run_rows

    def guarded(ctx: ReadContext, run: ScreenerRun) -> pd.DataFrame:
        assert run.run_id != "big", "ranked from screen_picks, not the run's every row"
        return real(ctx, run)

    monkeypatch.setattr(runs_module, "run_rows", guarded)
    found = load_ideas(_ctx(frozen=True), 50)
    assert len(found.items) == 50 and found.items[2].instrument_id == "EQ:S000"


def test_a_run_with_picks_but_no_picks_file_is_never_read_as_picking_nothing() -> None:
    backend = screens_store()  # r1 of alpha, rb of beta: rule_screen rows only
    write_big_run(backend, 3, frozen=False)
    found = load_ideas(context(StoreReader(backend)), 10)
    assert found.total >= 3 and "EQ:S000" in _ids(found)


def test_a_malformed_cursor_is_refused() -> None:
    ctx = _ctx(frozen=True, picks=60)
    for bad in ("garbage", "AAAA", "bm90OjU"):  # not base64 / no offset / another stamp
        with pytest.raises(ConfigurationError):
            load_ideas(ctx, 10, bad)


def test_a_cursor_from_before_a_new_run_is_refused_not_shifted() -> None:
    backend = screens_store()
    write_big_run(backend, 60, frozen=True, run_id="big")
    cursor = load_ideas(context(StoreReader(backend), WIDE), 10).next_cursor
    assert cursor is not None
    write_big_run(backend, 70, frozen=True, run_id="bigger")  # a newer run supersedes it
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(context(StoreReader(backend), WIDE), 10, cursor)


def test_a_cursor_from_another_rule_is_refused_not_shifted() -> None:
    backend = screens_store()
    write_big_run(backend, 60, frozen=True)
    cursor = load_ideas(context(StoreReader(backend), WIDE), 10).next_cursor
    assert cursor is not None
    other = {("site", "ranking", "ideas"): {"site_top": 400, "user_top": 500}}
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(context(StoreReader(backend), other), 10, cursor)


def test_a_negative_or_empty_page_is_empty_with_no_cursor_past_the_end() -> None:
    ctx = _ctx(frozen=True, picks=5)
    assert load_ideas(ctx, 0).items == ()
    last = load_ideas(ctx, 100)
    assert last.next_cursor is None and len(last.items) == 7


def test_a_cursor_from_a_viewer_with_other_licences_is_refused_not_shifted(
    reader: StoreReader,
) -> None:
    # Two viewers with the same screeners (the site presets) and the same runs: ``full`` holds
    # the personal licence, ``bare`` does not, so a run is withheld from one and not the other.
    docs = {
        ("site", "ranking", "ideas"): {"site_top": 1, "user_top": 1},
        ("site", "settings", "users"): {
            "user": [
                {"id": "admin", "role": "admin"},
                {"id": "full", "role": "trader", "licences": ["personal", "yahoo"]},
                {"id": "bare", "role": "trader"},
            ]
        },
    }
    full, bare = context(reader, docs, user="full"), context(reader, docs, user="bare")
    assert [r.run_id for r in _runs(full)] == [r.run_id for r in _runs(bare)]
    assert not any(s.withheld for s in load_ideas(full, 5).screeners)
    assert all(s.withheld for s in load_ideas(bare, 5).screeners if s.run is not None)
    cursor = load_ideas(full, 1).next_cursor
    assert cursor is not None
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(bare, 1, cursor)


def _runs(ctx: ReadContext) -> list[ScreenerRun]:
    return [s.run for s in load_ideas(ctx, 1).screeners if s.run is not None]


# ---------------------------------------------------------------------- filters (ADR 0082)
FPICKS = 12
VOLUME = "rollup.volume@v1.dollar_volume"
IV = "rollup.ibkr_iv@v1.iv30_ibkr"
USERS = {
    "user": [
        {"id": "admin", "role": "admin"},
        {"id": "full", "role": "trader", "licences": ["personal", "yahoo"]},
        {"id": "bare", "role": "trader"},
    ]
}
IV_FILTER = {
    "id": "iv", "label": "IV", "group": "tradeable", "kind": "range", "field": IV,
    "bins": [0, 0.5, 1], "guide": "term:filter_spread",
}  # fmt: skip
DOCS = {
    ("site", "settings", "users"): USERS,
    ("site", "ranking", "ideas"): {"site_top": 50, "user_top": 50},
    ("site", "filters", "ideas"): {
        **IDEAS_FILTERS,
        "filter": [*IDEAS_FILTERS["filter"], IV_FILTER],
    },
}


def volume(n: int) -> float | None:
    return (n + 1) * 10_000_000.0 if n < 8 else None


def earnings(n: int) -> int | None:
    return n if n < 6 else None


def filter_store(iv: Callable[[int], float | None] = lambda n: 0.1 + n / 20) -> MemoryBackend:
    backend = screens_store([f"S{n:03d}" for n in range(FPICKS)])
    write_big_run(backend, FPICKS, frozen=True)
    w = StoreWriter(backend)
    # the run recorded the licences of what it read: instrument facts only, open to everyone
    w.save_run(RunRecord("big", "screen-alpha-site", D1, T + timedelta(hours=3)).finish(
        T + timedelta(hours=3), stats={"field_licences": {"instrument.status": "open"}}
    ))  # fmt: skip
    ids = [f"EQ:S{n:03d}" for n in range(FPICKS)]
    for table, column, value in (
        ("volume", "dollar_volume", volume),
        ("earnings", "days_to_earnings", earnings),
        ("ibkr_iv", "iv30_ibkr", iv),
    ):
        rows = [{"instrument_id": i, column: value(n)} for n, i in enumerate(ids)]
        write_rows(w, f"rollups/instrument/{table}@v1", D1, rows)
    return backend


@pytest.fixture(scope="module")
def filter_backend() -> MemoryBackend:
    return filter_store()


def view(filter_backend: MemoryBackend, user: str = "full") -> ReadContext:
    from algotrade.data import StoreReader  # noqa: PLC0415

    return context(StoreReader(filter_backend), copy.deepcopy(DOCS), user=user)


def walk(ctx: ReadContext, filters: list[FilterInput], size: int = 3) -> list[Ideas]:
    """Every page of the filtered list, following the cursor."""
    pages, cursor = [], None
    while True:
        page = load_ideas(ctx, size, cursor, filters)
        pages.append(page)
        cursor = page.next_cursor
        if cursor is None:
            return pages


def ids(pages: list[Ideas]) -> list[str]:
    return [i.instrument_id for p in pages for i in p.items]


def facet(result: Ideas, filter_id: str) -> FilterFacet:
    assert result.facets is not None
    return next(f for f in result.facets.items if f.id == filter_id)


def test_a_filter_narrows_the_whole_list_before_it_is_paged(filter_backend: MemoryBackend) -> None:
    ctx = view(filter_backend)
    everything = ids(walk(ctx, []))
    assert len(everything) > FPICKS  # the other screeners' picks too
    only = [FilterInput("dollar_volume", min=50_000_000)]
    pages = walk(ctx, only, size=2)  # S004..S007 sit on later pages than the first
    assert sorted(ids(pages)) == [f"EQ:S{n:03d}" for n in range(4, 8)]
    assert ids(pages) == [i for i in everything if i in ids(pages)]  # the rule's order
    assert {p.total for p in pages} == {4}
    assert all(p.facets is not None and p.facets.total == len(everything) for p in pages)
    assert all(p.facets is not None and p.facets.matched == 4 for p in pages)
    assert [len(p.items) for p in pages] == [2, 2]


def test_ranks_stay_the_ideas_place_in_the_unfiltered_list(filter_backend: MemoryBackend) -> None:
    ctx = view(filter_backend)
    unfiltered = {i.instrument_id: i.rank for p in walk(ctx, []) for i in p.items}
    page = load_ideas(ctx, 10, None, [FilterInput("dollar_volume", min=50_000_000)])
    assert all(i.rank == unfiltered[i.instrument_id] for i in page.items)


def test_unknown_never_passes_a_filter_and_is_counted(filter_backend: MemoryBackend) -> None:
    ctx = view(filter_backend)
    everything = load_ideas(ctx, 100, None, [])
    zero = load_ideas(ctx, 100, None, [FilterInput("dollar_volume", min=0)])
    stored = {f"EQ:S{n:03d}" for n in range(8)}
    assert {i.instrument_id for i in zero.items} == stored  # a min of 0 admits no null
    assert facet(zero, "dollar_volume").unknown == everything.total - 8
    window = load_ideas(
        ctx, 100, None, [FilterInput("earnings", within=Within(100, WindowUnit.SESSIONS))]
    )
    assert {i.instrument_id for i in window.items} == {f"EQ:S{n:03d}" for n in range(6)}


def test_a_cursor_from_another_filter_set_is_refused_not_shifted(
    filter_backend: MemoryBackend,
) -> None:
    ctx = view(filter_backend)
    a = [FilterInput("dollar_volume", min=30_000_000)]
    b = [FilterInput("dollar_volume", min=40_000_000)]
    cursor = load_ideas(ctx, 1, None, a).next_cursor
    assert cursor is not None
    for other in (b, []):
        with pytest.raises(ConfigurationError, match="changed since"):
            load_ideas(ctx, 1, cursor, other)
    assert load_ideas(ctx, 1, cursor, a).items  # the same narrowing continues
    # a filter that narrows nothing (switched off, or nothing set) does not change the cursor
    same = [*a, FilterInput("earnings", active=False), FilterInput("agreeing")]
    assert load_ideas(ctx, 1, cursor, same).items == load_ideas(ctx, 1, cursor, a).items


def test_a_filter_the_viewer_is_not_offered_is_refused_before_any_count(
    filter_backend: MemoryBackend,
) -> None:
    bare = view(filter_backend, "bare")
    served = load_served_filters(bare, "ideas")
    assert "iv" not in {f.id for f in served.filters}
    [held] = [w for w in served.withheld if w.id == "iv"]
    assert held.unavailable.kind.value == "LICENCE" and held.unavailable.features == (IV,)
    with pytest.raises(FilterRefusedError):
        load_ideas(bare, 5, None, [FilterInput("iv", min=0.3)])
    assert "iv" in {
        f.id for f in load_served_filters(view(filter_backend, "full"), "ideas").filters
    }


def _shape(result: Ideas) -> tuple[object, ...]:
    """Everything a viewer is told about the list: total, items, every facet."""
    assert result.facets is not None
    return (
        result.total,
        [i.instrument_id for i in result.items],
        result.facets,
        result.next_cursor,
    )


def test_changing_a_hidden_licence_fields_values_changes_no_count() -> None:
    """The leak test: two stores differing only in the stored ``iv30_ibkr``. The viewer without
    the personal licence reads the same total, matched, removes, unknown, options and bins from
    both, with every offered filter set; the holder's own filter does tell them apart."""
    low, high = filter_store(lambda n: 0.05), filter_store(lambda n: 0.95)
    inputs = [
        FilterInput("dollar_volume", min=20_000_000),
        FilterInput("earnings", within=Within(4, WindowUnit.SESSIONS)),
        FilterInput("decision", values=["QUALIFIED"]),
    ]
    for given in (inputs, [*inputs, FilterInput("dollar_volume", active=False)][:3], []):
        bare = [_shape(load_ideas(view(b, "bare"), 100, None, given)) for b in (low, high)]
        assert bare[0] == bare[1]
    assert all(f.id != "iv" for f in _shape(load_ideas(view(low, "bare"), 5, None, []))[2].items)
    narrowed = [FilterInput("iv", min=0.5)]
    seen = [load_ideas(view(b, "full"), 100, None, narrowed).total for b in (low, high)]
    assert seen[0] != seen[1]  # the holder of the licence reads the values


def test_a_hidden_field_is_not_read_for_a_viewer_without_the_licence(
    monkeypatch: pytest.MonkeyPatch, filter_backend: MemoryBackend
) -> None:
    from algotrade.services.read.screens import ideas as module  # noqa: PLC0415

    asked: list[list[str]] = []
    real = module.load_feature_values

    def spy(ctx: ReadContext, instrument_ids: object, names: list[str], *args: object) -> object:
        asked.append(list(names))
        return real(ctx, instrument_ids, names, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(module, "load_feature_values", spy)
    load_ideas(view(filter_backend, "bare"), 5)
    assert asked and all(IV not in names for names in asked)
    assert len([n for n in asked if VOLUME in n]) == 1  # one batch read for every filter field
    asked.clear()
    load_ideas(view(filter_backend, "full"), 5)
    assert IV in asked[0]


# ------------------------------------------------------------------------- properties
inputs_strategy = st.lists(
    st.one_of(
        st.builds(
            FilterInput,
            st.just("dollar_volume"),
            min=st.none() | st.sampled_from([0, 20e6, 50e6, 90e6]),
            max=st.none() | st.sampled_from([30e6, 60e6, 100e6]),
            active=st.booleans(),
        ),
        st.builds(
            FilterInput,
            st.just("earnings"),
            within=st.none()
            | st.builds(Within, st.sampled_from([0, 2, 5, 9]), st.just(WindowUnit.SESSIONS)),
            active=st.booleans(),
        ),
        st.builds(
            FilterInput,
            st.just("decision"),
            values=st.lists(
                st.sampled_from(["QUALIFIED", "WATCH", "REJECT"]), max_size=3, unique=True
            ),
            active=st.booleans(),
        ),
    ),
    max_size=3,
    unique_by=lambda i: i.id,
)


def _passes(idea_id: str, given: list[FilterInput]) -> bool:
    n = int(idea_id[4:]) if idea_id.startswith("EQ:S") and idea_id[4:].isdigit() else None
    for f in given:
        if not f.active:
            continue
        if f.id == "dollar_volume" and (f.min is not None or f.max is not None):
            v = None if n is None else volume(n)
            if v is None or (f.min is not None and v < f.min) or (f.max is not None and v > f.max):
                return False
        if f.id == "earnings" and f.within is not None:
            e = None if n is None else earnings(n)
            if e is None or e > f.within.amount:
                return False
    return True


@settings(max_examples=40, deadline=None)
@hypothesis_given(inputs_strategy, st.integers(1, 5))
def test_the_facets_and_pages_agree_with_an_oracle_over_the_unfiltered_list(
    given: list[FilterInput], size: int
) -> None:
    ctx = view(BACKEND)
    unfiltered = [i for p in walk(ctx, [], 50) for i in p.items]
    pages = walk(ctx, given, size)
    got = [i for p in pages for i in p.items]
    decisions = next(
        (f.values for f in given if f.id == "decision" and f.active and f.values), None
    )
    expected = [
        i for i in unfiltered
        if _passes(i.instrument_id, given) and (decisions is None or i.best.decision in decisions)
    ]  # fmt: skip
    assert [i.instrument_id for i in got] == [i.instrument_id for i in expected]
    assert all(p.total == len(expected) for p in pages)
    facets: Facets | None = pages[0].facets
    assert facets is not None
    assert (facets.total, facets.matched) == (len(unfiltered), len(expected))
    for f in facets.items:
        if f.removes is not None:
            assert f.removes >= 0
        assert f.unknown >= 0 and all(o.count >= 0 for o in f.options)
    assert [len(p.items) for p in pages[:-1]] == [size] * (len(pages) - 1)


BACKEND = filter_store()


def test_a_cursor_is_refused_when_the_values_a_filter_reads_were_rewritten() -> None:
    """Fix for a review finding: the filters read stored values a later run may rewrite, which
    moves the list the offset indexes; the stamp carries the tickers the filters left."""
    given = [FilterInput("earnings", within=Within(100, WindowUnit.SESSIONS))]
    cursor = load_ideas(view(filter_store()), 2, None, given).next_cursor
    assert cursor is not None
    rewritten = filter_store()
    write_rows(
        StoreWriter(rewritten),
        "rollups/instrument/earnings@v1",
        D1,
        [{"instrument_id": "EQ:S000", "days_to_earnings": None}],
    )
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(view(rewritten), 2, cursor, given)
