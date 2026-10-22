from datetime import timedelta

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens import ideas as ideas_module
from algotrade.services.read.screens.ideas import (
    FIRST_PAGE,
    Ideas,
    load_ideas,
    screener_priority,
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

PRIORITY = {("me", "preferences", "preferences"): {"ideas": {"priority": ["beta", "nope"]}}}


def _ids(found: Ideas) -> list[str]:
    return [i.instrument_id for i in found.items]


def test_no_priority_ranks_by_score_then_tie_break(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 10)
    assert (ideas.session, ideas.priority, ideas.total) == (D1, (), 3)
    # Unlisted screeners share one place: score decides (BBB 90 by beta, AAA 50, DDD 10).
    assert _ids(ideas) == ["EQ:BBB", "EQ:AAA", "EQ:DDD"]
    first = ideas.items[0]
    assert first.rank == 1 and first.instrument is not None and first.instrument.symbol == "BBB"
    assert [(p.config_id, p.decision) for p in first.picks] == [
        ("beta", "QUALIFIED"), ("alpha", "WATCH")
    ]  # fmt: skip


def test_priority_first_and_the_users_screen_wins(reader: StoreReader) -> None:
    ideas = load_ideas(context(reader, PRIORITY), 10)
    assert ideas.priority == ("beta", "nope")
    assert _ids(ideas) == ["EQ:BBB", "EQ:DDD", "EQ:AAA"]  # beta's picks first
    # The site's beta run (CCC 99) is not me's beta: CCC is no idea.
    assert "EQ:CCC" not in _ids(ideas)
    assert [s.screener.id for s in ideas.screeners] == ["beta", "alpha", "gamma"]


def test_screeners_count_the_whole_run_and_say_not_run(ctx: ReadContext) -> None:
    ideas = load_ideas(ctx, 1)  # one item shown; counts are over the run
    assert _ids(ideas) == ["EQ:BBB"] and ideas.total == 3
    by_id = {s.screener.id: s for s in ideas.screeners}
    alpha = by_id["alpha"]
    assert alpha.run is not None and alpha.run.run_id == "r1"
    assert (alpha.picked, alpha.not_run) == (2, None)
    assert [r.instrument_id for r in alpha.top] == ["EQ:AAA", "EQ:BBB"]  # picks by rank
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


def test_priority_is_read_from_the_users_preferences(reader: StoreReader) -> None:
    assert screener_priority(context(reader, PRIORITY)) == ("beta", "nope")
    assert screener_priority(context(reader)) == ()


def test_paused_picks_are_no_ideas_but_are_listed_apart_with_their_reason(
    backend: MemoryBackend, reader: StoreReader
) -> None:
    write_gated(backend)
    ideas = load_ideas(context(reader), 10)
    assert "EQ:BBB" in _ids(ideas)  # beta still picks it
    assert [i.instrument_id for i in ideas.items if i.picks[0].config_id == "alpha"] == ["EQ:AAA"]
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
    return context(StoreReader(backend))


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
    first, second = load_ideas(ctx, 2), None
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
    real = ideas_module.run_rows

    def guarded(ctx: ReadContext, run: ScreenerRun) -> pd.DataFrame:
        assert run.run_id != "big", "ranked from screen_picks, not the run's every row"
        return real(ctx, run)

    monkeypatch.setattr(ideas_module, "run_rows", guarded)
    found = load_ideas(_ctx(frozen=True), 50)
    assert len(found.items) == 50 and found.items[0].instrument_id == "EQ:S000"


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
    cursor = load_ideas(context(StoreReader(backend)), 10).next_cursor
    assert cursor is not None
    write_big_run(backend, 70, frozen=True, run_id="bigger")  # a newer run supersedes it
    with pytest.raises(ConfigurationError, match="changed since"):
        load_ideas(context(StoreReader(backend)), 10, cursor)


def test_a_negative_or_empty_page_is_empty_with_no_cursor_past_the_end() -> None:
    ctx = _ctx(frozen=True, picks=5)
    assert load_ideas(ctx, 0).items == ()
    last = load_ideas(ctx, 100)
    assert last.next_cursor is None and len(last.items) == 7
