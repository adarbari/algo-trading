"""``streaks``: ``days_picked`` and ``new_today`` over the chain of a screener's previous runs.

One store of ``site``'s ``alpha`` over consecutive weekdays (``DAYS``): who it picked each day
is ``PICKS``; a day in ``GAPS`` has a run of ``beta`` only (the session is stored, alpha did not
run). Each test is run on both read paths (a run before ``screen_runs`` and a frozen run)."""

from datetime import date, timedelta

import pandas as pd
import pytest

from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, at_session
from algotrade.services.read.filtering.masks import FilterInput
from algotrade.services.read.screens import ideas as ideas_module
from algotrade.services.read.screens import results as results_module
from algotrade.services.read.screens.ideas import load_ideas
from algotrade.services.read.screens.results import load_result_page, run_withheld
from algotrade.services.read.screens.runs import ScreenerRun, latest_run
from algotrade.services.read.screens.streaks import CAP, days_picked, new_today
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.tables.writers import StoreWriter
from tests.helpers.stored_frames import stamped, write_reference
from tests.unit.services.read.screens.conftest import T, context, screens_store, write_run
from tests.unit.services.read.screens.test_runs import freeze

Days = tuple[date, ...]
Picks = dict[date, dict[str, str]]  # day -> symbol -> decision (a day missing: alpha did not run)


def weekdays(start: date, n: int) -> Days:
    out: list[date] = []
    day = start
    while len(out) < n:
        if day.weekday() < 5:
            out.append(day)
        day += timedelta(days=1)
    return tuple(out)


def _store(picks: Picks, days: Days, frozen: bool) -> MemoryBackend:
    store = MemoryBackend()
    w = StoreWriter(store)
    write_reference(w, days[0], {s: f"EQ:{s}" for s in ("AAA", "BBB", "CCC")})
    for n, day in enumerate(days):
        bar = {"instrument_id": "EQ:AAA", "ts": pd.Timestamp(day, tz="UTC"), "open": 1.0,
               "high": 1.0, "low": 1.0, "close": 1.0, "volume": 1.0}  # fmt: skip
        w.write_table("bars/1d", day, f"bars-{day}", stamped([bar], day, f"bars-{day}"))
        if day in picks:
            rows = [(s, d, 50.0 + k, None) for k, (s, d) in enumerate(picks[day].items())]
            write_run(w, day, f"a{n}", "site", "alpha", rows, knowledge=T + timedelta(days=n))
        else:  # the session is stored, alpha did not run in it
            write_run(w, day, f"b{n}", "site", "beta", [("AAA", "REJECT", 0.0, None)])
    if frozen:
        freeze(store, days)
    return store


def _alpha(reader: StoreReader, day: date, user: str = "admin") -> tuple[ReadContext, ScreenerRun]:
    ctx = at_session(context(reader, user=user), day)
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    return ctx, run


def _bare(found: dict[str, object]) -> dict[str, object]:
    return {k.removeprefix("EQ:"): v for k, v in found.items()}


def _never(_ctx: ReadContext, _run: ScreenerRun) -> bool:
    return False


Q, R = "QUALIFIED", "REJECT"
DAYS = weekdays(date(2026, 9, 28), 6)  # Mon 28, Tue 29, Wed 30, Thu Oct 1, Fri 2, Mon 5
# DAYS[0] is a run that picked nothing: the start of a history the walk can honestly end at
PICKS: Picks = {
    DAYS[0]: {"AAA": R, "BBB": R, "CCC": R},
    DAYS[1]: {"AAA": Q, "BBB": Q, "CCC": R},
    DAYS[2]: {"AAA": Q, "BBB": Q, "CCC": Q},
    DAYS[3]: {"AAA": Q, "BBB": R, "CCC": Q},
    DAYS[4]: {"AAA": Q, "BBB": Q, "CCC": R},
    DAYS[5]: {"AAA": Q, "BBB": Q, "CCC": R},
}
BOTH = pytest.mark.parametrize("frozen", [False, True], ids=["rows", "frozen"])


@BOTH
def test_a_streak_ends_at_the_first_run_that_did_not_pick(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[5])
    # AAA every day; BBB on the last two (REJECT before); CCC rejected today: not in the result
    assert _bare(days_picked(ctx, run, _never)) == {"AAA": 5, "BBB": 2}


@BOTH
def test_a_later_run_does_not_change_an_earlier_sessions_streak(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[3])  # the session two runs before the last
    assert _bare(days_picked(ctx, run, _never)) == {"AAA": 3, "CCC": 2}
    again = StoreReader(_store(PICKS, DAYS[:4], frozen))  # the same history without the later runs
    assert _bare(days_picked(*_alpha(again, DAYS[3]), _never)) == {"AAA": 3, "CCC": 2}


@BOTH
def test_the_previous_run_is_the_one_before_the_session_not_the_latest(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[4])
    # the latest run (DAYS[5]) picks BBB too; DAYS[3] rejected it: new today at DAYS[4]
    assert _bare(new_today(ctx, run, _never)) == {"AAA": False, "BBB": True}


