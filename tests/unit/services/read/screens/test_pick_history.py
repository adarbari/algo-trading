from collections import Counter
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import pandas as pd
import pytest

from algotrade.config.user import UserContext
from algotrade.core.time.calendar import sessions_ending
from algotrade.data import StoreReader
from algotrade.services.read.context import ReadContext, at_session, open_context
from algotrade.services.read.screens.pick_history import (
    DEFAULT_SESSIONS,
    MAX_SESSIONS,
    _counted,
    _decisions,
    load_pick_histories,
)
from algotrade.services.read.screens.runs import latest_run
from algotrade.services.read.values import UnknownCode
from algotrade.services.screening.rule_results import PAUSED, is_picked
from algotrade.services.screening.run import run_job_name
from algotrade.storage.backends.memory import MemoryBackend
from algotrade.storage.configs.files import MemoryConfigStore
from algotrade.storage.runs import RunRecord
from algotrade.storage.tables.writers import StoreWriter
from tests.unit.services.read.screens.conftest import D0, D1, write_run
from tests.unit.services.screening.test_regime import ON, screen
from tests.unit.services.screening.test_rule_screens import DAY, configs

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


def test_a_later_record_that_counted_nothing_defers_to_latest_run(
    backend: MemoryBackend, ctx: ReadContext
) -> None:
    """A later run still RUNNING (rows written, no summary) is what ``latestRun`` shows: its
    counts, not the older finished run's."""
    _screen(backend, D0, "a", ROWS, 0)  # 2 picked
    w = StoreWriter(backend)
    write_run(w, D0, "b", "me", "delta", GATED, knowledge=T0 + timedelta(hours=5))
    w.save_run(RunRecord("b", run_job_name("delta", "me"), D0, T0 + timedelta(hours=5)))
    entry = load_pick_histories(ctx, [DELTA], 2)[DELTA][0]
    run = latest_run(at_session(ctx, D0), *DELTA).run
    assert run is not None and run.run_id == "b"
    assert (entry.picked, entry.paused) == (run.picked, run.paused) == (1, 2)


def test_a_real_gated_run_is_counted_as_latest_run_counts_it() -> None:
    """The nightly's own record (``stats["summary"]``) of a run the regime gate paused."""
    outcome, reader = screen("STRESS", ON)
    ctx = open_context(reader, configs(), UserContext("site"), DAY)
    key = ("site", "big_liquid")
    run = latest_run(ctx, *key).run
    assert run is not None and run.paused == outcome.audit["decisions"]["PAUSED"] == 2
    records = reader.runs(run_job_name("big_liquid", "site"))
    assert len(records) == 1
    decisions = _decisions(records[0])  # what an earlier session's entry is counted from
    assert decisions is not None
    assert _counted(DAY, decisions).picked == run.picked and _counted(DAY, decisions).paused == 2
    entry = load_pick_histories(ctx, [key], 2)[key]
    assert [e.picked for e in entry] == [None, run.picked]  # the day before: no run


def test_a_record_saved_without_a_publish_is_seen_by_the_next_read(
    backend: MemoryBackend, ctx: ReadContext
) -> None:
    """The cached records are keyed on the runs generation too: an on-request run saves its
    record without moving ``visible_seq``."""
    before = load_pick_histories(ctx, [DELTA], 2)[DELTA][0]
    assert before.picked is None and before.not_run is not None
    when = T0 + timedelta(hours=24)
    record = RunRecord("late", run_job_name("delta", "me"), D0, when)
    seq = ctx.reader.visible_seq()
    stats = {"summary": {"decisions": {"QUALIFIED": 3}}}
    StoreWriter(backend).save_run(record.finish(when, stats=stats))
    assert ctx.reader.visible_seq() == seq
    after = load_pick_histories(ctx, [DELTA], 2)[DELTA][0]
    assert after.picked == 3 and after.not_run is None


# ---------------------------------------------------------------- frozen counts
# The counts come from each session's ``results/screen_runs`` rows (frozen at write); only a
# session without that partition, or a config with no row in one, reads run records.

GAMMA = ("me", "gamma")
ALPHA = ("site", "alpha")


