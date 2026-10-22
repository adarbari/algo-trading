"""``load_ideas``: the viewer's screener pool ranked by the rule (services/ideas/rule.py), each
idea served from its best pick only; the licence rule, NOT_RUN, the PAUSED section, paging."""

from datetime import timedelta

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
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
from tests.unit.services.read.screens.conftest import (
    CONFIGS,
    D1,
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
    # ``me`` holds the personal licence, ``trader`` does not: same runs, other pool
    wide = {**WIDE, ("site", "ranking", "ideas"): {"site_top": 1, "user_top": 1}}
    cursor = load_ideas(context(reader, wide), 1).next_cursor
    assert cursor is not None
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(context(reader, wide, user="trader"), 1, cursor)