@BOTH
def test_new_today_is_false_for_a_name_the_previous_run_picked(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[2])
    assert _bare(new_today(ctx, run, _never)) == {"AAA": False, "BBB": False, "CCC": True}


GAPS: Picks = {
    DAYS[0]: {"AAA": Q, "BBB": Q},
    DAYS[2]: {"AAA": Q, "BBB": R},  # DAYS[1]: alpha did not run
    DAYS[3]: {"AAA": Q, "BBB": Q},
}


@BOTH
def test_a_session_alpha_did_not_run_in_makes_an_open_streak_unknown(frozen: bool) -> None:
    days = DAYS[:4]
    reader = StoreReader(_store(GAPS, days, frozen))
    ctx, run = _alpha(reader, days[2])
    # AAA's streak would run into the gap: unknown, never 1 and never 0; BBB is rejected today
    assert _bare(days_picked(ctx, run, _never)) == {"AAA": None}
    ctx, run = _alpha(reader, days[3])
    # BBB's ended at DAYS[2] (rejected): known whatever lies beyond; AAA's reaches the gap
    assert _bare(days_picked(ctx, run, _never)) == {"AAA": None, "BBB": 1}


@BOTH
def test_new_today_is_unknown_when_there_is_no_previous_run(frozen: bool) -> None:
    reader = StoreReader(_store(GAPS, DAYS[:4], frozen))
    ctx, first = _alpha(reader, DAYS[0])  # the first run: nothing before it
    assert _bare(new_today(ctx, first, _never)) == {"AAA": None, "BBB": None}
    assert _bare(days_picked(ctx, first, _never)) == {
        "AAA": None,
        "BBB": None,
    }  # not taken for a streak of 1
    ctx, after_gap = _alpha(reader, DAYS[2])
    assert _bare(new_today(ctx, after_gap, _never)) == {"AAA": None}


@BOTH
def test_a_withheld_run_in_the_chain_makes_the_open_streaks_unknown(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[5])
    middle = latest_run(at_session(ctx, DAYS[3]), "site", "alpha").run
    assert middle is not None

    def hides_the_middle(_c: ReadContext, r: ScreenerRun) -> bool:
        return r.run_id == middle.run_id

    # BBB's streak ended at DAYS[3] (rejected): that run's rows tell, and they are hidden, so BBB
    # is unknown as AAA is; CCC is not picked at all
    assert _bare(days_picked(ctx, run, hides_the_middle)) == {"AAA": None, "BBB": None}
    assert _bare(new_today(ctx, run, hides_the_middle)) == {
        "AAA": False,
        "BBB": False,
    }  # one step only
    ctx3, run3 = _alpha(reader, DAYS[4])
    # DAYS[4] -> DAYS[3] is hidden: the previous run cannot be read
    assert _bare(new_today(ctx3, run3, hides_the_middle)) == {"AAA": None, "BBB": None}


@BOTH
def test_a_run_withheld_from_the_viewer_is_unknown_whole(frozen: bool) -> None:
    reader = StoreReader(_store(PICKS, DAYS, frozen))
    ctx, run = _alpha(reader, DAYS[5])
    assert _bare(days_picked(ctx, run, lambda _c, _r: True)) == {"AAA": None, "BBB": None}
    assert _bare(new_today(ctx, run, lambda _c, _r: True)) == {"AAA": None, "BBB": None}


def test_a_viewer_without_the_licence_gets_no_streak_from_the_real_rule() -> None:
    reader = StoreReader(screens_store())
    ctx = at_session(context(reader, user="trader"), date(2026, 10, 1))
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None and run_withheld(ctx, run)
    assert set(days_picked(ctx, run, run_withheld).values()) == {None}


@BOTH
def test_a_streak_is_capped(frozen: bool) -> None:
    days = weekdays(date(2026, 8, 3), CAP + 5)
    picks = {d: {"AAA": Q, "BBB": Q if n >= 3 else R} for n, d in enumerate(days)}
    reader = StoreReader(_store(picks, days, frozen))
    ctx, run = _alpha(reader, days[-1])
    found = _bare(days_picked(ctx, run, _never))
    assert found["AAA"] == CAP  # 25 runs picked it, reported as 20 (the filter's last bin)
    assert found["BBB"] == CAP  # picked on 22 of them
    ctx, run = _alpha(reader, days[CAP - 2])  # 19 runs of history, all picks: the start is
    assert _bare(days_picked(ctx, run, _never))["AAA"] is None  # reached below the cap: unknown
    ctx, run = _alpha(reader, days[CAP - 1])  # exactly 20
    assert _bare(days_picked(ctx, run, _never))["AAA"] == CAP


@BOTH
def test_a_streak_cut_by_the_cap_is_known_even_where_the_chain_ends_after_it(frozen: bool) -> None:
    days = weekdays(date(2026, 8, 3), CAP)
    picks = {d: {"AAA": Q} for d in days}  # the first run is the 20th back from the last
    reader = StoreReader(_store(picks, days, frozen))
    ctx, run = _alpha(reader, days[-1])
    assert _bare(days_picked(ctx, run, _never)) == {"AAA": CAP}


