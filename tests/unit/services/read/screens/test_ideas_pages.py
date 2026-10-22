"""``load_ideas`` in pages (owner decision 2026-10-22, "Ideas page size"): page two continues
page one in the one stable rank order (no repeat, no gap, the same order as one big page), a
cursor is refused when the runs behind it changed, and the ranking is the same whether the runs
have their ``results/screen_picks`` file or only ``rule_screen`` rows (the old path)."""

import pandas as pd
import pytest

from algotrade.core.model.errors import ConfigurationError
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext
from algotrade.services.read.screens import ideas
from algotrade.services.read.screens.ideas import FIRST_PAGE, Ideas, load_ideas
from algotrade.services.read.screens.runs import ScreenerRun
from algotrade.storage.backends.memory import MemoryBackend
from tests.unit.services.read.screens.conftest import (
    context,
    screens_store,
    write_big_run,
    write_gated,
)

PICKS = 120


def _ids(found: Ideas) -> list[str]:
    return [i.instrument_id for i in found.items]


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
    real = ideas.run_rows

    def guarded(ctx: ReadContext, run: ScreenerRun) -> pd.DataFrame:
        assert run.run_id != "big", "ranked from screen_picks, not the run's every row"
        return real(ctx, run)

    monkeypatch.setattr(ideas, "run_rows", guarded)
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


def test_the_backend_type_is_the_memory_one() -> None:
    assert isinstance(screens_store(), MemoryBackend)
