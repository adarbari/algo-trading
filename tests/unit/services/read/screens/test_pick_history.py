from collections import Counter
from datetime import UTC, date, datetime, timedelta

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, at_session, open_context
from algotrade.services.read.screens.pick_history import (
    DEFAULT_SESSIONS,
    MAX_SESSIONS,
    load_pick_histories,
)
from algotrade.services.read.screens.runs import latest_run
from algotrade.services.read.values import UnknownCode
from algotrade.services.screening.run import run_job_name
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.screens.conftest import D0, D1, write_run

Rows = list[tuple[str, str, float | None, float | None]]
ROWS: Rows = [("AAA", "QUALIFIED", 1.0, None), ("BBB", "WATCH", 2.0, None),
              ("CCC", "REJECT", 0.0, None)]  # fmt: skip
GATED: Rows = [("AAA", "QUALIFIED", 1.0, None), ("BBB", "PAUSED", 2.0, None),
               ("CCC", "PAUSED", 3.0, None), ("DDD", "REJECT", 0.0, None)]  # fmt: skip
T0 = datetime(2026, 9, 30, 23, tzinfo=UTC)
DELTA = ("me", "delta")


def _on(reader: StoreReader, day: date) -> ReadContext:
    return open_context(reader, MemoryConfigStore({}), UserContext("me"), day)


def _screen(
    backend: MemoryBackend, day: date, run_id: str, rows: Rows, hours: int, config: str = "delta"
) -> None:
    """A run of ``config`` for ``me`` on ``day`` stored ``hours`` after T0: its rows and its
    finished record with the summary the nightly writes."""
    when = T0 + timedelta(hours=hours)
    w = StoreWriter(backend)
    write_run(w, day, run_id, "me", config, rows, knowledge=when)
    counts = dict(Counter(decision for _, decision, _, _ in rows))
    record = RunRecord(run_id, run_job_name(config, "me"), day, when)
    w.save_run(record.finish(when, stats={"summary": {"decisions": counts}}))


def test_one_entry_per_session_oldest_first_and_a_missing_run_is_not_run(
    backend: MemoryBackend, ctx: ReadContext
) -> None:
    _screen(backend, D0, "d0", ROWS[:1], 0)
    _screen(backend, D1, "d1", ROWS, 24)
    found = load_pick_histories(ctx, [DELTA], 3)[DELTA]
    assert [p.session for p in found] == sessions_ending(D1, 3)  # 09-29, 09-30, 10-01
    first, second, third = found
    assert first.picked is None and first.paused is None and first.not_run is not None
    assert first.not_run.code is UnknownCode.NOT_RUN  # never D0's run carried forward
    assert first.not_run.cause.text == "delta has no run in results/rule_screen for 2026-09-29"
    assert (second.picked, second.paused, second.not_run) == (1, 0, None)
    assert (third.picked, third.paused, third.not_run) == (2, 0, None)


def test_every_entry_is_what_latest_run_says_at_that_session(
    backend: MemoryBackend, reader: StoreReader, ctx: ReadContext
) -> None:
    """Several runs in a session (the latest wins), a gated run (paused apart), a re-run of an
    old session stored later: entry ``d`` equals ``latestRun`` at ``at_session(d)``."""
    _screen(backend, D0, "a", ROWS[:1], 0)
    _screen(backend, D0, "b", ROWS, 3)
    _screen(backend, D1, "c", ROWS[:2], 24)
    _screen(backend, D1, "d", GATED, 26)
    _screen(backend, D0, "e", GATED, 30)  # a re-run of D0 after D1's: latestRun at D0 sees it
    found = load_pick_histories(ctx, [DELTA], 2)[DELTA]
    for entry in found:
        run = latest_run(at_session(ctx, entry.session), *DELTA).run
        assert run is not None
        assert (entry.picked, entry.paused) == (run.picked, run.paused)
    assert [(p.picked, p.paused) for p in found] == [(1, 2), (1, 2)]


def test_a_record_that_finished_no_screen_is_ignored(
    backend: MemoryBackend, ctx: ReadContext
) -> None:
    _screen(backend, D0, "a", ROWS, 0)
    w = StoreWriter(backend)
    w.save_run(RunRecord("x", run_job_name("delta", "me"), D0, T0 + timedelta(hours=5)))  # RUNNING
    old = RunRecord("y", run_job_name("delta", "me"), D0, T0 + timedelta(hours=6))
    w.save_run(old.finish(T0 + timedelta(hours=6), complete=False, stats={}))  # no counts
    found = load_pick_histories(ctx, [DELTA], 2)[DELTA]
    assert found[0].picked == 2  # run "a": the later records counted nothing


def test_the_window_is_cut_to_one_through_ninety_sessions(ctx: ReadContext) -> None:
    assert len(load_pick_histories(ctx, [DELTA])[DELTA]) == DEFAULT_SESSIONS == 30
    assert len(load_pick_histories(ctx, [DELTA], 500)[DELTA]) == MAX_SESSIONS == 90
    assert [p.session for p in load_pick_histories(ctx, [DELTA], 0)[DELTA]] == [D1]


def test_a_list_of_screeners_is_one_batch_and_ends_at_the_request_session(
    backend: MemoryBackend, reader: StoreReader, ctx: ReadContext
) -> None:
    _screen(backend, D0, "a", ROWS, 0)
    _screen(backend, D0, "g", ROWS[:1], 1, config="gamma")
    found = load_pick_histories(ctx, [("site", "alpha"), DELTA, ("me", "gamma")], 2)
    assert [p.picked for p in found[("site", "alpha")]] == [
        None,
        2,
    ]  # D0: rows without a run record are not counted
    assert [p.picked for p in found[DELTA]] == [2, None]
    assert [p.picked for p in found[("me", "gamma")]] == [1, None]
    earlier = load_pick_histories(_on(reader, D0), [DELTA], 2)[DELTA]
    assert [p.session for p in earlier] == sessions_ending(D0, 2)  # D1's run is past the window
    assert earlier[-1].picked == 2