def test_the_walk_is_read_once_per_run_and_published_state() -> None:
    reader = StoreReader(_store(PICKS, DAYS, True))
    ctx, run = _alpha(reader, DAYS[4])
    calls: list[str] = []

    def counting(c: ReadContext, r: ScreenerRun) -> bool:
        calls.append(r.run_id)
        return False

    first = days_picked(ctx, run, counting)
    seen = len(calls)
    assert days_picked(ctx, run, counting) == first and len(calls) == seen


# ------------------------------------------------- the columns they feed (ADR 0082 surfaces)


def test_ideas_carry_new_today_and_days_picked_from_each_pick_screeners_runs() -> None:
    both = [FilterInput("new_today"), FilterInput("days_picked")]  # set, nothing chosen yet
    ideas = load_ideas(context(StoreReader(screens_store())), 10, None, both)
    got = {i.instrument_id: (i.new_today, i.days_picked) for i in ideas.items}
    # AAA: site alpha picked it on D1 and did not on D0 (a run that day: 1 known). BBB: alpha
    # picked it on D0 too (not new), its D0 history starts there, and me's beta has no earlier
    # run (unknown): the longest known streak is not a bound. DDD: only me's beta, no earlier run.
    assert got == {"EQ:AAA": (True, 1), "EQ:BBB": (False, None), "EQ:DDD": (None, None)}


def test_the_ideas_filters_keep_known_rows_only() -> None:
    ctx = context(StoreReader(screens_store()))

    def kept(*filters: FilterInput) -> list[str]:
        return [i.instrument_id for i in load_ideas(ctx, 10, None, list(filters)).items]

    assert kept(FilterInput("new_today", ["yes"])) == ["EQ:AAA"]
    assert kept(FilterInput("new_today", ["no"])) == ["EQ:BBB"]  # DDD is unknown: in neither
    assert kept(FilterInput("days_picked", min=1)) == ["EQ:AAA"]
    assert kept(FilterInput("days_picked", min=2)) == []


def test_a_name_one_screener_picked_before_is_not_new_whatever_the_other_knows() -> None:
    # BBB: alpha picked it before (False) and beta has no previous run (None): not new, known
    ctx = context(StoreReader(screens_store()))
    [bbb] = [
        i
        for i in load_ideas(ctx, 10, None, [FilterInput("new_today")]).items
        if i.instrument_id == "EQ:BBB"
    ]
    assert bbb.new_today is False


def test_a_results_page_carries_days_picked_and_filters_on_it() -> None:
    ctx = context(StoreReader(screens_store()))
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    page = load_result_page(ctx, run, None, (), 1, 10, [FilterInput("days_picked")])
    # AAA 1; BBB reaches alpha's first run (unknown); CCC rejected today: 0, a known value
    assert {r.instrument_id: r.days_picked for r in page.results} == {
        "EQ:AAA": 1, "EQ:BBB": None, "EQ:CCC": 0
    }  # fmt: skip
    one = load_result_page(ctx, run, None, (), 1, 10, [FilterInput("days_picked", min=1)])
    assert [r.instrument_id for r in one.results] == ["EQ:AAA"]
    assert one.facets is not None
    [facet] = [f for f in one.facets.items if f.id == "days_picked"]
    assert facet.unknown == 1  # BBB: counted as unknown, never as a short streak


def _count_walks(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    for module in (ideas_module, results_module):
        for name in ("days_picked", "new_today"):
            if hasattr(module, name):
                real = getattr(module, name)

                def spy(*a: object, _real: object = real, _name: str = name, **k: object) -> object:
                    calls.append(_name)
                    return _real(*a, **k)  # type: ignore[operator]

                monkeypatch.setattr(module, name, spy)
    return calls


def test_a_request_without_the_history_filters_never_walks(monkeypatch: pytest.MonkeyPatch) -> None:
    ctx = context(StoreReader(screens_store()))
    run = latest_run(ctx, "site", "alpha").run
    assert run is not None
    calls = _count_walks(monkeypatch)
    plain = load_ideas(ctx, 10)
    unrelated = load_ideas(ctx, 10, None, [FilterInput("agreeing", min=1)])
    page = load_result_page(ctx, run, None, (), 1, 10, [FilterInput("rank", min=1)])
    assert calls == []
    assert {i.days_picked for i in plain.items} == {None} and plain.total == 3 == unrelated.total
    assert plain.facets is not None
    assert not {"new_today", "days_picked"} & {f.id for f in plain.facets.items}
    assert {r.days_picked for r in page.results} == {None}
    assert page.facets is not None and "days_picked" not in {f.id for f in page.facets.items}
    load_ideas(ctx, 10, None, [FilterInput("days_picked", min=1)])
    assert "days_picked" in calls and "new_today" not in calls  # only the column asked for
