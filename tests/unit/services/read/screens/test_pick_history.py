from datetime import UTC, date, datetime

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, open_context
from algotrade.services.read.screens.pick_history import (
    DEFAULT_SESSIONS,
    MAX_SESSIONS,
    load_pick_histories,
)
from algotrade.services.read.screens.runs import latest_run
from algotrade.services.read.values import UnknownCode
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.screens.conftest import D0, D1, write_gated, write_run

ROWS = [("AAA", "QUALIFIED", 1.0, None), ("BBB", "WATCH", 2.0, None), ("CCC", "REJECT", 0.0, None)]
EARLY = datetime(2026, 9, 30, 23, tzinfo=UTC)  # after D0's close, before D1's
LATE = datetime(2026, 10, 2, 5, tzinfo=UTC)  # after D1's close
DELTA = ("me", "delta")


def _on(reader: StoreReader, day: date) -> ReadContext:
    return open_context(reader, MemoryConfigStore({}), UserContext("me"), day)


def _delta(backend: MemoryBackend) -> None:
    """``delta`` ran on D0 (one pick) and on D1 (two picks); a re-run of D0 (three picks) was
    stored after D1 closed."""
    w = StoreWriter(backend)
    write_run(w, D0, "d0", "me", "delta", ROWS[:1], knowledge=EARLY)
    write_run(w, D1, "d1", "me", "delta", ROWS, knowledge=LATE)
    write_run(w, D0, "d0b", "me", "delta", [*ROWS[:2], ("DDD", "QUALIFIED", 3.0, None)], LATE)


def test_one_entry_per_session_oldest_first_and_a_missing_run_is_not_run(
    backend: MemoryBackend, ctx: ReadContext
) -> None:
    _delta(backend)
    found = load_pick_histories(ctx, [DELTA], 3)[DELTA]
    assert [p.session for p in found] == sessions_ending(D1, 3)  # 09-29, 09-30, 10-01
    first, second, third = found
    assert first.picked is None and first.paused is None and first.not_run is not None
    assert first.not_run.code is UnknownCode.NOT_RUN  # never D0's run carried forward
    assert first.not_run.cause.text == "delta has no run in results/rule_screen for 2026-09-29"
    assert (second.picked, second.paused, second.not_run) == (1, 0, None)
    assert (third.picked, third.paused, third.not_run) == (2, 0, None)


def test_a_run_stored_after_the_session_closed_is_not_read_back(
    backend: MemoryBackend, reader: StoreReader, ctx: ReadContext
) -> None:
    _delta(backend)
    at_d1 = load_pick_histories(ctx, [DELTA], 2)[DELTA]
    assert at_d1[0].picked == 1  # D0's re-run (3 picks) came after D1 closed: not known by D1
    at_d0 = load_pick_histories(_on(reader, D0), [DELTA], 2)[DELTA]
    assert [p.session for p in at_d0] == sessions_ending(D0, 2)  # D1's run is past the window
    assert at_d0[-1].picked == 3  # the request's own session reads as latestRun does


def test_several_runs_in_a_session_use_the_latest_run_rule(
    backend: MemoryBackend, reader: StoreReader, ctx: ReadContext
) -> None:
    key = ("site", "alpha")  # r0 (1 pick) then r1 (2 picks) on D1
    last = load_pick_histories(ctx, [key], 1)[key][0]
    run = latest_run(ctx, *key).run
    assert run is not None and (last.picked, last.paused) == (run.picked, run.paused) == (2, 0)
    write_gated(backend)  # r2 supersedes: AAA picked, BBB and DDD paused
    gated = load_pick_histories(_on(reader, D1), [key], 1)[key][0]
    assert (gated.picked, gated.paused) == (1, 2)


def test_the_window_is_cut_to_one_through_ninety_sessions(ctx: ReadContext) -> None:
    assert len(load_pick_histories(ctx, [DELTA])[DELTA]) == DEFAULT_SESSIONS == 30
    assert len(load_pick_histories(ctx, [DELTA], 500)[DELTA]) == MAX_SESSIONS == 90
    assert [p.session for p in load_pick_histories(ctx, [DELTA], 0)[DELTA]] == [D1]


def test_a_list_of_screeners_is_one_read(ctx: ReadContext) -> None:
    found = load_pick_histories(ctx, [("site", "alpha"), ("me", "beta"), ("me", "gamma")], 2)
    # the fixture's D0 runs are stamped after D1 closed: not known by D1, so D0 is NOT_RUN
    assert [p.picked for p in found[("site", "alpha")]] == [None, 2]
    assert [p.picked for p in found[("me", "beta")]] == [None, 2]
    assert [p.picked for p in found[("me", "gamma")]] == [None, None]