def _freeze(backend: MemoryBackend, day: date, run_id: str, config: str, rows: Rows) -> None:
    counts = Counter(decision for _, decision, _, _ in rows)
    picked = sum(n for d, n in counts.items() if is_picked(d))
    frame = pd.DataFrame(
        [
            {
                "user_id": "me", "config_id": config, "config_hash": "h", "config_version": 1,
                "rows": len(rows), "passed": picked, "picked": picked,
                "paused": counts.get(PAUSED, 0), "decision_names": sorted(counts),
                "decision_counts": [counts[d] for d in sorted(counts)], "regime": None,
                "size_multiplier": 1.0, "previous_run_id": None, "previous_session": None,
                "previous_version": None, "new_picks": None, "dropped": None,
            }
        ]
    )  # fmt: skip
    for name in ("config_version", "previous_version", "new_picks", "dropped"):
        frame[name] = frame[name].astype("Int64")
    frame["session_date"] = day
    frame["knowledge_ts"] = pd.Timestamp(T0 + timedelta(hours=1))
    frame["source"] = "test"
    frame["run_id"] = run_id
    StoreWriter(backend).write_result("screen_runs", day, run_id, frame)


def _window(backend: MemoryBackend, framed: bool) -> list[date]:
    """s0 unframed (a run), s1 framed (delta superseded, gamma with no row but a record, alpha
    never ran), s2 framed with no run of delta, then the request session D1."""
    s0, s1, s2, _ = sessions_ending(D1, 4)
    _screen(backend, s0, "a", ROWS, 0)
    _screen(backend, s1, "b", ROWS, 1)
    _screen(backend, s1, "c", GATED, 2)  # supersedes b
    _screen(backend, s1, "g", ROWS[:1], 3, config="gamma")
    _screen(backend, D1, "d", ROWS[:2], 24)
    if framed:
        _freeze(backend, s1, "c", "delta", GATED)  # gamma: no row, its record is the fallback
        _freeze(backend, s2, "z", "other", ROWS)  # a partition with none of the asked configs
    return [s0, s1, s2, D1]


def test_frozen_counts_equal_the_record_counts(reader_of: Callable[[bool], StoreReader]) -> None:
    keys = [DELTA, GAMMA, ALPHA]
    old = load_pick_histories(_on(reader_of(False), D1), keys, 4)
    new = load_pick_histories(_on(reader_of(True), D1), keys, 4)
    assert new == old
    assert [(p.picked, p.paused) for p in new[DELTA]] == [(2, 0), (1, 2), (None, None), (2, 0)]
    assert [p.picked for p in new[GAMMA]] == [None, 1, None, None]  # the no-row fallback
    assert all(p.not_run is not None for p in new[ALPHA])


@pytest.fixture
def reader_of() -> Callable[[bool], StoreReader]:
    def build(framed: bool) -> StoreReader:
        backend = MemoryBackend()
        _window(backend, framed)
        return StoreReader(backend)

    return build


def test_a_framed_session_reads_one_screen_runs_partition_and_no_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = MemoryBackend()
    s0, s1, s2, _ = sessions_ending(D1, 4)
    for day, run in ((s0, "a"), (s1, "b"), (s2, "c")):
        _screen(backend, day, run, ROWS, 0)
        _freeze(backend, day, run, "delta", ROWS)
    _screen(backend, D1, "d", ROWS, 24)
    reader = StoreReader(backend)
    ctx = _on(reader, D1)
    reads: list[tuple[str, date]] = []
    real = reader.read_latest_runs
    monkeypatch.setattr(
        reader, "read_latest_runs",
        lambda t, d, **kw: (reads.append((t, d)), real(t, d, **kw))[1],
    )  # fmt: skip
    for name in ("runs_of", "runs"):
        monkeypatch.setattr(reader, name, lambda *a, **k: pytest.fail("a run record was read"))
    found = load_pick_histories(ctx, [DELTA], 4)[DELTA]
    assert [p.picked for p in found] == [2, 2, 2, 2]
    frozen_reads = [r for r in reads if r[0].endswith("screen_runs") and r[1] != D1]
    assert sorted(frozen_reads) == sorted({(t, d) for t, d in frozen_reads})  # once per session
    assert {d for _, d in frozen_reads} == {s0, s1, s2}
